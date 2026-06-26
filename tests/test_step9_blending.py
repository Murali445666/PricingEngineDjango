"""
Step 9: Multi-Methodology Blending tests.

Covers:
  - CLAIM-scope ADD blending: final = post_outlier + total_billed * pct/100
  - CLAIM-scope OVERRIDE blending: final = total_billed * pct/100
  - LINE-scope ADD blending: per-line blended_allowed_amount set + claim total re-summed
  - LINE-scope OVERRIDE blending: per-line replacement
  - primary_methodology filter: only matching lines blended
  - No blending rules: result unchanged
  - Expired / future blending rule: not applied
  - Priority ordering: highest priority rule wins for CLAIM scope
  - Stop-loss / outlier already applied → blending runs on top
  - Carve-out EXCLUDED lines never blended
  - Bulk pricing: config shared, per-claim cache isolation preserved
  - API serializer: blended_total_allowed + applied_blending_rule_ids exposed
"""
import sys
import os
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

import django

# Ensure Django settings are configured before any app imports.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
try:
    django.setup()
except RuntimeError:
    pass

from core.engine.types import (
    LineResult,
    ClaimPricingResult,
    PricingStatus,
    PricingTrace,
)
from core.engine.orchestrator import _apply_blending


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_line(allowed: float, methodology: str = "DRG", status=PricingStatus.SUCCESS) -> LineResult:
    return LineResult(
        status=status,
        allowed_amount=Decimal(str(allowed)),
        methodology=methodology,
        details="",
        contract_id="1",
        rule_id=1,
        trace=PricingTrace(),
    )


def _make_line_input(billed: float) -> MagicMock:
    li = MagicMock()
    li.billed_amount = Decimal(str(billed))
    return li


def _make_blending_rule(
    rule_id: int,
    blend_type: str,
    scope: str = "CLAIM",
    primary_methodology: str = "",
    secondary_methodology: str = "PERCENT_BILLED",
    blend_percentage: float = 10.0,
    priority: int = 0,
    start: date = date(2024, 1, 1),
    end: date = None,
) -> MagicMock:
    rule = MagicMock()
    rule.blending_rule_id = rule_id
    rule.blend_type = blend_type
    rule.scope = scope
    rule.primary_methodology = primary_methodology
    rule.secondary_methodology = secondary_methodology
    rule.blend_percentage = Decimal(str(blend_percentage))
    rule.priority = priority
    rule.effective_start_date = start
    rule.effective_end_date = end
    return rule


SERVICE_DATE = date(2025, 6, 1)


# ---------------------------------------------------------------------------
# CLAIM-scope blending
# ---------------------------------------------------------------------------

class TestClaimScopeBlending:

    def test_no_blending_rules_unchanged(self):
        """With empty blending_rules tuple, result is the post-outlier total unchanged."""
        lr = _make_line(500.0)
        blended, ids, status, traces = _apply_blending(
            Decimal("500.00"), Decimal("1000.00"), [lr], [_make_line_input(1000.0)], (), SERVICE_DATE
        )
        assert blended == Decimal("500.00")
        assert ids == []
        assert status is None
        assert traces == []

    def test_claim_add_blending(self):
        """ADD: blended = 500 + 1000 * 10% = 600."""
        lr = _make_line(500.0)
        rule = _make_blending_rule(1, "ADD", scope="CLAIM", blend_percentage=10.0)
        blended, ids, status, traces = _apply_blending(
            Decimal("500.00"), Decimal("1000.00"), [lr], [_make_line_input(1000.0)], (rule,), SERVICE_DATE
        )
        assert blended == Decimal("600.00")
        assert ids == [1]
        assert status == PricingStatus.BLENDING_APPLIED
        assert len(traces) == 1
        assert "BLENDING_APPLIED(ADD)" in traces[0]

    def test_claim_override_blending(self):
        """OVERRIDE: blended = 1000 * 25% = 250, regardless of post-outlier total."""
        lr = _make_line(500.0)
        rule = _make_blending_rule(2, "OVERRIDE", scope="CLAIM", blend_percentage=25.0)
        blended, ids, status, traces = _apply_blending(
            Decimal("500.00"), Decimal("1000.00"), [lr], [_make_line_input(1000.0)], (rule,), SERVICE_DATE
        )
        assert blended == Decimal("250.00")
        assert ids == [2]
        assert status == PricingStatus.BLENDING_APPLIED

    def test_claim_add_zero_percent(self):
        """ADD with 0%: blended total equals post-outlier total (no change)."""
        lr = _make_line(500.0)
        rule = _make_blending_rule(3, "ADD", blend_percentage=0.0)
        blended, ids, status, traces = _apply_blending(
            Decimal("500.00"), Decimal("1000.00"), [lr], [_make_line_input(1000.0)], (rule,), SERVICE_DATE
        )
        assert blended == Decimal("500.00")
        assert ids == [3]

    def test_claim_scope_first_rule_wins(self):
        """Multiple CLAIM rules: only highest-priority (first in tuple) applies."""
        r1 = _make_blending_rule(10, "ADD", priority=5, blend_percentage=10.0)
        r2 = _make_blending_rule(11, "ADD", priority=1, blend_percentage=50.0)
        lr = _make_line(500.0)
        blended, ids, status, traces = _apply_blending(
            Decimal("500.00"), Decimal("1000.00"), [lr], [_make_line_input(1000.0)],
            (r1, r2), SERVICE_DATE
        )
        assert blended == Decimal("600.00")
        assert ids == [10]

    def test_expired_rule_not_applied(self):
        """A rule with effective_end_date < service_date must be skipped."""
        rule = _make_blending_rule(20, "ADD", end=date(2024, 12, 31), blend_percentage=10.0)
        lr = _make_line(500.0)
        blended, ids, status, traces = _apply_blending(
            Decimal("500.00"), Decimal("1000.00"), [lr], [_make_line_input(1000.0)], (rule,), SERVICE_DATE
        )
        assert blended == Decimal("500.00")
        assert ids == []

    def test_future_rule_not_applied(self):
        """A rule with effective_start_date > service_date must be skipped."""
        rule = _make_blending_rule(21, "ADD", start=date(2026, 1, 1), blend_percentage=10.0)
        lr = _make_line(500.0)
        blended, ids, status, traces = _apply_blending(
            Decimal("500.00"), Decimal("1000.00"), [lr], [_make_line_input(1000.0)], (rule,), SERVICE_DATE
        )
        assert blended == Decimal("500.00")
        assert ids == []


# ---------------------------------------------------------------------------
# LINE-scope blending
# ---------------------------------------------------------------------------

class TestLineScopeBlending:

    def test_line_add_all_lines(self):
        """LINE ADD, no primary_methodology filter: all non-excluded lines blended."""
        lr1 = _make_line(400.0, methodology="DRG")
        lr2 = _make_line(100.0, methodology="RBRVS")
        li1 = _make_line_input(800.0)
        li2 = _make_line_input(200.0)
        rule = _make_blending_rule(30, "ADD", scope="LINE", primary_methodology="", blend_percentage=10.0)
        blended, ids, status, traces = _apply_blending(
            Decimal("500.00"), Decimal("1000.00"),
            [lr1, lr2], [li1, li2], (rule,), SERVICE_DATE
        )
        # lr1: 400 + 800*10% = 480; lr2: 100 + 200*10% = 120
        assert lr1.blended_allowed_amount == Decimal("480.00")
        assert lr2.blended_allowed_amount == Decimal("120.00")
        assert blended == Decimal("600.00")
        assert ids == [30]
        assert status == PricingStatus.BLENDING_APPLIED

    def test_line_override_all_lines(self):
        """LINE OVERRIDE, no filter: all non-excluded lines replaced with pct-of-billed."""
        lr1 = _make_line(400.0, methodology="DRG")
        lr2 = _make_line(100.0, methodology="RBRVS")
        li1 = _make_line_input(800.0)
        li2 = _make_line_input(200.0)
        rule = _make_blending_rule(31, "OVERRIDE", scope="LINE", primary_methodology="", blend_percentage=20.0)
        blended, ids, status, traces = _apply_blending(
            Decimal("500.00"), Decimal("1000.00"),
            [lr1, lr2], [li1, li2], (rule,), SERVICE_DATE
        )
        # lr1: 800*20% = 160; lr2: 200*20% = 40
        assert lr1.blended_allowed_amount == Decimal("160.00")
        assert lr2.blended_allowed_amount == Decimal("40.00")
        assert blended == Decimal("200.00")

    def test_line_scope_primary_methodology_filter(self):
        """LINE ADD with primary_methodology='DRG': only DRG lines are blended."""
        lr_drg = _make_line(400.0, methodology="DRG")
        lr_rvu = _make_line(100.0, methodology="RBRVS")
        li_drg = _make_line_input(800.0)
        li_rvu = _make_line_input(200.0)
        rule = _make_blending_rule(32, "ADD", scope="LINE", primary_methodology="DRG", blend_percentage=10.0)
        blended, ids, status, traces = _apply_blending(
            Decimal("500.00"), Decimal("1000.00"),
            [lr_drg, lr_rvu], [li_drg, li_rvu], (rule,), SERVICE_DATE
        )
        # DRG line: 400 + 800*10% = 480
        # RBRVS line: unchanged at 100
        assert lr_drg.blended_allowed_amount == Decimal("480.00")
        assert lr_rvu.blended_allowed_amount is None
        assert blended == Decimal("580.00")  # 480 + 100

    def test_excluded_lines_not_blended(self):
        """CARVEOUT_EXCLUDED lines must remain at $0 and be excluded from blending."""
        lr_ok = _make_line(400.0, methodology="DRG")
        lr_ex = _make_line(0.0, methodology="DRG", status=PricingStatus.CARVEOUT_EXCLUDED)
        li_ok = _make_line_input(800.0)
        li_ex = _make_line_input(200.0)
        rule = _make_blending_rule(33, "ADD", scope="LINE", primary_methodology="", blend_percentage=10.0)
        blended, ids, status, traces = _apply_blending(
            Decimal("400.00"), Decimal("1000.00"),
            [lr_ok, lr_ex], [li_ok, li_ex], (rule,), SERVICE_DATE
        )
        # Excluded line: stays 0; ok line: 400 + 800*10% = 480
        assert lr_ex.blended_allowed_amount is None
        assert lr_ok.blended_allowed_amount == Decimal("480.00")
        assert blended == Decimal("480.00")

    def test_line_scope_no_matching_lines(self):
        """LINE scope rule with primary_methodology that matches nothing: nothing applied."""
        lr = _make_line(400.0, methodology="RBRVS")
        li = _make_line_input(800.0)
        rule = _make_blending_rule(34, "ADD", scope="LINE", primary_methodology="DRG", blend_percentage=10.0)
        blended, ids, status, traces = _apply_blending(
            Decimal("400.00"), Decimal("800.00"), [lr], [li], (rule,), SERVICE_DATE
        )
        assert blended == Decimal("400.00")  # unchanged
        assert ids == []
        assert lr.blended_allowed_amount is None


# ---------------------------------------------------------------------------
# Interaction with stop-loss / outlier
# ---------------------------------------------------------------------------

class TestBlendingWithPriorSteps:

    def test_blending_on_stop_loss_total(self):
        """If stop-loss reduced total to 600, ADD blending adds on top of 600."""
        lr = _make_line(1000.0)
        li = _make_line_input(2000.0)
        rule = _make_blending_rule(40, "ADD", blend_percentage=5.0)
        # Simulate: stop-loss reduced total from 1000 to 600
        post_outlier_total = Decimal("600.00")
        total_billed = Decimal("2000.00")
        blended, ids, status, traces = _apply_blending(
            post_outlier_total, total_billed, [lr], [li], (rule,), SERVICE_DATE
        )
        # 600 + 2000*5% = 600 + 100 = 700
        assert blended == Decimal("700.00")
        assert ids == [40]


# ---------------------------------------------------------------------------
# Unknown blend_type (defensive)
# ---------------------------------------------------------------------------

class TestEdgeCases:

    def test_unknown_blend_type_skipped(self):
        """An unrecognised blend_type is silently skipped."""
        lr = _make_line(500.0)
        rule = _make_blending_rule(50, "MULTIPLY", blend_percentage=10.0)
        blended, ids, status, traces = _apply_blending(
            Decimal("500.00"), Decimal("1000.00"), [lr], [_make_line_input(1000.0)], (rule,), SERVICE_DATE
        )
        assert blended == Decimal("500.00")
        assert ids == []

    def test_multiple_line_scope_rules_different_methodologies(self):
        """Two LINE rules with different primary_methodology each apply to their own lines."""
        lr_drg = _make_line(400.0, methodology="DRG")
        lr_rvu = _make_line(100.0, methodology="RBRVS")
        li_drg = _make_line_input(800.0)
        li_rvu = _make_line_input(200.0)
        rule_drg = _make_blending_rule(60, "ADD", scope="LINE", primary_methodology="DRG",
                                       blend_percentage=10.0, priority=2)
        rule_rvu = _make_blending_rule(61, "ADD", scope="LINE", primary_methodology="RBRVS",
                                       blend_percentage=20.0, priority=1)
        blended, ids, status, traces = _apply_blending(
            Decimal("500.00"), Decimal("1000.00"),
            [lr_drg, lr_rvu], [li_drg, li_rvu], (rule_drg, rule_rvu), SERVICE_DATE
        )
        # DRG: 400 + 800*10% = 480; RBRVS: 100 + 200*20% = 140
        assert lr_drg.blended_allowed_amount == Decimal("480.00")
        assert lr_rvu.blended_allowed_amount == Decimal("140.00")
        assert blended == Decimal("620.00")
        assert set(ids) == {60, 61}
        assert status == PricingStatus.BLENDING_APPLIED


# ---------------------------------------------------------------------------
# Integration: ClaimOrchestrator (mocked DB) with blending
# ---------------------------------------------------------------------------

class TestClaimOrchestratorBlending:
    """Verifies ClaimOrchestrator.run() threads blending into canonical execution order."""

    def _make_config(self, blending_rules=()):
        from core.engine.config import ContractPricingConfig
        contract = MagicMock()
        contract.pk = 1
        contract.effective_start_date = date(2024, 1, 1)
        version = MagicMock()
        version.pk = 1
        config = ContractPricingConfig(
            contract=contract,
            version=version,
            service_date=date(2025, 6, 1),
            rules=(),
            methodologies=(),
            stop_loss_rules=(),
            outlier_rules=(),
            base_rates={},
            carveouts=(),
            cap_floors=(),
            blending_rules=tuple(blending_rules),
        )
        return config, contract, version

    def _make_claim_input(self, contract, billed=1000.0):
        from core.engine.config import ClaimPricingInput, ClaimLineInput
        return ClaimPricingInput(
            contract=contract,
            service_date=date(2025, 6, 1),
            claim_type="INPATIENT",
            lines=[ClaimLineInput(procedure_code="470", billed_amount=Decimal(str(billed)), units=1)],
        )

    def test_no_blending_rules_result_unchanged(self):
        """Without blending rules ClaimPricingResult.blended_total_allowed equals total_allowed."""
        from core.engine.orchestrator import ClaimOrchestrator
        config, contract, version = self._make_config()
        claim_input = self._make_claim_input(contract)

        mock_result = LineResult(
            status=PricingStatus.SUCCESS,
            allowed_amount=Decimal("500.00"),
            methodology="DRG",
            details="",
            contract_id="1",
            rule_id=1,
            trace=PricingTrace(),
        )

        with patch("core.engine.orchestrator.resolve_active_contract_version", return_value=version), \
             patch("core.engine.orchestrator.build_contract_pricing_config_from_db", return_value=config), \
             patch.object(ClaimOrchestrator, "__init__", return_value=None):

            orch = ClaimOrchestrator.__new__(ClaimOrchestrator)
            mock_line_orch = MagicMock()
            mock_line_orch.run.return_value = mock_result
            mock_line_orch.loader = MagicMock()
            orch.line_orchestrator = mock_line_orch

            result = orch.run(claim_input, config=config)

        assert result.blended_total_allowed == result.total_allowed
        assert result.applied_blending_rule_ids == []

    def test_claim_add_blending_in_orchestrator(self):
        """CLAIM ADD blending is applied and reflected in ClaimPricingResult."""
        from core.engine.orchestrator import ClaimOrchestrator

        blend_rule = _make_blending_rule(99, "ADD", scope="CLAIM", blend_percentage=10.0)
        config, contract, version = self._make_config(blending_rules=(blend_rule,))
        claim_input = self._make_claim_input(contract, billed=1000.0)

        mock_result = LineResult(
            status=PricingStatus.SUCCESS,
            allowed_amount=Decimal("500.00"),
            methodology="DRG",
            details="",
            contract_id="1",
            rule_id=1,
            trace=PricingTrace(),
        )

        with patch("core.engine.orchestrator.resolve_active_contract_version", return_value=version), \
             patch("core.engine.orchestrator.build_contract_pricing_config_from_db", return_value=config), \
             patch.object(ClaimOrchestrator, "__init__", return_value=None):

            orch = ClaimOrchestrator.__new__(ClaimOrchestrator)
            mock_line_orch = MagicMock()
            mock_line_orch.run.return_value = mock_result
            mock_line_orch.loader = MagicMock()
            orch.line_orchestrator = mock_line_orch

            result = orch.run(claim_input, config=config)

        # post-line total = 500; blending ADD 10% of 1000 billed = 100 → blended = 600
        assert result.blended_total_allowed == Decimal("600.00")
        assert result.total_allowed == Decimal("600.00")
        assert result.final_total_allowed == Decimal("600.00")
        assert 99 in result.applied_blending_rule_ids
        assert result.status == PricingStatus.BLENDING_APPLIED


# ---------------------------------------------------------------------------
# Serializer: blending fields exposed in API response
# ---------------------------------------------------------------------------

class TestBlendingSerializer:

    def test_claim_result_serializer_exposes_blending_fields(self):
        """ClaimPricingResultSerializer must include blended_total_allowed and applied_blending_rule_ids."""
        from core.api.serializers import ClaimPricingResultSerializer

        line = LineResult(
            status=PricingStatus.SUCCESS,
            allowed_amount=Decimal("600.00"),
            methodology="DRG",
            details="",
            contract_id="1",
            rule_id=1,
            trace=PricingTrace(),
        )
        result = ClaimPricingResult(
            claim_id=42,
            contract_id="1",
            lines=[line],
            total_allowed=Decimal("600.00"),
            line_count=1,
            status=PricingStatus.BLENDING_APPLIED,
            blended_total_allowed=Decimal("600.00"),
            applied_blending_rule_ids=[99],
        )

        data = ClaimPricingResultSerializer(result).data
        assert "blended_total_allowed" in data
        assert "applied_blending_rule_ids" in data
        assert data["applied_blending_rule_ids"] == [99]

    def test_line_result_serializer_exposes_blending_fields(self):
        """PricingResponseSerializer must include blended_allowed_amount and blending_rule_id."""
        from core.api.serializers import PricingResponseSerializer

        line = LineResult(
            status=PricingStatus.SUCCESS,
            allowed_amount=Decimal("500.00"),
            methodology="DRG",
            details="",
            contract_id="1",
            rule_id=1,
            trace=PricingTrace(),
            blended_allowed_amount=Decimal("550.00"),
            blending_rule_id=30,
        )
        data = PricingResponseSerializer(line).data
        assert "blended_allowed_amount" in data
        assert "blending_rule_id" in data
        assert Decimal(str(data["blended_allowed_amount"])) == Decimal("550.00")
        assert data["blending_rule_id"] == 30
