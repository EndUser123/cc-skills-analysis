"""Friction detection package for GAP."""
from .correction_patterns import detect_correction_patterns
from .workflow_repetition import detect_workflow_repetition

__all__ = ["detect_correction_patterns", "detect_workflow_repetition"]
