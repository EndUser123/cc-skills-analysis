"""
Enhanced TRACE methodology with debugRCA integrations.

This module extends the core TRACE methodology with:
1. Evidence saturation detection
2. CKS findings persistence
3. Red flag detection
4. ACH-based scenario generation
5. Timeline visualization for RCA
6. Call graph hypothesis generation
7. Differential TRACE capability
"""

import subprocess
import sys
import warnings
from pathlib import Path
from typing import Any, Optional

# Add debugRCA package to path
debugrca_src = str(Path("P:\\\\\\packages/debugRCA/src").resolve())
if debugrca_src not in sys.path:
    sys.path.insert(0, debugrca_src)

# Add CSF src to path for CKS integration
csf_src = str(Path("P:\\\\\\__csf/src").resolve())
if csf_src not in sys.path:
    sys.path.insert(0, csf_src)

# Import enhanced tracer base
from .tracer import TraceIssue, Tracer, TraceReport, TraceScenario


class EvidenceSaturationChecker:
    """Check if TRACE has sufficient evidence coverage using debugRCA's saturation detection."""

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

        # Calculate saturation using Jaccard similarity (fallback method)
        # This is a simplified version when debugRCA semantic search is unavailable
        saturation_score = self._calculate_jaccard_saturation(evidence_texts)

        return saturation_score >= self.threshold

    def _calculate_jaccard_saturation(self, evidence_texts: list[str]) -> float:
        """Calculate evidence saturation using Jaccard keyword overlap.

        Args:
            evidence_texts: List of evidence strings

        Returns:
            Saturation score between 0.0 and 1.0
        """
        if len(evidence_texts) < 2:
            return 0.0

        # Extract unique keywords from all evidence
        all_keywords = set()
        evidence_keywords = []

        for text in evidence_texts:
            # Simple keyword extraction (words >= 4 chars)
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

        # Diminishing returns detection
        avg_similarity = sum(similarities) / len(similarities)
        saturation = min(1.0, avg_similarity * 2.0)  # Scale up for coverage

        return saturation


class RedFlagDetector:
    """Detect anti-debugging patterns in TRACE findings."""

    def validate_trace_quality(self, report: TraceReport) -> list[str]:
        """Check for anti-debugging patterns in TRACE findings.

        Args:
            report: TRACE report to validate

        Returns:
            List of red flag warnings (empty if no issues)
        """
        red_flags = []

        # Check 1: P0/P1 issues without line references
        for issue in report.issues:
            if issue.severity in ['P0', 'P1']:
                if not self._has_line_reference(issue.location):
                    red_flags.append(
                        f"P0/P1 issue without line reference: {issue.category} - {issue.problem}"
                    )

        # Check 2: Contradictory findings
        red_flags.extend(self._detect_contradictions(report.issues))

        # Check 3: Vague locations
        for issue in report.issues:
            if self._is_vague_location(issue.location):
                red_flags.append(
                    f"Vague location for {issue.severity} issue: {issue.location}"
                )

        # Check 4: Missing impact or recommendation
        for issue in report.issues:
            if not issue.impact or issue.impact.strip() == "":
                red_flags.append(
                    f"Missing impact for {issue.severity} issue: {issue.category}"
                )
            if not issue.recommendation or issue.recommendation.strip() == "":
                red_flags.append(
                    f"Missing recommendation for {issue.severity} issue: {issue.category}"
                )

        return red_flags

    def _has_line_reference(self, location: str) -> bool:
        """Check if location contains line number reference."""
        if not location:
            return False
        # Check for patterns like "line 42", "L:42", "42-45", etc.
        line_indicators = ['line', 'Line', 'L:', 'l:', ':', '-', ',']
        return any(indicator in location for indicator in line_indicators)

    def _is_vague_location(self, location: str) -> bool:
        """Check if location is too vague."""
        vague_patterns = [
            'function', 'method', 'class', 'module', 'file',
            'somewhere', 'unknown', 'various', 'multiple'
        ]
        location_lower = location.lower() if location else ""
        return (
            not location or
            len(location) < 5 or
            any(pattern in location_lower for pattern in vague_patterns)
        )

    def _detect_contradictions(self, issues: list[TraceIssue]) -> list[str]:
        """Detect contradictory findings."""
        contradictions = []

        # Check for contradictory severity on same category
        category_issues = {}
        for issue in issues:
            if issue.category not in category_issues:
                category_issues[issue.category] = []
            category_issues[issue.category].append(issue)

        for category, cat_issues in category_issues.items():
            if len(cat_issues) > 1:
                severities = [issue.severity for issue in cat_issues]
                # Check for both P0/P1 and P3 in same category
                has_critical = any(s in ['P0', 'P1'] for s in severities)
                has_minor = any(s in ['P2', 'P3'] for s in severities)

                if has_critical and has_minor:
                    contradictions.append(
                        f"Contradictory findings in {category}: "
                        f"both critical ({has_critical}) and minor ({has_minor}) issues"
                    )

        return contradictions


class ACHScenarioGenerator:
    """Generate TRACE scenarios using Analysis of Competing Hypotheses (ACH) framework."""

    # ACH categories from debugRCA methodology
    ACH_CATEGORIES = [
        "Logic",        # Control flow, algorithm errors, logic bugs
        "Data",         # Data corruption, type mismatches, format issues
        "State",        # State machine errors, lifecycle issues, stale state
        "Integration",  # API mismatches, protocol errors, boundary failures
        "Resource",     # Memory leaks, resource exhaustion, race conditions
        "Environment",  # Configuration errors, dependency issues, platform-specific
    ]

    def generate_ach_scenarios(
        self,
        target_path: Path,
        content: str,
        domain: str = "code"
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
            scenario = self._create_scenario_for_category(
                category, target_path, content, domain
            )
            if scenario:
                scenarios.append(scenario)

        return scenarios

    def _create_scenario_for_category(
        self,
        category: str,
        target_path: Path,
        content: str,
        domain: str
    ) -> Optional[TraceScenario]:
        """Create a TRACE scenario for a specific ACH category.

        Args:
            category: ACH category name
            target_path: Path to target file
            content: Content of target file
            domain: Domain type

        Returns:
            TraceScenario for this category or None if not applicable
        """
        # Define scenario templates for each category
        scenario_templates = {
            "Logic": {
                "name": "Logic Error Path",
                "description": "Trace through control flow and algorithm logic",
                "focus": "if/else branches, loops, return statements, error conditions"
            },
            "Data": {
                "name": "Data Corruption Path",
                "description": "Trace data transformation and validation",
                "focus": "type conversions, data parsing, validation checks"
            },
            "State": {
                "name": "State Transition Path",
                "description": "Trace state machine and lifecycle changes",
                "focus": "state changes, lifecycle events, stale data"
            },
            "Integration": {
                "name": "Integration Boundary Path",
                "description": "Trace cross-module calls and API boundaries",
                "focus": "function calls, API requests, module boundaries"
            },
            "Resource": {
                "name": "Resource Management Path",
                "description": "Trace resource acquisition and release",
                "focus": "file handles, locks, connections, memory"
            },
            "Environment": {
                "name": "Environment Configuration Path",
                "description": "Trace environment-specific behavior",
                "focus": "config loading, environment variables, dependencies"
            }
        }

        if category not in scenario_templates:
            return None

        template = scenario_templates[category]

        # Check if category is relevant to content
        if not self._is_category_relevant(category, content, domain):
            return None

        return TraceScenario(
            name=template["name"],
            description=template["description"],
            state_table=[],  # To be populated during tracing
            findings=[]
        )

    def _is_category_relevant(self, category: str, content: str, domain: str) -> bool:
        """Check if an ACH category is relevant to the target content."""
        # Define keyword patterns for each category
        category_keywords = {
            "Logic": ["if ", "else", "for ", "while ", "return", "raise", "except"],
            "Data": ["parse", "validate", "convert", "transform", "encode", "decode"],
            "State": ["state", "status", "phase", "stage", "lifecycle", "mode"],
            "Integration": ["import", "from ", "call", "request", "api", "endpoint"],
            "Resource": ["open", "close", "lock", "connect", "acquire", "release", "file"],
            "Environment": ["config", "env", "setting", "option", "parameter"]
        }

        if category not in category_keywords:
            return True  # Default to relevant

        keywords = category_keywords[category]
        content_lower = content.lower()

        # Check if any keyword appears in content
        return any(keyword.lower() in content_lower for keyword in keywords)


class TimelineVisualizer:
    """Generate Mermaid timeline visualizations for debugRCA incident reports."""

    @staticmethod
    def events_to_mermaid(events: list[dict[str, Any]]) -> str:
        """Convert incident timeline events to Mermaid diagram.

        Args:
            events: List of event dictionaries with 'timestamp', 'description', 'cause' keys

        Returns:
            Mermaid timeline diagram as string
        """
        if not events:
            return ""

        mermaid = ["%%{init: {'theme':'base', 'themeVariables': { 'primaryColor':'#01579b'}}}%%"]
        mermaid.append("timeline")
        mermaid.append(f"    title Incident Timeline: {events[0].get('title', 'Incident')}")

        # Group events by phase/time
        current_phase = None
        for i, event in enumerate(events):
            timestamp = event.get('timestamp', f'T{i+1}')
            description = event.get('description', 'Event')
            cause = event.get('cause', '')
            status = event.get('status', 'unknown')

            # Add status emoji
            if 'success' in status.lower():
                description = f"✓ {description}"
            elif 'error' in status.lower() or 'fail' in status.lower():
                description = f"✗ {description}"
            elif 'warning' in status.lower() or 'warn' in status.lower():
                description = f"⚠ {description}"

            mermaid.append(f"    {timestamp} : {description}")

            if cause:
                mermaid.append(f"              : {cause}")

        return "\n".join(mermaid)


class CallGraphHypothesisGenerator:
    """Generate hypotheses from call graph analysis for RCA."""

    def analyze_call_graph_for_hypotheses(self, target_file: str) -> list[str]:
        """Generate hypotheses from call graph analysis.

        Args:
            target_file: Path to Python file to analyze

        Returns:
            List of hypothesis strings derived from call graph patterns
        """
        hypotheses = []

        # Generate call graph using pyan
        dot_file = "trace_callgraph.dot"
        try:
            subprocess.run([
                'python', '-m', 'pyan', target_file,
                '--uses', '--no-defines', '--colored', '--grouped',
                '--annotated', '--dot'
            ], capture_output=True, text=True, check=True)

            # Parse DOT file for patterns
            if Path(dot_file).exists():
                hypotheses = self._extract_hypotheses_from_graph(dot_file)

        except (subprocess.CalledProcessError, FileNotFoundError):
            # pyan not available or failed - return empty
            pass

        return hypotheses

    def _extract_hypotheses_from_graph(self, dot_file: str) -> list[str]:
        """Extract hypotheses from DOT call graph file.

        Args:
            dot_file: Path to DOT file generated by pyan

        Returns:
            List of hypothesis strings
        """
        hypotheses = []

        try:
            with open(dot_file) as f:
                content = f.read()

            # Pattern 1: Circular dependencies
            # Look for bidirectional edges (A -> B and B -> A)
            if '->' in content:
                lines = content.split('\n')
                edges = []
                for line in lines:
                    if '->' in line:
                        parts = line.split('->')
                        if len(parts) == 2:
                            src = parts[0].strip().strip('"').strip()
                            dst = parts[1].split('[')[0].strip().strip('"').strip()
                            if src and dst:
                                edges.append((src, dst))

                # Check for bidirectional edges
                for src, dst in edges:
                    if (dst, src) in edges:
                        hypotheses.append(
                            f"RESOURCE: Circular dependency detected between {src} and {dst} "
                            f"- may cause resource leaks or initialization race conditions"
                        )

            # Pattern 2: Deep call stacks (look for chains)
            # Count depth by tracking longest path
            # (Simplified - just note if file has complex structure)

            # Pattern 3: Cross-module calls
            module_calls = set()
            for line in content.split('\n'):
                if '->' in line:
                    parts = line.split('->')
                    if len(parts) == 2:
                        src_module = parts[0].split('.')[0].strip().strip('"')
                        dst_module = parts[1].split('.')[0].split('[')[0].strip().strip('"')
                        if src_module and dst_module and src_module != dst_module:
                            module_calls.add((src_module, dst_module))

            if module_calls:
                hypotheses.append(
                    f"INTEGRATION: Cross-module dependencies detected: "
                    f"{len(module_calls)} inter-module calls - potential boundary failures"
                )

        except Exception:
            # Parsing failed - return empty
            pass

        return hypotheses


class CKSFindingsStorage:
    """Persist TRACE findings to CKS for cross-session pattern recognition."""

    def __init__(self):
        """Initialize CKS findings storage."""
        self._cks = None
        self._available = False

        # Try to import CKS
        try:
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", category=DeprecationWarning)
                from cks.unified import CKS
            self._cks = CKS
            self._available = True
        except ImportError:
            self._available = False

    def persist_trace_findings(self, report: TraceReport) -> int:
        """Store TRACE findings to CKS.

        Args:
            report: TRACE report to persist

        Returns:
            Number of findings successfully stored
        """
        if not self._available:
            return 0

        stored_count = 0

        try:
            cks = self._cks()

            for issue in report.issues:
                finding_type = self._map_category_to_finding_type(issue.category)
                severity = self._map_severity(issue.severity)
                line_number = self._extract_line_number(issue.location)

                # Store finding
                cks.store_finding(
                    finding_type=finding_type,
                    source="trace",
                    message=f"[{issue.severity}] {issue.location}: {issue.problem}",
                    file_path=str(report.target_path),
                    line_number=line_number,
                    severity=severity,
                    metadata={
                        "impact": issue.impact,
                        "recommendation": issue.recommendation,
                        "domain": report.domain,
                        "date": report.date.isoformat()
                    }
                )
                stored_count += 1

        except Exception as e:
            # CKS storage failed - log warning but don't fail
            print(f"Warning: CKS storage failed: {e}")

        return stored_count

    def _map_category_to_finding_type(self, category: str) -> str:
        """Map TRACE category to CKS finding type."""
        category_map = {
            "Logic Errors": "LOGIC",
            "Resource Leaks": "RESOURCE_LEAK",
            "Race Conditions": "RACE_CONDITION",
            "Inconsistencies": "INCONSISTENCY"
        }
        return category_map.get(category, "ISSUE")

    def _map_severity(self, trace_severity: str) -> str:
        """Map TRACE severity to CKS severity."""
        severity_map = {
            "P0": "critical",
            "P1": "high",
            "P2": "medium",
            "P3": "low"
        }
        return severity_map.get(trace_severity, "medium")

    def _extract_line_number(self, location: str) -> Optional[int]:
        """Extract line number from location string."""
        if not location:
            return None

        # Try to extract first number from location
        import re
        match = re.search(r'\d+', location)
        if match:
            return int(match.group())
        return None


class DifferentialTracer(Tracer):
    """Compare TRACE results between two versions for differential debugging."""

    def __init__(self, target_path: Path, working_version: str, broken_version: str):
        """Initialize differential tracer.

        Args:
            target_path: Path to file to trace
            working_version: Git ref for working version (commit hash, branch, tag)
            broken_version: Git ref for broken version
        """
        # Import CodeTracer adapter (will be created separately)
        from .adapters.code_tracer import CodeTracer

        # Initialize tracers for both versions
        self.working_tracer = CodeTracer(target_path)
        self.broken_tracer = CodeTracer(target_path)
        self.working_version = working_version
        self.broken_version = broken_version

    def compare_traces(self) -> dict[str, Any]:
        """Compare TRACE results between working and broken versions using git show.

        Returns:
            Dictionary with new_issues, fixed_issues, and root_cause_candidates

        Safety: Uses git show instead of git checkout - does not modify working directory
        """
        import subprocess
        import tempfile

        # Read file content from working version using git show
        working_content = subprocess.run(
            ['git', 'show', f'{self.working_version}:{self.working_tracer.target_path}'],
            capture_output=True, text=True, check=True
        ).stdout

        # Read file content from broken version using git show
        broken_content = subprocess.run(
            ['git', 'show', f'{self.broken_version}:{self.broken_tracer.target_path}'],
            capture_output=True, text=True, check=True
        ).stdout

        # Create temporary files for TRACE analysis (non-destructive)
        with tempfile.TemporaryDirectory() as tmpdir:
            # Write working version to temp file
            working_temp = Path(tmpdir) / self.working_tracer.target_path.name
            working_temp.write_text(working_content, encoding='utf-8')

            # Write broken version to temp file
            broken_temp = Path(tmpdir) / self.broken_tracer.target_path.name
            broken_temp.write_text(broken_content, encoding='utf-8')

            # Create tracers for temp files
            from .adapters.code_tracer import CodeTracer
            working_tracer = CodeTracer(working_temp)
            broken_tracer = CodeTracer(broken_temp)

            # Execute TRACE on both versions
            working_report_data = working_tracer.to_dict()
            broken_report_data = broken_tracer.to_dict()

        # Extract issues
        working_issues = set(
            f"{i['category']}: {i['problem']}"
            for i in working_report_data['issues']
        )
        broken_issues = set(
            f"{i['category']}: {i['problem']}"
            for i in broken_report_data['issues']
        )

        # Identify differences
        new_issues = broken_issues - working_issues
        fixed_issues = working_issues - broken_issues

        # Generate root cause candidates from new issues
        root_cause_candidates = self._analyze_new_issues(
            new_issues,
            broken_report_data['issues']
        )

        return {
            "working_version": self.working_version,
            "broken_version": self.broken_version,
            "new_issues": list(new_issues),
            "fixed_issues": list(fixed_issues),
            "root_cause_candidates": root_cause_candidates,
            "working_issue_count": len(working_issues),
            "broken_issue_count": len(broken_issues)
        }

    def _analyze_new_issues(
        self,
        new_issues: set[str],
        broken_report_issues: list[dict]
    ) -> list[dict]:
        """Analyze new issues to identify root cause candidates.

        Args:
            new_issues: Set of new issue descriptions
            broken_report_issues: Full issue data from broken version

        Returns:
            List of potential root causes with evidence
        """
        candidates = []

        # Find full issue data for new issues
        for issue_desc in new_issues:
            for issue_data in broken_report_issues:
                if f"{issue_data['category']}: {issue_data['problem']}" == issue_desc:
                    # Prioritize P0/P1 issues as root cause candidates
                    if issue_data['severity'] in ['P0', 'P1']:
                        candidates.append({
                            "issue": issue_desc,
                            "severity": issue_data['severity'],
                            "location": issue_data['location'],
                            "confidence": "high" if issue_data['severity'] == 'P0' else "medium"
                        })

        return candidates
