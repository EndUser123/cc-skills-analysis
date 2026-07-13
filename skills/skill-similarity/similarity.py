#!/usr/bin/env python
"""
Find skills similar to a target skill.

Usage: python similarity.py <target_skill>

This script:
1. Parses the target skill to extract keywords, dependencies, category
2. Scans all skills in multiple directories:
   - P:\\\\\\.claude/skills (project-local)
   - ~/.claude/skills (user-local)
   - .claude-plugins/*/skills (plugin skills, both locations)
3. Calculates similarity scores based on multiple factors
4. Groups results by tier (HIGH/MEDIUM/LOW/MINIMAL)
5. Exports JSON report
"""

import json
import re
import sys as _sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

# gap-engine skill coverage for gap-engine session tracking
_gto_lib = Path("P:\\\\\\.claude/skills")
if str(_gto_lib) not in _sys.path:
    _sys.path.insert(0, str(_gto_lib))
from skills.debrief.gap_engine.__lib.skill_coverage_detector import _append_skill_coverage


@dataclass
class SkillInfo:
    """Information about a skill."""

    name: str
    path: Path
    description: str = ""
    category: str = ""
    triggers: list[str] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)
    suggest: list[str] = field(default_factory=list)
    keywords: set[str] = field(default_factory=set)
    content_lines: list[str] = field(default_factory=list)
    similarity_score: float = 0.0
    matched_keywords: set[str] = field(default_factory=set)


# Common English stop words to filter out from keyword extraction
STOP_WORDS = {
    "a",
    "an",
    "the",
    "and",
    "or",
    "but",
    "if",
    "then",
    "else",
    "when",
    "for",
    "of",
    "with",
    "by",
    "from",
    "to",
    "in",
    "on",
    "at",
    "as",
    "is",
    "are",
    "was",
    "were",
    "be",
    "been",
    "being",
    "have",
    "has",
    "had",
    "do",
    "does",
    "did",
    "will",
    "would",
    "could",
    "should",
    "may",
    "might",
    "must",
    "shall",
    "can",
    "need",
    "this",
    "that",
    "these",
    "those",
    "use",
    "used",
    "using",
    "make",
    "made",
    "get",
    "got",
    "into",
    "over",
    "under",
    "about",
    "above",
    "below",
    "after",
    "before",
    "between",
    "through",
    "during",
    "without",
    "within",
    "upon",
    "via",
    "per",
    # Technical terms that are too generic
    "skill",
    "skills",
    "command",
    "workflow",
    "system",
    "tool",
    "file",
    "based",
    "enabled",
    "related",
    "specific",
    "general",
    "auto",
    "automatic",
}


def parse_frontmatter_and_content(skill_file: Path) -> dict:
    """Parse YAML frontmatter and content from SKILL.md.

    Robust parsing that:
    - Only recognizes the FIRST frontmatter section (at start of file)
    - Ignores --- markers in code blocks or other contexts
    - Handles edge cases like empty frontmatter
    """
    content = skill_file.read_text()
    lines = content.split("\n")

    # Find the FIRST frontmatter section (must be at start of file)
    # Skip leading empty lines
    first_non_empty = 0
    while first_non_empty < len(lines) and not lines[first_non_empty].strip():
        first_non_empty += 1

    # Check if first non-empty line is ---
    if first_non_empty >= len(lines) or lines[first_non_empty].strip() != "---":
        # No frontmatter found
        return {
            "frontmatter": {
                "name": "",
                "description": "",
                "category": "",
                "triggers": [],
                "aliases": [],
                "depends_on_skills": [],
                "suggest": [],
            },
            "content": content,
            "content_lines": lines,
        }

    # Find closing ---
    frontmatter_end = first_non_empty + 1
    while frontmatter_end < len(lines) and lines[frontmatter_end].strip() != "---":
        frontmatter_end += 1

    if frontmatter_end >= len(lines):
        # No closing --- found, treat rest as content
        frontmatter_lines = lines[first_non_empty + 1 :]
        content_lines = []
    else:
        frontmatter_lines = lines[first_non_empty + 1 : frontmatter_end]
        content_lines = lines[frontmatter_end + 1 :]

    # Simple YAML parsing for our needs
    # We only care about specific fields - ignore everything else
    data = {
        "name": "",
        "description": "",
        "category": "",
        "triggers": [],
        "aliases": [],
        "depends_on_skills": [],
        "suggest": [],
    }

    current_list = None
    for line in frontmatter_lines:
        line_stripped = line.strip()
        if not line_stripped or line_stripped.startswith("#"):
            continue

        # Handle list start (key ending with :)
        if line_stripped.endswith(":") and not line_stripped.startswith("- "):
            key = line_stripped[:-1]
            # Only track lists we care about
            if key in ("triggers", "aliases", "depends_on_skills", "suggest"):
                current_list = key
                if current_list not in data:
                    data[current_list] = []
            else:
                current_list = None
            continue

        # Handle list items with dash
        if current_list and line_stripped.startswith("- "):
            value = line_stripped[2:].strip()
            # Remove quotes
            value = value.strip("\"'")
            # Remove leading slash if present (for skill names)
            if value.startswith("/"):
                value = value[1:]
            data[current_list].append(value)
            continue

        # Handle inline list format: key: [item1, item2]
        inline_list_match = re.match(r"^(\w+(?:_\w+)*)\s*:\s*\[(.*)\]$", line_stripped)
        if inline_list_match:
            key, values_str = inline_list_match.groups()
            if key in ("triggers", "aliases", "depends_on_skills", "suggest"):
                # Parse inline list - handle both single and double quotes
                items = []
                for item in values_str.split(","):
                    item = item.strip().strip("\"'")
                    if item:
                        # Remove leading slash if present
                        if item.startswith("/"):
                            item = item[1:]
                        items.append(item)
                data[key] = items
            continue

        # Handle key-value pairs (only for known scalar fields)
        if ":" in line_stripped and not line_stripped.startswith("- "):
            parts = line_stripped.split(":", 1)
            if len(parts) == 2:
                key, value = parts
                key = key.strip()
                value = value.strip().strip("\"'")
                # Only store scalar fields we care about
                if key in ("name", "version", "description", "category", "domain"):
                    data[key] = value

    return {
        "frontmatter": data,
        "content": "\n".join(content_lines),
        "content_lines": content_lines,
        # Add raw frontmatter lines for debugging
        "_frontmatter_lines": frontmatter_lines,
    }


def extract_keywords_from_text(text: str, max_keywords: int = 30) -> set[str]:
    """Extract meaningful keywords from text using word frequency."""
    text_lower = text.lower()

    # Remove markdown code blocks
    text_lower = re.sub(r"```.*?```", "", text_lower, flags=re.DOTALL)
    text_lower = re.sub(r"`[^`]+`", "", text_lower)

    # Extract words
    words = re.findall(r"\b[a-z][a-z0-9_-]+\b", text_lower)

    # Filter stop words and short words
    words = [w for w in words if w not in STOP_WORDS and len(w) >= 3]

    # Count frequency
    word_freq = defaultdict(int)
    for word in words:
        word_freq[word] += 1

    # Get top keywords
    sorted_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)
    return {word for word, _ in sorted_words[:max_keywords]}


def calculate_similarity(
    skill: SkillInfo,
    target_keywords: set[str],
    target_category: str,
    target_depends: set[str],
    target_suggests: set[str],
    target_name: str,
) -> float:
    """Calculate similarity score to target skill."""
    score = 0.0

    # Skip self
    if skill.name.lower() == target_name.lower():
        return 0.0

    # Category match
    if skill.category and skill.category == target_category:
        score += 0.3

    # Keyword matching in description (higher weight)
    desc_lower = skill.description.lower()
    desc_words = set(re.findall(r"\b[a-z][a-z0-9_-]+\b", desc_lower))
    for keyword in target_keywords:
        if keyword in desc_words:
            score += 0.1
            skill.matched_keywords.add(keyword)

    # Keyword matching in content (lower weight)
    for keyword in target_keywords:
        if keyword in skill.keywords:
            score += 0.03

    # Shared dependencies
    for dep in skill.depends_on:
        if dep in target_depends:
            score += 0.2

    # Shared suggestions
    for sugg in skill.suggest:
        if sugg in target_suggests:
            score += 0.15

    # Trigger/alias match
    all_names = [skill.name.lower()] + [a.lower() for a in skill.aliases]
    if target_name.lower() in all_names:
        score += 0.5

    return min(score, 1.0)  # Cap at 1.0


def get_skills_directories() -> list[Path]:
    """Return all directories containing skills.

    Searches in:
    1. Project-local skills: P:\\\\\\.claude/skills
    2. User-local skills: ~/.claude/skills
    3. Plugin skills: .claude-plugins/*/skills (both locations)
    """
    # Get base directories
    # __file__ is in P:\\\\\\.claude/skills/similarity/similarity.py
    # So __file__.parent.parent.parent is P:\\\\\\.claude
    base_dir = Path(__file__).parent.parent.parent
    user_dir = Path.home() / ".claude"

    directories = [
        base_dir / "skills",
        user_dir / "skills",
    ]

    # Add plugin skills directories from both locations
    for plugin_dir in base_dir.glob(".claude-plugins/*/skills"):
        directories.append(plugin_dir)
    for plugin_dir in user_dir.glob(".claude-plugins/*/skills"):
        directories.append(plugin_dir)

    # Return only existing directories
    return [d for d in directories if d.exists()]


def scan_skills(
    skills_dirs: list[Path], target_name: str
) -> tuple[list[SkillInfo], SkillInfo | None]:
    """Scan all skills across multiple directories and return parsed information plus target skill.

    Handles duplicates by preferring project-local skills over user-local skills.
    Returns None for target_skill if not found.
    """
    skills_dict = {}  # name -> SkillInfo (for deduplication)
    target_skill = None

    for skills_dir in skills_dirs:
        for skill_path in skills_dir.iterdir():
            if not skill_path.is_dir():
                continue

            skill_file = skill_path / "SKILL.md"
            if not skill_file.exists():
                continue

            try:
                parsed = parse_frontmatter_and_content(skill_file)
                fm = parsed["frontmatter"]

                # Use frontmatter name, or fall back to directory name
                skill_name = fm.get("name", "").strip()
                if not skill_name:
                    skill_name = skill_path.name

                skill = SkillInfo(
                    name=skill_name,
                    path=skill_path,
                    description=fm.get("description", ""),
                    category=fm.get("category", ""),
                    triggers=fm.get("triggers", []),
                    aliases=fm.get("aliases", []),
                    depends_on=fm.get("depends_on_skills", []),
                    suggest=fm.get("suggest", []),
                    content_lines=parsed["content_lines"],
                )

                # Extract keywords from content
                content = parsed["content"]
                skill.keywords = extract_keywords_from_text(content)

                # Check if this is the target skill (first occurrence wins)
                if target_skill is None and skill.name.lower() == target_name.lower().lstrip("/"):
                    target_skill = skill

                # Handle duplicates: prefer project-local (P:\\\\\\) over user-local (~)
                # If skill already exists, only replace if the new path is project-local
                skill_key = skill.name.lower()
                if skill_key not in skills_dict:
                    skills_dict[skill_key] = skill
                else:
                    existing = skills_dict[skill_key]
                    # Replace if existing is user-local and new is project-local
                    if str(existing.path).startswith(str(Path.home())) and not str(
                        skill_path
                    ).startswith(str(Path.home())):
                        skills_dict[skill_key] = skill

            except Exception as e:
                print(f"Warning: Failed to parse {skill_file}: {e}")

    skills = list(skills_dict.values())
    return skills, target_skill


def main():
    """Main entry point."""
    if len(_sys.argv) < 2:
        print("Usage: python similarity.py <target_skill>")
        print("Example: python similarity.py /evolve")
        _sys.exit(1)

    target_name = _sys.argv[1].lstrip("/")
    skills_dirs = get_skills_directories()

    if not skills_dirs:
        print("Error: No skills directories found!")
        _sys.exit(1)

    print(f"Scanning skills for similarity to /{target_name}...")
    print(f"Searching in {len(skills_dirs)} directories:")
    for d in skills_dirs:
        print(f"  - {d}")
    print("=" * 70)

    skills, target_skill = scan_skills(skills_dirs, target_name)

    if not target_skill:
        print(f"Error: Target skill '/{target_name}' not found!")
        _sys.exit(1)

    print(f"Found {len(skills)} skills with SKILL.md files")
    print(f"Target: /{target_skill.name}")
    print(f"Description: {target_skill.description}")
    print(f"Category: {target_skill.category}")
    print(f"Keywords extracted: {len(target_skill.keywords)}")
    print()

    # Extract target metadata for comparison
    target_keywords = target_skill.keywords
    target_category = target_skill.category
    target_depends = set(target_skill.depends_on)
    target_suggests = set(target_skill.suggest)

    # Calculate similarity scores
    for skill in skills:
        skill.similarity_score = calculate_similarity(
            skill, target_keywords, target_category, target_depends, target_suggests, target_name
        )

    # Sort by similarity score
    skills_by_similarity = sorted(skills, key=lambda s: s.similarity_score, reverse=True)

    # Group by similarity tiers
    tiers = {
        "HIGH (0.5+)": [],
        "MEDIUM (0.2-0.49)": [],
        "LOW (0.05-0.19)": [],
        "MINIMAL (<0.05)": [],
    }

    for skill in skills_by_similarity:
        if skill.similarity_score >= 0.5:
            tiers["HIGH (0.5+)"].append(skill)
        elif skill.similarity_score >= 0.2:
            tiers["MEDIUM (0.2-0.49)"].append(skill)
        elif skill.similarity_score >= 0.05:
            tiers["LOW (0.05-0.19)"].append(skill)
        else:
            tiers["MINIMAL (<0.05)"].append(skill)

    # Output results
    for tier_name, tier_skills in tiers.items():
        if not tier_skills:
            continue

        print(f"\n{tier_name}")
        print("-" * 70)

        for skill in tier_skills[:10]:  # Limit to top 10 per tier
            print(f"\n  /{skill.name} (score: {skill.similarity_score:.2f})")
            print(f"    Description: {skill.description[:80]}...")
            if skill.matched_keywords:
                print(f"    Keywords: {', '.join(sorted(list(skill.matched_keywords)[:10]))}")
            if skill.depends_on:
                print(f"    Depends on: {', '.join(skill.depends_on)}")

    # Export JSON for further analysis
    output = []
    for skill in skills_by_similarity:
        output.append(
            {
                "name": f"/{skill.name}",
                "score": round(skill.similarity_score, 3),
                "description": skill.description,
                "category": skill.category,
                "keywords": sorted(list(skill.matched_keywords))[:15],
                "depends_on": skill.depends_on,
                "suggest": skill.suggest,
            }
        )

    # Create output directory in P:\\\\\\.claude/.artifacts/{terminal_id}/similarity/
    terminal_id = os.environ.get("CLAUDE_TERMINAL_ID", "cli")
    evidence_dir = Path.cwd().resolve() / ".claude" / ".artifacts" / terminal_id / "similarity"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    output_file = evidence_dir / f"{target_name}_report.json"
    output_file.write_text(json.dumps(output, indent=2))
    print(f"\n\nFull report exported to: {output_file}")

    # Log gap-engine skill coverage after report is written
    try:
        _append_skill_coverage(
            target_key=f"skills/similarity/{target_name}",
            skill="/similarity",
            terminal_id="cli",
            git_sha=None,
        )
    except Exception:
        pass  # best-effort


if __name__ == "__main__":
    main()
