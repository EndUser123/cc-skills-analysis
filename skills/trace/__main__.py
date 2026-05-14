#!/usr/bin/env python
"""
TRACE - Manual Trace-Through Verification

Domain adapters for manual code/skill/workflow/document trace-through.
Catches logic errors that automated testing misses (60-80% detection rate).

Usage:
    python __main__.py "code:src/handoff.py"
    python __main__.py "skill:skill-development"
    python __main__.py "workflow:flows/feature.md"
    python __main__.py "document:CLAUDE.md"
    python __main__.py "src/handoff.py"  # Auto-detect domain
"""

import argparse
import os
import sys
from pathlib import Path

# Add hooks lib to path for quality_log import
_hooks_lib = Path("P:\\\\\\.claude/hooks/__lib")
if str(_hooks_lib) not in sys.path:
    sys.path.insert(0, str(_hooks_lib))

from adapters.code_tracer import CodeTracer
from adapters.skill_tracer import SkillTracer
from scripts.core.tracer import Tracer

DOMAIN_ADAPTERS = {
    "code": CodeTracer,
    "skill": SkillTracer,  # Implemented
    "workflow": None,  # Future extension point
    "document": None,  # Future extension point
}


def parse_target(target: str) -> tuple[str, str]:
    """
    Parse domain and target from invocation string.

    Args:
        target: Target string (e.g., "code:src/handoff.py" or "src/handoff.py")

    Returns:
        Tuple of (domain, target_path)
    """
    if ":" in target:
        # Explicit domain: "code:src/handoff.py"
        domain, target_path = target.split(":", 1)
        return domain, target_path

    # Auto-detect domain from target
    target_path = target
    target_lower = target.lower()

    if target_lower.endswith(".py"):
        return "code", target_path
    elif target_lower.endswith("skill.md") or "skills/" in target_lower:
        return "skill", target_path
    elif "flows/" in target_lower or target_lower.endswith("flow.md"):
        return "workflow", target_path
    else:
        return "document", target_path


def resolve_target_path(target: str, domain: str) -> Path:
    """
    Resolve target path relative to project root.

    Args:
        target: Target path string
        domain: Domain name

    Returns:
        Resolved Path object

    Raises:
        ValueError: If path contains invalid characters
        PermissionError: If path is not accessible
    """
    try:
        # Convert to Path and validate
        target_path = Path(target)

        # Validate path characters (Windows compatibility)
        if any(char in str(target_path) for char in ["<", ">", '"', "|", "?", "*"]):
            raise ValueError(f"Path contains invalid characters: {target}")

        # If relative, resolve from project root (configurable via environment)
        if not target_path.is_absolute():
            # P0: Make project root configurable (Recommendation #3)
            project_root = Path(os.getenv("TRACE_PROJECT_ROOT", "P:\\\\\\"))
            target_path = project_root / target_path

        # Resolve to absolute path (raises OSError if path is invalid)
        target_path = target_path.resolve()

        return target_path

    except (OSError, ValueError) as e:
        # P1: Enhanced error handling with user-friendly message (Recommendation #2)
        raise type(e)(
            f"Failed to resolve path '{target}': {e}\n"
            f"  Hint: Check the file path is correct and accessible.\n"
            f"  Current working directory: {Path.cwd()}\n"
            f"  Project root: {os.getenv('TRACE_PROJECT_ROOT', 'P:\\\\\\')}"
        ) from e


def main():
    """Main entry point for TRACE skill."""
    parser = argparse.ArgumentParser(
        description="Manual trace-through verification for code, skills, workflows, and documents"
    )
    parser.add_argument(
        "target", help='Target to trace (format: "domain:path" or just "path" for auto-detect)'
    )
    parser.add_argument("--template", type=int, help="Template number to use (code domain only)")
    parser.add_argument(
        "--full", action="store_true", help="Full TRACE review (all templates/checklists)"
    )
    parser.add_argument(
        "--output",
        choices=["text", "markdown", "json"],
        default="markdown",
        help="Output format (default: markdown)",
    )
    parser.add_argument(
        "--project-root", help="Project root directory (overrides TRACE_PROJECT_ROOT env var)"
    )

    args = parser.parse_args()

    # Parse domain and target
    domain, target_path = parse_target(args.target)

    # Validate domain
    if domain not in DOMAIN_ADAPTERS:
        print(f"Error: Unknown domain '{domain}'", file=sys.stderr)
        print(f"Supported domains: {', '.join(DOMAIN_ADAPTERS.keys())}", file=sys.stderr)
        print("  Hint: Use format 'domain:path' (e.g., 'code:src/handoff.py')", file=sys.stderr)
        sys.exit(1)

    # Check if domain adapter is implemented
    adapter_class = DOMAIN_ADAPTERS[domain]
    if adapter_class is None:
        print(f"Error: Domain '{domain}' is not yet implemented", file=sys.stderr)
        print("Implemented domains: code, skill")
        print("Future domains: workflow, document")
        sys.exit(1)

    # Override project root if specified via CLI (Recommendation #3)
    if args.project_root:
        os.environ["TRACE_PROJECT_ROOT"] = args.project_root

    # Resolve target path with enhanced error handling (Recommendation #2)
    try:
        resolved_path = resolve_target_path(target_path, domain)
    except (OSError, ValueError, PermissionError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    # Check if file exists (Recommendation #5 - enhanced error message)
    if not resolved_path.exists():
        print(f"Error: Target file not found: {resolved_path}", file=sys.stderr)
        print("  Suggestion: Check the file path is correct", file=sys.stderr)
        print(f"  Current working directory: {Path.cwd()}", file=sys.stderr)
        print(
            "  Supported file types: .py (code), SKILL.md (skill), .md (document)", file=sys.stderr
        )
        sys.exit(1)

    # Create tracer instance
    tracer: Tracer = adapter_class(
        target_path=resolved_path, template=args.template, full_review=args.full
    )

    # Run TRACE with proper resource cleanup (Recommendation #1)
    report = None
    try:
        report = tracer.trace()

        # Log to quality log
        try:
            from quality_log import log_quality_skill

            project_root = Path.cwd()
            log_quality_skill(
                skill_name="trace",
                result="completed",
                tier="manual-trace",
                project_root=project_root,
            )
        except ImportError:
            pass  # quality_log module not available
        except Exception:
            pass  # Quality logging is best-effort, never block

        # Output report
        if args.output == "markdown":
            print(report)
        elif args.output == "json":
            import json

            print(json.dumps(tracer.to_dict(), indent=2))
        else:
            print(report)

    except Exception as e:
        # P0: Resource leak - tracer may have opened files/resources
        # Recommendation: Add cleanup code here if tracer has cleanup method
        print(f"Error during TRACE: {e}", file=sys.stderr)
        print(f"  Target: {resolved_path}", file=sys.stderr)
        print(f"  Domain: {domain}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        sys.exit(1)
    finally:
        # P0: Ensure cleanup even if TRACE fails (Recommendation #1)
        # If tracer has resources that need cleanup, call it here
        if hasattr(tracer, "cleanup"):
            tracer.cleanup()


if __name__ == "__main__":
    main()
