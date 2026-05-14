#!/usr/bin/env python
"""Validate retro SKILL.md specifies required RNS output format elements.

Ensures future edits to retro SKILL.md don't accidentally remove:
- RNS output format section with domain grouping
- Domain emoji mapping table
- Gap coverage section (MAPPED/REJECTED/DEFERRED)
- "Do ALL" footer
- Carryover rule for prior retro actions
"""

from pathlib import Path

import pytest

SKILL_PATH = Path(__file__).resolve().parents[1] / "SKILL.md"


@pytest.fixture
def skill_content() -> str:
    assert SKILL_PATH.exists(), f"retro SKILL.md not found at {SKILL_PATH}"
    return SKILL_PATH.read_text(encoding="utf-8")


class TestRetroRNSFormat:
    """Validate retro SKILL.md contains required RNS format elements."""

    def test_has_rns_output_section(self, skill_content: str) -> None:
        assert "### RNS Output" in skill_content, "Missing RNS Output section header"

    def test_has_domain_emoji_table(self, skill_content: str) -> None:
        assert "### Domain Emoji Mapping" in skill_content, "Missing Domain Emoji Mapping section"
        # Verify key domains are present
        for domain in ["quality", "tests", "docs", "security"]:
            assert domain in skill_content.lower(), f"Missing domain: {domain}"

    def test_has_gap_coverage_section(self, skill_content: str) -> None:
        assert "GAP COVERAGE" in skill_content, "Missing GAP COVERAGE section"
        assert "MAPPED" in skill_content, "Missing MAPPED disposition"
        assert "REJECTED" in skill_content, "Missing REJECTED disposition"
        assert "DEFERRED" in skill_content, "Missing DEFERRED disposition"

    def test_has_do_all_footer(self, skill_content: str) -> None:
        assert "Do ALL" in skill_content, "Missing 'Do ALL' footer directive"

    def test_has_carryover_rule(self, skill_content: str) -> None:
        assert "carryover" in skill_content.lower(), "Missing carryover rule for prior retro actions"

    def test_has_score_axes(self, skill_content: str) -> None:
        assert "completeness" in skill_content.lower(), "Missing completeness score axis"
        assert "optimality" in skill_content.lower(), "Missing optimality score axis"
        assert "satisfaction" in skill_content.lower(), "Missing satisfaction score axis"

    def test_has_aggregation_rule(self, skill_content: str) -> None:
        assert "RNS Aggregation Rule" in skill_content, "Missing RNS Aggregation Rule section"
        assert "silently dropped" in skill_content.lower(), "Missing 'no silently dropped' rule"

    def test_has_workflow_steps_chaining(self, skill_content: str) -> None:
        for skill in ["recap", "gto", "friction", "pre-mortem", "rns"]:
            assert skill in skill_content.lower(), f"Missing chained skill: {skill}"
