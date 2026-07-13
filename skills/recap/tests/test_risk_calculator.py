#!/usr/bin/env python
"""
Tests for recap's objective risk calculator module.

Tests the tier×size×kind formula for objective risk assessment.
Run with: pytest tests/test_risk_calculator.py -v
"""

import pytest
from enum import Enum


class TestRiskCalculatorEnums:
    """Tests that Tier, Size, Kind enums are defined correctly."""

    def test_tier_enum_exists(self):
        """Test that Tier enum exists with correct values."""
        from recap.risk_calculator import Tier

        assert hasattr(Tier, 'CORE')
        assert hasattr(Tier, 'HIGH')
        assert hasattr(Tier, 'MEDIUM')
        assert hasattr(Tier, 'LOW')
        assert hasattr(Tier, 'UTILITY')

        # Verify weights
        assert Tier.CORE.value['weight'] == 1.0
        assert Tier.HIGH.value['weight'] == 0.8
        assert Tier.MEDIUM.value['weight'] == 0.6
        assert Tier.LOW.value['weight'] == 0.4
        assert Tier.UTILITY.value['weight'] == 0.2

    def test_size_enum_exists(self):
        """Test that Size enum exists with correct values."""
        from recap.risk_calculator import Size

        assert hasattr(Size, 'LARGE')
        assert hasattr(Size, 'MEDIUM')
        assert hasattr(Size, 'SMALL')
        assert hasattr(Size, 'TINY')

        # Verify weights
        assert Size.LARGE.value['weight'] == 1.0
        assert Size.MEDIUM.value['weight'] == 0.6
        assert Size.SMALL.value['weight'] == 0.3
        assert Size.TINY.value['weight'] == 0.1

    def test_kind_enum_exists(self):
        """Test that Kind enum exists with correct values."""
        from recap.risk_calculator import Kind

        assert hasattr(Kind, 'REFACTOR')
        assert hasattr(Kind, 'FEATURE')
        assert hasattr(Kind, 'BUGFIX')
        assert hasattr(Kind, 'CONFIG')
        assert hasattr(Kind, 'DOCS')

        # Verify weights
        assert Kind.REFACTOR.value['weight'] == 1.0
        assert Kind.FEATURE.value['weight'] == 0.8
        assert Kind.BUGFIX.value['weight'] == 0.6
        assert Kind.CONFIG.value['weight'] == 0.3
        assert Kind.DOCS.value['weight'] == 0.1


class TestCalculateObjectiveRisk:
    """Tests calculate_objective_risk() function."""

    def test_calculate_objective_risk_happy_path(self):
        """Test objective risk calculation with valid inputs."""
        from recap.risk_calculator import calculate_objective_risk, Tier, Size, Kind

        risk = calculate_objective_risk(
            tier=Tier.CORE,
            size=Size.LARGE,
            kind=Kind.REFACTOR
        )

        # Formula: (tier_weight × 0.5) + (size_weight × 0.3) + (kind_weight × 0.2)
        # (1.0 × 0.5) + (1.0 × 0.3) + (1.0 × 0.2) = 0.5 + 0.3 + 0.2 = 1.0
        assert risk == 1.0

    def test_calculate_objective_risk_low_risk(self):
        """Test objective risk calculation for low-risk scenario."""
        from recap.risk_calculator import calculate_objective_risk, Tier, Size, Kind

        risk = calculate_objective_risk(
            tier=Tier.UTILITY,
            size=Size.TINY,
            kind=Kind.DOCS
        )

        # (0.2 × 0.5) + (0.1 × 0.3) + (0.1 × 0.2) = 0.1 + 0.03 + 0.02 = 0.15
        assert risk == 0.15

    def test_calculate_objective_risk_medium_risk(self):
        """Test objective risk calculation for medium-risk scenario."""
        from recap.risk_calculator import calculate_objective_risk, Tier, Size, Kind

        risk = calculate_objective_risk(
            tier=Tier.MEDIUM,
            size=Size.MEDIUM,
            kind=Kind.FEATURE
        )

        # (0.6 × 0.5) + (0.6 × 0.3) + (0.8 × 0.2) = 0.3 + 0.18 + 0.16 = 0.64
        assert risk == 0.64

    def test_calculate_objective_risk_handles_missing_fields(self):
        """Test that missing fields defaults to lowest weight."""
        from recap.risk_calculator import calculate_objective_risk

        # Missing all fields should use lowest weight
        risk = calculate_objective_risk()
        # (0.2 × 0.5) + (0.1 × 0.3) + (0.1 × 0.2) = 0.15
        assert risk == 0.15


class TestMapThreshold:
    """Tests map_threshold() function."""

    def test_map_threshold_critical(self):
        """Test threshold mapping for critical risk."""
        from recap.risk_calculator import map_threshold

        level = map_threshold(0.85)
        assert level == "CRITICAL"

    def test_map_threshold_high(self):
        """Test threshold mapping for high risk."""
        from recap.risk_calculator import map_threshold

        level = map_threshold(0.75)
        assert level == "HIGH"

    def test_map_threshold_medium(self):
        """Test threshold mapping for medium risk."""
        from recap.risk_calculator import map_threshold

        level = map_threshold(0.5)
        assert level == "MEDIUM"

    def test_map_threshold_low(self):
        """Test threshold mapping for low risk."""
        from recap.risk_calculator import map_threshold

        level = map_threshold(0.3)
        assert level == "LOW"

    def test_map_threshold_bounds(self):
        """Test threshold mapping at boundary values."""
        from recap.risk_calculator import map_threshold

        # Test exact boundaries
        assert map_threshold(0.8) == "CRITICAL"  # >= 0.8
        assert map_threshold(0.7) == "HIGH"     # >= 0.7
        assert map_threshold(0.5) == "MEDIUM"   # >= 0.5
        assert map_threshold(0.0) == "LOW"      # < 0.5


if __name__ == '__main__':
    import pytest
    import sys
    sys.path.insert(0, str(__file__).parent.parent / "scripts")
    sys.exit(pytest.main([__file__, '-v']))
