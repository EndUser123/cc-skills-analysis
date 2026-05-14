"""
Code TRACE adapter - resource management, exception paths, race conditions.

Implements TRACE methodology for Python code files.
Focuses on file descriptors, locks, exception handling, and concurrency.
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.core.tracer import TraceIssue, Tracer, TraceScenario


class CodeTracer(Tracer):
    """
    Code TRACE adapter for Python files.

    Uses TRACE templates to verify:
    - File descriptor management
    - Lock cleanup (no race conditions)
    - Exception handling (no resource leaks)
    - TOCTOU race conditions
    - Logic correctness
    """

    def read_target(self) -> str:
        """Read Python source file."""
        return self.target_path.read_text(encoding='utf-8')

    def define_scenarios(self) -> list[TraceScenario]:
        """
        Define scenarios to trace.

        For code, always trace:
        1. Happy path (normal operation)
        2. Error path (exception handling)
        3. Edge case (timeout, empty input, boundary)
        """
        return [
            TraceScenario(
                name='Happy Path',
                description='Normal operation without errors'
            ),
            TraceScenario(
                name='Error Path',
                description='Exception is raised, verify cleanup'
            ),
            TraceScenario(
                name='Edge Case',
                description='Boundary condition (timeout, empty input, etc.)'
            ),
        ]

    def trace_scenario(self, scenario: TraceScenario) -> None:
        """
        Execute TRACE for a single scenario.

        This is a simplified implementation. In production, would:
        1. Parse Python AST
        2. Identify functions with resource management
        3. Create state table for each function
        4. Step through code line-by-line
        5. Track variable states and resources
        6. Document findings
        """
        # For now, create a placeholder state table
        scenario.state_table = [
            {
                'step': 'Read file',
                'operation': f'Load {self.target_path.name}',
                'state': 'File content loaded',
                'resources': 'N/A',
                'notes': f'{len(self.content)} lines read'
            },
        ]

        # Check for common patterns (simplified)
        self._check_file_descriptors(scenario)
        self._check_lock_management(scenario)
        self._check_exception_handling(scenario)

    def _check_file_descriptors(self, scenario: TraceScenario) -> None:
        """Check for file descriptor management issues."""
        # Look for common fd issues
        if 'os.open(' in self.content and 'fdopen(' in self.content:
            # Check if fd is reused after fdopen (common bug)
            lines = self.content.split('\n')
            for i, line in enumerate(lines, 1):
                if 'fdopen(' in line and i < len(lines) - 1:
                    # Check next few lines for fd reuse
                    next_lines = '\n'.join(lines[i:min(i+5, len(lines))])
                    if 'fd' in next_lines and 'except' in next_lines:
                        scenario.findings.append(
                            f"Line {i}: Possible fd reuse after fdopen() - "
                            f"fd consumed by fdopen(), cannot reuse in except block"
                        )
                        self.report.issues.append(TraceIssue(
                            severity='P0',
                            category='Resource Leaks Found',
                            location=f"Line {i}",
                            problem='File descriptor consumed by fdopen(), then reused in except block',
                            impact='OSError: Bad file descriptor crashes error handler',
                            recommendation='Create new temp file with new fd in except block (see Template 2)'
                        ))

    def _check_lock_management(self, scenario: TraceScenario) -> None:
        """Check for lock cleanup race conditions."""
        # Look for lock acquisition without tracking flag
        if 'os.open(' in self.content and '.lock' in self.content:
            # Check for lock_acquired flag
            if 'lock_acquired' not in self.content and 'acquired' not in self.content:
                scenario.findings.append(
                    "Lock acquisition without tracking flag - "
                    "finally block may delete another process's lock"
                )
                self.report.issues.append(TraceIssue(
                    severity='P0',
                    category='Race Conditions Found',
                    location='Lock management code',
                    problem='Finally block deletes lock even if acquisition failed',
                    impact='Race condition: two terminals both think they have the lock',
                    recommendation='Add lock_acquired flag, check before unlink (see Template 1)'
                ))

    def _check_exception_handling(self, scenario: TraceScenario) -> None:
        """Check for exception handling issues."""
        # Look for bare except
        if 'except:' in self.content or 'except\n' in self.content:
            # Find line numbers
            lines = self.content.split('\n')
            for i, line in enumerate(lines, 1):
                if 'except:' in line or line.strip() == 'except':
                    scenario.findings.append(
                        f"Line {i}: Bare except clause - catches KeyboardInterrupt and SystemExit"
                    )
                    self.report.issues.append(TraceIssue(
                        severity='P1',
                        category='Logic Errors Found',
                        location=f"Line {i}",
                        problem='Bare except catches all exceptions including KeyboardInterrupt',
                        impact='Cannot interrupt program with Ctrl+C',
                        recommendation='Catch specific exceptions (OSError, ValueError, etc.)'
                    ))

    def check_checklist(self) -> list[TraceIssue]:
        """
        Verify code TRACE checklist.

        Checks:
        - File descriptors opened → closed (all paths)
        - Locks acquired → released (even if acquisition fails)
        - Exception paths don't leak resources
        - No TOCTOU races
        - Cleanup in finally blocks
        """
        issues: list[TraceIssue] = []

        # Check for context manager usage (preferred pattern)
        if 'with open(' in self.content:
            # Good - using context managers
            pass
        elif 'open(' in self.content and 'with ' not in self.content:
            # Warning - not using context managers
            issues.append(TraceIssue(
                severity='P2',
                category='Code Quality',
                location='File I/O code',
                problem='File opened without context manager',
                impact='Resource leak if exception occurs before close()',
                recommendation='Use "with open()" or ensure close() in finally block'
            ))

        # Check for missing finally blocks
        if 'try:' in self.content and 'finally:' not in self.content:
            # Check if resources are acquired
            if any(keyword in self.content for keyword in ['os.open(', 'lock=', 'connect(', 'socket(']):
                issues.append(TraceIssue(
                    severity='P1',
                    category='Resource Leaks Found',
                    location='Exception handling code',
                    problem='Resources acquired but no finally block for cleanup',
                    impact='Resource leaks on exception',
                    recommendation='Add finally block or use context managers'
                ))

        return issues

    def read_context(self, pattern: str) -> dict[str, str]:
        """Read context files for cross-context verification.

        Args:
            pattern: Glob pattern for context files (e.g., "**/*registry*.py")

        Returns:
            Dictionary mapping file paths to file contents
        """
        import glob

        context_files = {}

        # Get the directory containing the target file
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
