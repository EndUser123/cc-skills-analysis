"""
Core TRACE methodology - domain-agnostic trace-through verification.

Base package for TRACE functionality.
"""

from .tracer import TraceIssue, TraceReport, TraceScenario, Tracer

__all__ = [
    'TraceIssue',
    'TraceReport',
    'TraceScenario',
    'Tracer',
]
