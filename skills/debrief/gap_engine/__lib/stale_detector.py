"""Stale documentation detector — finds doc files that reference modified source files."""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from ..models import EvidenceRef, Finding


def get_file_git_date(file_path: Path, root: Path) -> str | None:
    """Get the last commit date for a file using git log."""
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--format=%ci", "--", str(file_path)],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip().split()[0]  # YYYY-MM-DD
    except (subprocess.TimeoutExpired, OSError):
        pass
    return None


def get_project_docs(root: Path) -> list[Path]:
    """Find documentation files in the project."""
    docs: list[Path] = []
    
    # Common doc locations
    doc_paths = [
        root / "docs",
        root / "doc",
        root / "Documentation",
        root / "CHANGELOG.md",
        root / "CHANGES.md",
        root / "docs" / "ARCHITECTURE.md",
    ]
    
    for doc_path in doc_paths:
        if doc_path.exists():
            if doc_path.is_file():
                docs.append(doc_path)
            else:
                # Glob markdown files in directory
                docs.extend(doc_path.glob("**/*.md"))
    
    return docs


def find_file_references(doc_path: Path, file_stems: set[str]) -> list[str]:
    """Find mentions of file stems in documentation."""
    references: list[str] = []
    
    try:
        content = doc_path.read_text(encoding="utf-8", errors="ignore")
        for stem in file_stems:
            # Look for file paths or module names in the doc
            patterns = [
                rf"\b{re.escape(stem)}\b",
                rf"`{re.escape(stem)}`",
                rf"{re.escape(stem)}\.py",
                rf"{re.escape(stem)}\.ts",
                rf"/{re.escape(stem)}/",
            ]
            for pattern in patterns:
                if re.search(pattern, content, re.IGNORECASE):
                    references.append(stem)
                    break
    except (OSError, UnicodeDecodeError):
        pass
    
    return references


def detect_stale_docs(
    root: Path,
    session_edited_files: list[Path],
    terminal_id: str,
    session_id: str,
    git_sha: str | None,
) -> list[Finding]:
    """Detect documentation files that reference source files modified this session.
    
    Compares doc modification dates against source file modification dates to find
    potentially stale documentation.
    """
    findings: list[Finding] = []
    
    if not session_edited_files:
        return findings
    
    # Get file stems for matching (module names without extensions)
    file_stems = set()
    for f in session_edited_files:
        file_stems.add(f.stem)
        if f.suffix:
            file_stems.add(f.stem + f.suffix)
    
    # Find all documentation files
    doc_files = get_project_docs(root)
    if not doc_files:
        return findings
    
    # Check each doc file for references to modified files
    for doc_path in doc_files:
        references = find_file_references(doc_path, file_stems)
        if not references:
            continue
        
        # Get modification dates
        doc_date = get_file_git_date(doc_path, root)
        
        # Check each referenced source file
        stale_count = 0
        stale_details: list[str] = []
        
        for edited_file in session_edited_files:
            if edited_file.stem in references or edited_file.name in references:
                source_date = get_file_git_date(edited_file, root)
                if source_date and doc_date:
                    # Source was modified after doc
                    if source_date > doc_date:
                        stale_count += 1
                        stale_details.append(
                            f"{edited_file.name} updated {source_date} (doc is {doc_date})"
                        )
        
        if stale_count > 0:
            findings.append(
                Finding(
                    id=f"DOCS-STALE-{len(findings) + 1:03d}",
                    title=f"Documentation references modified files",
                    description=f"docs/{doc_path.name} mentions {len(references)} source file(s); {stale_count} source(s) modified after this doc",
                    source_type="detector",
                    source_name="stale_docs_detector",
                    domain="docs",
                    gap_type="stale_docs",
                    severity="medium" if stale_count >= 2 else "low",
                    evidence_level="verified",
                    scope="local",
                    terminal_id=terminal_id,
                    session_id=session_id,
                    git_sha=git_sha,
                    evidence=[
                        EvidenceRef(
                            kind="path",
                            value=str(doc_path.relative_to(root)),
                            detail=f"references: {', '.join(set(references))}",
                        ),
                        EvidenceRef(
                            kind="git",
                            value="git log --format=%ci",
                            detail=f"stale reasons: {'; '.join(stale_details[:3])}",
                        ),
                    ],
                )
            )
    
    return findings
