#!/usr/bin/env python
"""
Objective risk calculator for recap's pre-handoff check.

Replaces subjective L×I scoring with deterministic tier×size×kind formula.

Formula: risk = (tier_weight × 0.5) + (size_weight × 0.3) + (kind_weight × 0.2)

Weights prioritize:
- Tier (50%): How central the code is to the system
- Size (30%): How much code is being changed
- Kind (20%): What type of change is being made
"""

from enum import Enum
from dataclasses import dataclass
from typing import Optional


# ============================================================================
# Enums with Weights
# ============================================================================

class Tier(Enum):
    """System tier - how central the code is to the system."""
    CORE = {"name": "core", "weight": 1.0}        # Central architecture, critical paths
    HIGH = {"name": "high", "weight": 0.8}        # Important subsystems
    MEDIUM = {"name": "medium", "weight": 0.6}    # Standard features
    LOW = {"name": "low", "weight": 0.4}         # Peripheral features
    UTILITY = {"name": "utility", "weight": 0.2}  # Helper code, tools


class Size(Enum):
    """Change size - how much code is being modified."""
    LARGE = {"name": "large", "weight": 1.0}      # Multi-file, extensive changes
    MEDIUM = {"name": "medium", "weight": 0.6}    # Single file, moderate changes
    SMALL = {"name": "small", "weight": 0.3}     # Function-level changes
    TINY = {"name": "tiny", "weight": 0.1}       # Minor tweaks, adjustments


class Kind(Enum):
    """Change kind - what type of change is being made."""
    REFACTOR = {"name": "refactor", "weight": 1.0}  # Restructuring existing code
    FEATURE = {"name": "feature", "weight": 0.8}     # Adding new functionality
    BUGFIX = {"name": "bugfix", "weight": 0.6}      # Fixing bugs
    CONFIG = {"name": "config", "weight": 0.3}      # Configuration changes
    DOCS = {"name": "docs", "weight": 0.1}          # Documentation only


# ============================================================================
# Constants
# ============================================================================

# Weight distribution for risk formula
TIER_WEIGHT_PERCENT = 0.5
SIZE_WEIGHT_PERCENT = 0.3
KIND_WEIGHT_PERCENT = 0.2

# Thresholds for risk level classification
THRESHOLD_CRITICAL = 0.8
THRESHOLD_HIGH = 0.7
THRESHOLD_MEDIUM = 0.5
THRESHOLD_LOW = 0.0


# ============================================================================
# Core Functions
# ============================================================================

def calculate_objective_risk(
    tier: Optional[Tier] = None,
    size: Optional[Size] = None,
    kind: Optional[Kind] = None
) -> float:
    """
    Calculate objective risk score using tier×size×kind formula.

    Formula: risk = (tier_weight × 0.5) + (size_weight × 0.3) + (kind_weight × 0.2)

    Args:
        tier: System tier (defaults to UTILITY if None)
        size: Change size (defaults to TINY if None)
        kind: Change kind (defaults to DOCS if None)

    Returns:
        Risk score between 0.0 and 1.0

    Examples:
        >>> calculate_objective_risk(Tier.CORE, Size.LARGE, Kind.REFACTOR)
        1.0
        >>> calculate_objective_risk(Tier.UTILITY, Size.TINY, Kind.DOCS)
        0.15
    """
    # Default to lowest weight if not provided
    tier = tier or Tier.UTILITY
    size = size or Size.TINY
    kind = kind or Kind.DOCS

    # Extract weights
    tier_weight = tier.value["weight"]
    size_weight = size.value["weight"]
    kind_weight = kind.value["weight"]

    # Calculate weighted risk score
    risk = (
        (tier_weight * TIER_WEIGHT_PERCENT) +
        (size_weight * SIZE_WEIGHT_PERCENT) +
        (kind_weight * KIND_WEIGHT_PERCENT)
    )

    return round(risk, 2)


def map_threshold(risk_score: float) -> str:
    """
    Map risk score to threshold level.

    Thresholds:
    - CRITICAL: >= 0.8
    - HIGH: >= 0.7
    - MEDIUM: >= 0.5
    - LOW: < 0.5

    Args:
        risk_score: Risk score between 0.0 and 1.0

    Returns:
        Threshold level as string

    Examples:
        >>> map_threshold(0.85)
        'CRITICAL'
        >>> map_threshold(0.75)
        'HIGH'
        >>> map_threshold(0.5)
        'MEDIUM'
        >>> map_threshold(0.3)
        'LOW'
    """
    if risk_score >= THRESHOLD_CRITICAL:
        return "CRITICAL"
    elif risk_score >= THRESHOLD_HIGH:
        return "HIGH"
    elif risk_score >= THRESHOLD_MEDIUM:
        return "MEDIUM"
    else:
        return "LOW"


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class RiskAssessment:
    """Complete risk assessment result."""
    score: float              # 0.0-1.0 risk score
    level: str                # CRITICAL, HIGH, MEDIUM, LOW
    tier: Tier                # System tier used
    size: Size                # Change size used
    kind: Kind                # Change kind used

    def __str__(self) -> str:
        """String representation of risk assessment."""
        return (f"Risk: {self.score:.2f} ({self.level}) - "
                f"{self.tier.value['name']} tier, "
                f"{self.size.value['name']} size, "
                f"{self.kind.value['name']} kind")


def assess_risk(
    tier: Optional[Tier] = None,
    size: Optional[Size] = None,
    kind: Optional[Kind] = None
) -> RiskAssessment:
    """
    Perform complete risk assessment.

    Args:
        tier: System tier (defaults to UTILITY if None)
        size: Change size (defaults to TINY if None)
        kind: Change kind (defaults to DOCS if None)

    Returns:
        RiskAssessment dataclass with complete assessment
    """
    # Default to lowest weight if not provided
    tier = tier or Tier.UTILITY
    size = size or Size.TINY
    kind = kind or Kind.DOCS

    # Calculate risk score
    score = calculate_objective_risk(tier, size, kind)

    # Map to threshold level
    level = map_threshold(score)

    return RiskAssessment(
        score=score,
        level=level,
        tier=tier,
        size=size,
        kind=kind
    )


# ============================================================================
# CLI Integration
# ============================================================================

def parse_tier(tier_str: str) -> Tier:
    """Parse tier from string input."""
    tier_map = {
        "core": Tier.CORE,
        "high": Tier.HIGH,
        "medium": Tier.MEDIUM,
        "low": Tier.LOW,
        "utility": Tier.UTILITY
    }
    return tier_map.get(tier_str.lower(), Tier.UTILITY)


def parse_size(size_str: str) -> Size:
    """Parse size from string input."""
    size_map = {
        "large": Size.LARGE,
        "medium": Size.MEDIUM,
        "small": Size.SMALL,
        "tiny": Size.TINY
    }
    return size_map.get(size_str.lower(), Size.TINY)


def parse_kind(kind_str: str) -> Kind:
    """Parse kind from string input."""
    kind_map = {
        "refactor": Kind.REFACTOR,
        "feature": Kind.FEATURE,
        "bugfix": Kind.BUGFIX,
        "config": Kind.CONFIG,
        "docs": Kind.DOCS
    }
    return kind_map.get(kind_str.lower(), Kind.DOCS)
