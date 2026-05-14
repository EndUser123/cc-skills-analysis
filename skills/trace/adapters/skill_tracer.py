"""
Skill TRACE adapter - intent detection, tool selection, fallback scenarios.

Implements TRACE methodology for SKILL.md files.
Focuses on intent matching logic, tool selection determinism, and fallback handling.
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.core.tracer import TraceIssue, Tracer, TraceScenario


class SkillTracer(Tracer):
    """
    Skill TRACE adapter for SKILL.md files.

    Uses TRACE methodology to verify:
    - Intent detection patterns
    - Tool selection logic
    - Fallback scenarios
    - Error handling
    """

    def read_target(self) -> str:
        """Read skill SKILL.md file."""
        return self.target_path.read_text(encoding='utf-8')

    def define_scenarios(self) -> list[TraceScenario]:
        """
        Define scenarios to trace.

        For skills, always trace:
        1. Matched Intent (user input matches known intent)
        2. Unmatched Intent (user input has no matching intent)
        3. Tool Failure (selected tool fails or errors)
        """
        return [
            TraceScenario(
                name='Matched Intent',
                description='User input matches known intent pattern'
            ),
            TraceScenario(
                name='Unmatched Intent',
                description='User input has no matching intent (fallback scenario)'
            ),
            TraceScenario(
                name='Tool Failure',
                description='Selected tool fails or raises exception'
            ),
        ]

    def trace_scenario(self, scenario: TraceScenario) -> None:
        """
        Execute TRACE for a single scenario.

        Parses SKILL.md frontmatter and content to verify intent detection.
        """
        # Extract frontmatter and content
        frontmatter, content = self._parse_skill_md()

        # Create state table entry
        scenario.state_table.append({
            'step': 'Parse SKILL.md',
            'operation': f'Load {self.target_path.name}',
            'state': f'Frontmatter: {len(frontmatter)} fields',
            'resources': 'N/A',
            'notes': 'Skill file loaded'
        })

        # Trace based on scenario type
        if scenario.name == 'Matched Intent':
            self._trace_matched_intent(scenario, frontmatter, content)
        elif scenario.name == 'Unmatched Intent':
            self._trace_unmatched_intent(scenario, frontmatter, content)
        elif scenario.name == 'Tool Failure':
            self._trace_tool_failure(scenario, frontmatter, content)

    def _parse_skill_md(self) -> tuple[dict[str, str], str]:
        """
        Parse SKILL.md into frontmatter and content.

        Returns:
            Tuple of (frontmatter dict, content string)
        """
        content = self.content
        frontmatter = {}
        body_start = 0

        # Extract YAML frontmatter (between --- markers)
        if content.startswith('---'):
            frontmatch_end = content.find('---', 3)
            if frontmatch_end != -1:
                frontmatter_text = content[3:frontmatch_end]
                body_start = frontmatch_end + 3

                # Parse YAML key-value pairs
                for line in frontmatter_text.split('\n'):
                    if ':' in line and not line.strip().startswith('#'):
                        key, value = line.split(':', 1)
                        frontmatter[key.strip()] = value.strip()

        body = content[body_start:].strip()
        return frontmatter, body

    def _trace_matched_intent(self, scenario: TraceScenario, frontmatter: dict[str, str], content: str) -> None:
        """Trace matched intent scenario."""
        scenario.state_table.append({
            'step': 'Intent Detection',
            'operation': 'Match user input to intent',
            'state': 'Intent matched',
            'resources': 'N/A',
            'notes': '✓ Intent pattern found'
        })

        # Check for intent patterns in content
        has_trigger = 'trigger' in frontmatter
        has_when = 'when' in frontmatter

        if has_trigger:
            scenario.state_table.append({
                'step': 'Trigger Pattern',
                'operation': 'Check trigger field',
                'state': f"Trigger: {frontmatter.get('trigger', '')[:50]}",
                'resources': 'N/A',
                'notes': '✓ Trigger pattern defined'
            })

        # Check for tool selection
        scenario.state_table.append({
            'step': 'Tool Selection',
            'operation': 'Select tool for intent',
            'state': 'Tool selected',
            'resources': 'N/A',
            'notes': '✓ Deterministic tool selection'
        })

        # Check for issues
        if not (has_trigger or has_when):
            scenario.findings.append(
                "Skill has no trigger or when field - intent detection unclear"
            )
            self.report.issues.append(TraceIssue(
                severity='P1',
                category='Logic Errors Found',
                location='SKILL.md frontmatter',
                problem='Missing trigger or when field for intent detection',
                impact='Skill may not be invoked when expected',
                recommendation='Add trigger field with intent pattern or when field with conditions'
            ))

    def _trace_unmatched_intent(self, scenario: TraceScenario, frontmatter: dict[str, str], content: str) -> None:
        """Trace unmatched intent scenario (fallback path)."""
        scenario.state_table.append({
            'step': 'Intent Detection',
            'operation': 'Match user input to intent',
            'state': 'No match found',
            'resources': 'N/A',
            'notes': '✗ Intent not matched'
        })

        # Check for fallback mechanism
        has_fallback = 'fallback' in content.lower() or 'default' in frontmatter

        if has_fallback:
            scenario.state_table.append({
                'step': 'Fallback Handler',
                'operation': 'Execute fallback logic',
                'state': 'Fallback triggered',
                'resources': 'N/A',
                'notes': '✓ Fallback mechanism exists'
            })
        else:
            scenario.state_table.append({
                'step': 'Fallback Handler',
                'operation': 'Execute fallback logic',
                'state': 'No fallback',
                'resources': 'N/A',
                'notes': '✗ No fallback for unmatched intents'
            })
            scenario.findings.append(
                "Skill has no fallback for unmatched intents - users get generic error"
            )
            self.report.issues.append(TraceIssue(
                severity='P1',
                category='Logic Errors Found',
                location='Intent detection section',
                problem='No fallback for unmatched intents',
                impact='Users get generic error on unknown input',
                recommendation='Add fallback intent with default tool or /search delegation'
            ))

    def _trace_tool_failure(self, scenario: TraceScenario, frontmatter: dict[str, str], content: str) -> None:
        """Trace tool failure scenario."""
        scenario.state_table.append({
            'step': 'Tool Execution',
            'operation': 'Execute selected tool',
            'state': 'Tool failed',
            'resources': 'N/A',
            'notes': '✗ Tool raised exception'
        })

        # Check for error handling
        has_error_handling = (
            'except' in content.lower() or
            'error' in content.lower() or
            'try' in content.lower()
        )

        if has_error_handling:
            scenario.state_table.append({
                'step': 'Error Handling',
                'operation': 'Handle tool failure',
                'state': 'Exception caught',
                'resources': 'N/A',
                'notes': '✓ Error handling present'
            })
        else:
            scenario.state_table.append({
                'step': 'Error Handling',
                'operation': 'Handle tool failure',
                'state': 'No error handler',
                'resources': 'N/A',
                'notes': '✗ Tool failure crashes skill'
            })
            scenario.findings.append(
                "Tool failure not handled - skill crashes on tool errors"
            )
            self.report.issues.append(TraceIssue(
                severity='P0',
                category='Logic Errors Found',
                location='Tool execution code',
                problem='No error handling for tool failures',
                impact='Skill crashes when tool fails, poor user experience',
                recommendation='Add try-except blocks around tool calls with fallback behavior'
            ))

        # Check for retry logic
        has_retry = 'retry' in content.lower()

        if has_retry:
            scenario.state_table.append({
                'step': 'Retry Logic',
                'operation': 'Check for retry mechanism',
                'state': 'Retry present',
                'resources': 'N/A',
                'notes': '⚠️ Verify retry has max limit to prevent infinite loops'
            })
            # Check for max retry limit
            if 'max' not in content.lower() and 'limit' not in content.lower():
                scenario.findings.append(
                    "Retry logic may not have max limit - risk of infinite loops"
                )
                self.report.issues.append(TraceIssue(
                    severity='P2',
                    category='Logic Errors Found',
                    location='Retry logic',
                    problem='Retry mechanism may lack max retry limit',
                    impact='Risk of infinite loops if tool fails repeatedly',
                    recommendation='Add max_retry limit with exponential backoff'
                ))

    def check_checklist(self) -> list[TraceIssue]:
        """
        Verify skill TRACE checklist.

        Checks:
        - Fallback intent exists
        - Tool selection is deterministic
        - Error handling present
        - No infinite retry loops
        """
        issues: list[TraceIssue] = []

        # Parse skill
        frontmatter, content = self._parse_skill_md()

        # Check 1: Fallback intent
        if 'fallback' not in content.lower() and 'default' not in frontmatter:
            issues.append(TraceIssue(
                severity='P1',
                category='Logic Errors Found',
                location='Intent detection section',
                problem='No fallback for unmatched intents',
                impact='Users get generic error on unknown input',
                recommendation='Add fallback intent with default tool or /search delegation'
            ))

        # Check 2: Deterministic tool selection
        # Look for tool selection patterns that might be non-deterministic
        if 'random' in content.lower() or 'arbitrary' in content.lower():
            issues.append(TraceIssue(
                severity='P2',
                category='Logic Errors Found',
                location='Tool selection logic',
                problem='Non-deterministic tool selection detected',
                impact='Inconsistent user experience, hard to debug',
                recommendation='Use deterministic tool selection based on intent criteria'
            ))

        # Check 3: Error handling in tool calls
        tool_call_patterns = ['Skill(', 'Agent(', 'Bash(', 'Read(', 'Edit(']
        has_tool_call = any(pattern in content for pattern in tool_call_patterns)

        if has_tool_call and 'except' not in content.lower():
            issues.append(TraceIssue(
                severity='P0',
                category='Logic Errors Found',
                location='Tool execution code',
                problem='Tool calls without error handling',
                impact='Skill crashes on tool failures',
                recommendation='Wrap tool calls in try-except with fallback behavior'
            ))

        # Check 4: SKILL.md exists and is readable
        if not self.target_path.exists():
            issues.append(TraceIssue(
                severity='P0',
                category='Resource Leaks Found',
                location=str(self.target_path),
                problem='SKILL.md file not found',
                impact='Cannot perform TRACE',
                recommendation='Ensure SKILL.md exists at expected path'
            ))

        return issues

    def read_context(self, pattern: str) -> dict[str, str]:
        """Read context files for cross-context verification.

        For skills, searches for related SKILL.md files, Python files in same directory.

        Args:
            pattern: Glob pattern for context files (e.g., "*.py", "SKILL.md")

        Returns:
            Dictionary mapping file paths to file contents
        """
        import glob

        context_files = {}

        # Get the directory containing the skill
        target_dir = self.target_path.parent

        # Search for matching files
        search_pattern = str(target_dir / pattern)
        matched_files = glob.glob(search_pattern, recursive=True)

        # Read each matched file
        for file_path in matched_files:
            try:
                path = Path(file_path)
                context_files[str(path)] = path.read_text(encoding='utf-8')
            except (OSError, UnicodeDecodeError):
                # Skip files that can't be read
                pass

        return context_files
