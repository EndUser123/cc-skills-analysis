"""
Core TRACE methodology - domain-agnostic trace-through verification.

Base class for all domain-specific TRACE adapters.

Enhanced with debugRCA integrations:
- Evidence saturation detection
- Red flag detection
- ACH scenario generation
- Timeline visualization
- Call graph hypothesis generation
- CKS findings persistence
- Differential TRACE capability

Enhanced with Tree-of-Thought (ToT) integration:
- Branching scenario generation based on conditional logic
- Branch scoring and pruning for focused TRACE effort
- Opt-out support via --no-tot flag
"""

import os
import re
import subprocess
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

# gap-engine skill coverage integration
_gto_lib = Path("P:\\\\\\.claude/skills")
if str(_gto_lib) not in sys.path:
    sys.path.insert(0, str(_gto_lib))
from skills.debrief.gap_engine.__lib.skill_coverage_detector import _append_skill_coverage


@dataclass
class TraceScenario:
    """A TRACE scenario (happy path, error path, edge case)."""

    name: str
    description: str
    state_table: list[dict[str, Any]] = field(default_factory=list)
    findings: list[str] = field(default_factory=list)


@dataclass
class TraceIssue:
    """A finding from TRACE analysis."""

    severity: str  # P0, P1, P2, P3
    category: str
    location: str  # Line numbers or section reference
    problem: str
    impact: str
    recommendation: str


@dataclass
class VerificationStep:
    """A verification step for hypothesis testing (Phase 4)."""

    hypothesis: str  # The hypothesis being tested
    confirmation_test: str  # What would prove this theory
    refutation_test: str  # What would disprove this theory
    confidence: str  # Confidence level: High, Medium, Low


@dataclass
class TraceReport:
    """Complete TRACE report for a target."""

    domain: str
    target_path: Path
    date: datetime
    scenarios: list[TraceScenario] = field(default_factory=list)
    issues: list[TraceIssue] = field(default_factory=list)
    summary: dict[str, int] = field(default_factory=dict)
    ach_scenarios: list[TraceScenario] = field(default_factory=list)  # ACH-based scenarios
    verification_steps: list[VerificationStep] = field(default_factory=list)  # Phase 4 verification

    def state_table_to_mermaid(self, scenario: TraceScenario) -> str:
        """Convert TRACE state table to Mermaid flowchart.

        Args:
            scenario: TraceScenario with state_table to convert

        Returns:
            Mermaid flowchart as string
        """
        if not scenario.state_table:
            return ""

        mermaid = ["flowchart TD"]
        mermaid.append("    classDef default fill:#e1f5ff,stroke:#01579b,stroke-width:2px")

        # Track defined styles to avoid O(n²) string operations
        defined_styles = set()

        for i, step in enumerate(scenario.state_table):
            node_id = f"Step{i}"
            operation = step.get("operation", f"Step {i}").replace('"', '\\"')
            notes = step.get("notes", "")

            # Add emoji indicators for notes
            if "✓" in notes or "PASS" in notes.upper():
                if "pass" not in defined_styles:
                    mermaid.append("    classDef pass fill:#c8e6c9,stroke:#2e7d32,stroke-width:2px")
                    defined_styles.add("pass")
                class_str = " :::pass"
            elif "✗" in notes or "FAIL" in notes.upper() or "BUG" in notes.upper():
                if "fail" not in defined_styles:
                    mermaid.append("    classDef fail fill:#ffcdd2,stroke:#c62828,stroke-width:2px")
                    defined_styles.add("fail")
                class_str = " :::fail"
            elif "⚠" in notes or "WARN" in notes.upper():
                if "warn" not in defined_styles:
                    mermaid.append("    classDef warn fill:#fff9c4,stroke:#f57f17,stroke-width:2px")
                    defined_styles.add("warn")
                class_str = " :::warn"
            else:
                class_str = ""

            # Create node label with operation
            label = f"{i}. {operation}"
            mermaid.append(f'    {node_id}["{label}"]{class_str}')

            # Add edge from previous step
            if i > 0:
                prev_id = f"Step{i - 1}"
                edge_label = step.get("transition", "")
                if edge_label:
                    mermaid.append(f"    {prev_id} -->|{edge_label}| {node_id}")
                else:
                    mermaid.append(f"    {prev_id} --> {node_id}")

        return "\n".join(mermaid)

    def generate_call_graph_recommendation(self) -> str:
        """Generate call graph visualization recommendation for code domain.

        Returns:
            Recommendation text with installation and usage instructions
        """
        if self.domain != "code":
            return ""

        recommendation = [
            "### Call Graph Visualization",
            "",
            "**Recommendation**: Generate a call graph to visualize function call relationships.",
            "",
            "#### Installation",
            "```bash",
            "pip install pyan pygraphviz",
            "# Also install Graphviz: https://graphviz.org/download/",
            "```",
            "",
            "#### Usage",
            "```bash",
            "# Generate DOT file",
            "python -m pyan "
            + str(self.target_path)
            + " --uses --no-defines --colored --grouped --annotated --dot > trace_callgraph.dot",
            "",
            "# Convert to PNG",
            "dot -Tpng trace_callgraph.dot -o trace_callgraph.png",
            "",
            "# View the file",
            "# Windows: start trace_callgraph.png",
            "# Linux/Mac: open trace_callgraph.png",
            "```",
            "",
            "#### What to Look For",
            "- Circular dependencies (A calls B, B calls A)",
            "- Deep call stacks (>5 levels)",
            "- Unexpected cross-module calls",
            "- Single functions called from many places (coupling risk)",
            "",
        ]

        return "\n".join(recommendation)

    def generate_program_slicing_recommendation(self) -> str:
        """Generate program slicing recommendation when circular deps detected.

        Returns:
            Recommendation text if circular dependencies found, empty string otherwise
        """
        # Check if any issue mentions circular dependencies
        has_circular_deps = any(
            "circular" in issue.problem.lower() or "cycle" in issue.problem.lower()
            for issue in self.issues
        )

        if not has_circular_deps:
            return ""

        recommendation = [
            "### Program Slicing Recommendation",
            "",
            "**Detected**: Circular dependencies in call graph.",
            "",
            "**Action**: Use program slicing to isolate affected code paths.",
            "",
            "#### Installation",
            "```bash",
            "pip install pycg",
            "```",
            "",
            "#### Usage",
            "```bash",
            "# Generate call graph for dependency analysis",
            "pycg " + str(self.target_path) + " --package __main__ > trace_deps.txt",
            "",
            "# Analyze the output for circular imports",
            "# Look for modules that import each other",
            "```",
            "",
            "#### What to Look For",
            "- Modules importing each other directly (A imports B, B imports A)",
            "- Indirect cycles (A → B → C → A)",
            "- Consider refactoring to break cycles (extract shared code)",
            "",
        ]

        return "\n".join(recommendation)

    # ========================================
    # debugRCA Integration Methods
    # ========================================

    def validate_quality(self) -> list[str]:
        """Validate TRACE report for anti-debugging patterns (red flag detection).

        Returns:
            List of red flag warnings (empty if no issues)

        Integration with debugRCA's red flag detection framework.
        """
        red_flags = []

        for issue in self.issues:
            # Check 1: P0/P1 issues without line references
            if issue.severity in ["P0", "P1"]:
                if not self._has_line_reference(issue.location):
                    red_flags.append(
                        f"P0/P1 issue without line reference: {issue.category} - {issue.problem}"
                    )

            # Check 2: Vague locations
            if issue.severity in ["P0", "P1", "P2"]:
                if self._is_vague_location(issue.location):
                    red_flags.append(f"Vague location for {issue.severity} issue: {issue.location}")

            # Check 3: Missing impact or recommendation
            if not issue.impact or issue.impact.strip() == "":
                red_flags.append(f"Missing impact for {issue.severity} issue: {issue.category}")
            if not issue.recommendation or issue.recommendation.strip() == "":
                red_flags.append(
                    f"Missing recommendation for {issue.severity} issue: {issue.category}"
                )

        # Check 4: Contradictory findings
        red_flags.extend(self._detect_contradictions())

        return red_flags

    def _has_line_reference(self, location: str) -> bool:
        """Check if location contains line number reference."""
        if not location:
            return False
        line_indicators = ["line", "Line", "L:", "l:", ":", "-", ","]
        return any(indicator in location for indicator in line_indicators)

    def _is_vague_location(self, location: str) -> bool:
        """Check if location is too vague."""
        if not location:
            return True
        vague_patterns = [
            "function",
            "method",
            "class",
            "module",
            "file",
            "somewhere",
            "unknown",
            "various",
            "multiple",
            "somewhere in",
            "area",
            "section",
        ]
        location_lower = location.lower()
        return len(location) < 5 or any(pattern in location_lower for pattern in vague_patterns)

    def _detect_contradictions(self) -> list[str]:
        """Detect contradictory findings in TRACE report."""
        contradictions = []

        # Group issues by category
        category_issues = {}
        for issue in self.issues:
            if issue.category not in category_issues:
                category_issues[issue.category] = []
            category_issues[issue.category].append(issue)

        # Check for contradictory severities in same category
        for category, cat_issues in category_issues.items():
            if len(cat_issues) > 1:
                severities = [issue.severity for issue in cat_issues]
                has_critical = any(s in ["P0", "P1"] for s in severities)
                has_minor = any(s in ["P2", "P3"] for s in severities)

                if has_critical and has_minor:
                    contradictions.append(
                        f"Contradictory findings in {category}: "
                        f"both critical and minor issues detected"
                    )

        return contradictions

    def persist_to_cks(self) -> int:
        """Store TRACE findings to CKS for cross-session pattern recognition.

        Returns:
            Number of findings successfully stored (0 if CKS unavailable)

        Integration with debugRCA's CKS findings storage framework.
        """
        # Add CSF src to path for CKS integration
        csf_src = str(Path("P:\\\\\\__csf/src").resolve())
        if csf_src not in sys.path:
            sys.path.insert(0, csf_src)

        try:
            import warnings

            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", category=DeprecationWarning)
                from cks.unified import CKS

            cks = CKS()
            stored_count = 0

            for issue in self.issues:
                finding_type = self._map_category_to_type(issue.category)
                severity = self._map_severity(issue.severity)
                line_number = self._extract_line_number(issue.location)

                # Build finding message
                message = f"[{issue.severity}] {issue.location}: {issue.problem}"

                # Store to CKS
                cks.store_finding(
                    finding_type=finding_type,
                    source="trace",
                    message=message,
                    file_path=str(self.target_path),
                    line_number=line_number,
                    severity=severity,
                    metadata={
                        "domain": self.domain,
                        "impact": issue.impact,
                        "recommendation": issue.recommendation,
                        "date": self.date.isoformat(),
                    },
                )
                stored_count += 1

            # gap-engine skill coverage logging
            try:
                _append_skill_coverage(
                    target_key="skills/trace",
                    skill="/trace",
                    terminal_id=os.environ.get("TERMINAL_ID", os.environ.get("TERM_ID", "unknown")),
                    git_sha=None,
                )
            except Exception:
                pass

            return stored_count

        except ImportError:
            # CKS not available - return 0
            return 0
        except Exception as e:
            # Storage failed - log warning but don't fail
            print(f"Warning: CKS storage failed: {e}")
            return 0

    def _map_category_to_type(self, category: str) -> str:
        """Map TRACE category to CKS finding type."""
        category_map = {
            "Logic Errors": "LOGIC",
            "Resource Leaks": "RESOURCE_LEAK",
            "Race Conditions": "RACE_CONDITION",
            "Inconsistencies": "INCONSISTENCY",
            "Logic Error": "LOGIC",
            "Resource Leak": "RESOURCE_LEAK",
            "Race Condition": "RACE_CONDITION",
        }
        return category_map.get(category, "ISSUE")

    def _map_severity(self, trace_severity: str) -> str:
        """Map TRACE severity (P0-P3) to CKS severity."""
        severity_map = {"P0": "critical", "P1": "high", "P2": "medium", "P3": "low"}
        return severity_map.get(trace_severity, "medium")

    def _extract_line_number(self, location: str) -> Optional[int]:
        """Extract line number from location string."""
        if not location:
            return None
        match = re.search(r"\d+", location)
        if match:
            return int(match.group())
        return None

    def to_markdown(self) -> str:
        """Convert report to markdown format."""
        lines = [
            f"## TRACE Report: {self.domain}:{self.target_path}",
            "",
            f"**Date**: {self.date.strftime('%Y-%m-%d')}",
            f"**Scenarios traced**: {len(self.scenarios)}",
            "",
        ]

        # Add call graph recommendation for code domain
        if self.domain == "code":
            call_graph_rec = self.generate_call_graph_recommendation()
            if call_graph_rec:
                lines.append(call_graph_rec)

        # Add Mermaid diagrams for each scenario with state tables
        for scenario in self.scenarios:
            if scenario.state_table:
                mermaid_diagram = self.state_table_to_mermaid(scenario)
                if mermaid_diagram:
                    lines.extend(
                        [
                            f"### Visualization: {scenario.name}",
                            "",
                            "```mermaid",
                            mermaid_diagram,
                            "```",
                            "",
                        ]
                    )

        # Add program slicing recommendation if circular deps detected
        slicing_rec = self.generate_program_slicing_recommendation()
        if slicing_rec:
            lines.append(slicing_rec)

        # Summary section
        lines.extend(["### Summary", ""])

        for category, count in self.summary.items():
            status = "✅" if count == 0 else "❌"
            lines.append(f"- {status} {category}: {count}")

        lines.append("")

        # Issues section
        if self.issues:
            lines.extend(["### Issues Found", ""])

            for i, issue in enumerate(self.issues, 1):
                lines.extend(
                    [
                        f"#### Issue #{i}: {issue.severity} - {issue.category}",
                        f"- **Location**: {issue.location}",
                        f"- **Problem**: {issue.problem}",
                        f"- **Impact**: {issue.impact}",
                        f"- **Recommendation**: {issue.recommendation}",
                        "",
                    ]
                )

        # TRACE results
        lines.extend(["### TRACE Results", ""])

        if all(count == 0 for count in self.summary.values()):
            lines.append("✅ PASS - All scenarios traced correctly")
        else:
            lines.append("❌ FAIL - Issues found during TRACE")

        lines.append("")

        return "\n".join(lines)


class Tracer(ABC):
    """
    Base class for all domain-specific TRACE adapters.

    Domain adapters inherit from this class and implement:
    - read_target(): Load target file/content
    - define_scenarios(): Define happy/error/edge cases
    - trace_scenario(): Execute trace for one scenario
    - check_checklist(): Verify domain-specific checks

    Enhanced with Tree-of-Thought (ToT) branching scenario generation.
    """

    def __init__(
        self,
        target_path: Path,
        template: int | None = None,
        full_review: bool = False,
        enable_tot: bool | None = None,
    ):
        self.target_path = target_path
        self.template = template
        self.full_review = full_review
        self.content: str = ""

        # ToT enhancement: check opt-out flag
        # --no-tot flag disables ToT branching enhancement
        if enable_tot is None:
            # Default: enabled unless TRACE_NO_TOT environment variable is set
            enable_tot = os.environ.get("TRACE_NO_TOT", "false").lower() != "true"
        self.enable_tot = enable_tot

        self.report = TraceReport(
            domain=self.__class__.__name__.replace("Tracer", "").lower(),
            target_path=target_path,
            date=datetime.now(),
        )

    @abstractmethod
    def read_target(self) -> str:
        """Read target file/content."""
        pass

    @abstractmethod
    def define_scenarios(self) -> list[TraceScenario]:
        """Define scenarios to trace (happy, error, edge)."""
        pass

    @abstractmethod
    def trace_scenario(self, scenario: TraceScenario) -> None:
        """Execute trace for a single scenario."""
        pass

    @abstractmethod
    def check_checklist(self) -> list[TraceIssue]:
        """Verify domain-specific checklist."""
        pass

    @abstractmethod
    def read_context(self, pattern: str) -> dict[str, str]:
        """Read context files matching glob pattern for cross-context verification.

        Args:
            pattern: Glob pattern for context files (e.g., "**/*registry*.py", "**/router*.py")

        Returns:
            Dictionary mapping file paths to file contents
        """
        pass

    # ========================================
    # Tree-of-Thought (ToT) Integration
    # ========================================

    def generate_tot_scenarios(self) -> list[TraceScenario]:
        """Generate branching scenarios using Tree-of-Thought reasoning.

        Returns:
            List of additional TraceScenario objects from ToT branching analysis

        Integration: Uses BranchGenerator from /code/utils/tot_tracer.py
        to analyze conditional logic and generate high-value execution paths.
        """
        if not self.enable_tot:
            return []

        # Import BranchGenerator from shared utils
        try:
            # Add code skill utils to path
            code_utils_path = Path("P:\\\\\\.claude/skills/code/utils")
            if str(code_utils_path) not in sys.path:
                sys.path.insert(0, str(code_utils_path))

            from tot_tracer import BranchGenerator

            generator = BranchGenerator(self.content)
            branches = generator.generate_branches()

            # Prune unlikely branches
            pruned_branches = generator.prune_branches(branches)

            # Convert ToT branches to TRACE scenarios
            tot_scenarios = []
            for branch in pruned_branches:
                scenario = TraceScenario(
                    name=f"ToT Branch: {branch['description'][:50]}",
                    description=f"Branch scenario: {branch['description']}",
                    state_table=[],
                    findings=[],
                )
                tot_scenarios.append(scenario)

            return tot_scenarios

        except ImportError:
            # ToT utils not available - return empty list
            return []
        except Exception as e:
            # ToT generation failed - log warning but continue
            print(f"Warning: ToT scenario generation failed: {e}")
            return []

    def trace(self) -> str:
        """
        Main TRACE workflow.

        Returns:
            TRACE report in markdown format
        """
        try:
            # Step 1: Read target
            self.content = self.read_target()

            # Step 2: Define scenarios
            scenarios = self.define_scenarios()

            # Step 2.5: Generate ToT branching scenarios (if enabled)
            if self.enable_tot:
                try:
                    tot_scenarios = self.generate_tot_scenarios()
                    if tot_scenarios:
                        scenarios.extend(tot_scenarios)
                except Exception as e:
                    # Log ToT generation error but continue
                    print(f"Warning: ToT scenario generation failed: {e}")

            # Step 3: Trace each scenario
            for scenario in scenarios:
                try:
                    self.trace_scenario(scenario)
                except Exception as e:
                    # Log scenario-level error but continue with other scenarios
                    scenario.findings.append(f"⚠️ Scenario tracing failed: {e}")
                finally:
                    self.report.scenarios.append(scenario)

            # Step 4: Check domain-specific checklist
            try:
                issues = self.check_checklist()
                self.report.issues.extend(issues)
            except Exception as e:
                # Log checklist error but don't fail entire TRACE
                self.report.issues.append(
                    TraceIssue(
                        severity="P2",
                        category="Checklist Error",
                        location="trace()",
                        problem=f"Checklist validation failed: {e}",
                        impact="Some domain-specific checks may have been skipped",
                        recommendation="Review checklist implementation for bugs",
                    )
                )

            # Step 5: Generate summary
            self.report.summary = self._generate_summary()

            # Step 6: Return report
            return self.report.to_markdown()

        except FileNotFoundError as e:
            # Critical error: target file not found
            error_report = TraceReport(
                domain=self.__class__.__name__.replace("Tracer", "").lower(),
                target_path=self.target_path,
                date=datetime.now(),
            )
            error_report.issues.append(
                TraceIssue(
                    severity="P0",
                    category="File Not Found",
                    location=str(self.target_path),
                    problem=f"Target file not found: {e}",
                    impact="Cannot perform TRACE - target file does not exist or is not readable",
                    recommendation="Check file path and permissions",
                )
            )
            error_report.summary = {"File Access Error": 1}
            return error_report.to_markdown()

        except PermissionError as e:
            # Critical error: permission denied
            error_report = TraceReport(
                domain=self.__class__.__name__.replace("Tracer", "").lower(),
                target_path=self.target_path,
                date=datetime.now(),
            )
            error_report.issues.append(
                TraceIssue(
                    severity="P0",
                    category="Permission Denied",
                    location=str(self.target_path),
                    problem=f"Permission denied reading target: {e}",
                    impact="Cannot perform TRACE - insufficient permissions to read target file",
                    recommendation="Check file permissions and run with appropriate access",
                )
            )
            error_report.summary = {"File Access Error": 1}
            return error_report.to_markdown()

        except Exception as e:
            # Unexpected error: provide context and re-raise
            raise RuntimeError(f"TRACE failed for {self.target_path}: {e}") from e

    def _generate_summary(self) -> dict[str, int]:
        """Generate summary statistics from issues."""
        summary = {
            "Logic Errors Found": 0,
            "Resource Leaks Found": 0,
            "Race Conditions Found": 0,
            "Inconsistencies Found": 0,
        }

        for issue in self.report.issues:
            category = issue.category
            if category in summary:
                summary[category] += 1
            else:
                summary[category] = 1

        return summary

    def to_dict(self) -> dict[str, Any]:
        """Convert report to dictionary format."""
        return {
            "domain": self.report.domain,
            "target_path": str(self.report.target_path),
            "date": self.report.date.isoformat(),
            "scenarios": [
                {
                    "name": s.name,
                    "description": s.description,
                    "state_table": s.state_table,
                    "findings": s.findings,
                }
                for s in self.report.scenarios
            ],
            "issues": [
                {
                    "severity": i.severity,
                    "category": i.category,
                    "location": i.location,
                    "problem": i.problem,
                    "impact": i.impact,
                    "recommendation": i.recommendation,
                }
                for i in self.report.issues
            ],
            "summary": self.report.summary,
        }


# ========================================
# debugRCA Integration Utilities
# ========================================


def generate_rca_timeline_mermaid(
    events: list[dict[str, Any]], title: str = "Incident Timeline"
) -> str:
    """Generate Mermaid timeline from incident events for RCA Phase 1.

    Integration: Allows debugRCA to use TRACE's Mermaid visualization
    for incident timeline reconstruction.

    Args:
        events: List of event dictionaries with 'timestamp', 'description',
                optional 'cause' and 'status' keys
        title: Title for the timeline

    Returns:
        Mermaid timeline diagram as string

    Example:
        >>> events = [
        ...     {"timestamp": "2024-01-15 10:23", "description": "Error", "status": "error"}
        ... ]
        >>> mermaid = generate_rca_timeline_mermaid(events, "Outage")
    """
    if not events:
        return ""

    mermaid = ["%%{init: {'theme':'base', 'themeVariables': { 'primaryColor':'#01579b'}}}%%"]
    mermaid.append("timeline")
    mermaid.append(f"    title {title}")

    for event in events:
        timestamp = event.get("timestamp", "Unknown")
        description = event.get("description", "Event")
        cause = event.get("cause", "")
        status = event.get("status", "unknown")

        # Add status indicators
        if "success" in status.lower() or "pass" in status.lower():
            description = f"✓ {description}"
        elif "error" in status.lower() or "fail" in status.lower():
            description = f"✗ {description}"
        elif "warning" in status.lower() or "warn" in status.lower():
            description = f"⚠ {description}"

        mermaid.append(f"    {timestamp} : {description}")

        if cause:
            mermaid.append(f"              : {cause}")

    return "\n".join(mermaid)


def generate_hypotheses_from_call_graph(target_file: str) -> list[str]:
    """Generate hypotheses from call graph analysis for RCA Phase 2.

    Integration: Uses TRACE's call graph recommendation to automate
    hypothesis generation during debugRCA's Isolate phase.

    Args:
        target_file: Path to Python file to analyze

    Returns:
        List of hypothesis strings derived from call graph patterns
    """
    hypotheses = []
    dot_file = "trace_callgraph.dot"

    try:
        # Generate call graph using pyan
        subprocess.run(
            [
                "python",
                "-m",
                "pyan",
                target_file,
                "--uses",
                "--no-defines",
                "--colored",
                "--grouped",
                "--annotated",
                "--dot",
            ],
            capture_output=True,
            text=True,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        # Parse DOT file for patterns
        if Path(dot_file).exists():
            hypotheses = _extract_hypotheses_from_dot(dot_file)

    except (subprocess.CalledProcessError, FileNotFoundError):
        # pyan not available - return empty
        pass

    return hypotheses


def _extract_hypotheses_from_dot(dot_file: str) -> list[str]:
    """Extract hypotheses from DOT call graph file."""
    hypotheses = []

    try:
        with open(dot_file) as f:
            content = f.read()

        # Pattern 1: Circular dependencies (bidirectional edges)
        edges = []
        for line in content.split("\n"):
            if "->" in line:
                parts = line.split("->")
                if len(parts) == 2:
                    src = parts[0].strip().strip('"').strip()
                    dst_part = parts[1].split("[")[0] if "[" in parts[1] else parts[1]
                    dst = dst_part.strip().strip('"').strip()
                    if src and dst:
                        edges.append((src, dst))

        # Check for bidirectional edges (circular deps)
        for src, dst in edges:
            if (dst, src) in edges:
                hypotheses.append(
                    f"RESOURCE: Circular dependency between {src} and {dst} "
                    f"- potential resource leak or initialization race condition"
                )

        # Pattern 2: Cross-module calls (integration boundaries)
        module_calls = set()
        for line in content.split("\n"):
            if "->" in line:
                parts = line.split("->")
                if len(parts) == 2:
                    src_module = parts[0].split(".")[0].strip().strip('"')
                    dst_part = parts[1].split("[")[0] if "[" in parts[1] else parts[1]
                    dst_module = dst_part.split(".")[0].strip().strip('"')
                    if src_module and dst_module and src_module != dst_module:
                        module_calls.add((src_module, dst_module))

        if module_calls:
            hypotheses.append(
                f"INTEGRATION: Cross-module dependencies detected - "
                f"{len(module_calls)} inter-module calls present - potential boundary failures"
            )

    except Exception:
        # Parsing failed
        pass

    return hypotheses


class EvidenceSaturationChecker:
    """Check if TRACE has sufficient evidence coverage.

    Integration: Uses debugRCA's evidence saturation detection
    to determine when TRACE has sufficient coverage.
    """

    def __init__(self, threshold: float = 0.75):
        """Initialize saturation checker.

        Args:
            threshold: Saturation threshold (0.0-1.0, default 0.75)
        """
        self.threshold = threshold

    def is_trace_complete(self, scenarios: list[TraceScenario]) -> bool:
        """Check if TRACE scenarios provide sufficient evidence coverage.

        Args:
            scenarios: List of TRACE scenarios with findings

        Returns:
            True if evidence saturation >= threshold
        """
        if not scenarios:
            return False

        # Collect all findings as evidence texts
        evidence_texts = []
        for scenario in scenarios:
            evidence_texts.extend(scenario.findings)

        if not evidence_texts:
            return False

        # Calculate saturation using Jaccard similarity
        saturation_score = self._calculate_jaccard_saturation(evidence_texts)

        return saturation_score >= self.threshold

    def _calculate_jaccard_saturation(self, evidence_texts: list[str]) -> float:
        """Calculate evidence saturation using Jaccard keyword overlap."""
        if len(evidence_texts) < 2:
            return 0.0

        # Extract unique keywords from all evidence
        all_keywords = set()
        evidence_keywords = []

        for text in evidence_texts:
            keywords = set(word.lower() for word in text.split() if len(word) >= 4)
            evidence_keywords.append(keywords)
            all_keywords.update(keywords)

        if not all_keywords:
            return 0.0

        # Calculate average Jaccard similarity between evidence pairs
        similarities = []
        for i in range(len(evidence_keywords)):
            for j in range(i + 1, len(evidence_keywords)):
                intersection = evidence_keywords[i] & evidence_keywords[j]
                union = evidence_keywords[i] | evidence_keywords[j]
                if union:
                    jaccard = len(intersection) / len(union)
                    similarities.append(jaccard)

        if not similarities:
            return 0.0

        avg_similarity = sum(similarities) / len(similarities)
        saturation = min(1.0, avg_similarity * 2.0)

        return saturation


class ACHScenarioGenerator:
    """Generate TRACE scenarios using Analysis of Competing Hypotheses (ACH).

    Integration: Uses debugRCA's ACH framework to generate comprehensive
    TRACE scenarios covering all hypothesis categories.
    """

    # ACH categories from debugRCA methodology
    ACH_CATEGORIES = [
        "Logic",  # Control flow, algorithm errors, logic bugs
        "Data",  # Data corruption, type mismatches, format issues
        "State",  # State machine errors, lifecycle issues, stale state
        "Integration",  # API mismatches, protocol errors, boundary failures
        "Resource",  # Memory leaks, resource exhaustion, race conditions
        "Environment",  # Configuration errors, dependency issues, platform-specific
    ]

    def generate_ach_scenarios(
        self, target_path: Path, content: str, domain: str = "code"
    ) -> list[TraceScenario]:
        """Generate comprehensive TRACE scenarios from ACH categories.

        Args:
            target_path: Path to target file
            content: Content of target file
            domain: Domain type (code, skill, workflow, document)

        Returns:
            List of TraceScenario objects covering all ACH categories
        """
        scenarios = []

        for category in self.ACH_CATEGORIES:
            scenario = self._create_scenario_for_category(category, target_path, content, domain)
            if scenario:
                scenarios.append(scenario)

        return scenarios

    def _create_scenario_for_category(
        self, category: str, target_path: Path, content: str, domain: str
    ) -> Optional[TraceScenario]:
        """Create a TRACE scenario for a specific ACH category."""
        scenario_templates = {
            "Logic": {
                "name": "Logic Error Path",
                "description": "Trace through control flow and algorithm logic",
                "focus": "if/else branches, loops, return statements, error conditions",
            },
            "Data": {
                "name": "Data Corruption Path",
                "description": "Trace data transformation and validation",
                "focus": "type conversions, data parsing, validation checks",
            },
            "State": {
                "name": "State Transition Path",
                "description": "Trace state machine and lifecycle changes",
                "focus": "state changes, lifecycle events, stale data",
            },
            "Integration": {
                "name": "Integration Boundary Path",
                "description": "Trace cross-module calls and API boundaries",
                "focus": "function calls, API requests, module boundaries",
            },
            "Resource": {
                "name": "Resource Management Path",
                "description": "Trace resource acquisition and release",
                "focus": "file handles, locks, connections, memory",
            },
            "Environment": {
                "name": "Environment Configuration Path",
                "description": "Trace environment-specific behavior",
                "focus": "config loading, environment variables, dependencies",
            },
        }

        if category not in scenario_templates:
            return None

        template = scenario_templates[category]

        # Check if category is relevant to content
        if not self._is_category_relevant(category, content, domain):
            return None

        return TraceScenario(
            name=template["name"], description=template["description"], state_table=[], findings=[]
        )

    def _is_category_relevant(self, category: str, content: str, domain: str) -> bool:
        """Check if an ACH category is relevant to the target content."""
        category_keywords = {
            "Logic": ["if ", "else", "for ", "while ", "return", "raise", "except"],
            "Data": ["parse", "validate", "convert", "transform", "encode", "decode"],
            "State": ["state", "status", "phase", "stage", "lifecycle", "mode"],
            "Integration": ["import", "from ", "call", "request", "api", "endpoint"],
            "Resource": ["open", "close", "lock", "connect", "acquire", "release", "file"],
            "Environment": ["config", "env", "setting", "option", "parameter"],
        }

        if category not in category_keywords:
            return True

        keywords = category_keywords[category]
        content_lower = content.lower()

        return any(keyword.lower() in content_lower for keyword in keywords)


class DifferentialTracer(Tracer):
    """Compare TRACE results between two versions for differential debugging.

    Integration: Applies debugRCA's differential debugging framework
    to TRACE analysis, enabling comparison between working and broken versions.
    """

    def __init__(self, target_path: Path, working_version: str, broken_version: str):
        """Initialize differential tracer.

        Args:
            target_path: Path to file to trace
            working_version: Git ref for working version (commit hash, branch, tag)
            broken_version: Git ref for broken version
        """
        # Will initialize parent class after git operations
        self.target_path = target_path
        self.working_version = working_version
        self.broken_version = broken_version
        self.working_report = None
        self.broken_report = None

    def compare_traces(self) -> dict[str, Any]:
        """Compare TRACE results between working and broken versions.

        Returns:
            Dictionary with new_issues, fixed_issues, and root_cause_candidates
        """
        # Get current git commit
        original_commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()

        # Import CodeTracer adapter
        from .adapters.code_tracer import CodeTracer

        # TRACE working version
        subprocess.run(["git", "checkout", self.working_version], capture_output=True, check=True)
        working_tracer = CodeTracer(self.target_path)
        working_tracer.trace()
        working_data = working_tracer.to_dict()

        # TRACE broken version
        subprocess.run(["git", "checkout", self.broken_version], capture_output=True, check=True)
        broken_tracer = CodeTracer(self.target_path)
        broken_tracer.trace()
        broken_data = broken_tracer.to_dict()

        # Restore original commit
        subprocess.run(["git", "checkout", original_commit], capture_output=True, check=True)

        # Extract issues
        working_issues = set(f"{i['category']}: {i['problem']}" for i in working_data["issues"])
        broken_issues = set(f"{i['category']}: {i['problem']}" for i in broken_data["issues"])

        # Identify differences
        new_issues = broken_issues - working_issues
        fixed_issues = working_issues - broken_issues

        # Generate root cause candidates from new issues
        root_cause_candidates = self._analyze_new_issues(new_issues, broken_data["issues"])

        return {
            "working_version": self.working_version,
            "broken_version": self.broken_version,
            "new_issues": list(new_issues),
            "fixed_issues": list(fixed_issues),
            "root_cause_candidates": root_cause_candidates,
            "working_issue_count": len(working_issues),
            "broken_issue_count": len(broken_issues),
        }

    def _analyze_new_issues(
        self, new_issues: set[str], broken_report_issues: list[dict]
    ) -> list[dict]:
        """Analyze new issues to identify root cause candidates."""
        candidates = []

        # Find full issue data for new issues
        for issue_desc in new_issues:
            for issue_data in broken_report_issues:
                if f"{issue_data['category']}: {issue_data['problem']}" == issue_desc:
                    # Prioritize P0/P1 issues as root cause candidates
                    if issue_data["severity"] in ["P0", "P1"]:
                        candidates.append(
                            {
                                "issue": issue_desc,
                                "severity": issue_data["severity"],
                                "location": issue_data["location"],
                                "confidence": "high"
                                if issue_data["severity"] == "P0"
                                else "medium",
                            }
                        )

        return candidates
