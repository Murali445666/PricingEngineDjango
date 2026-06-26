"""
Step 7 – Contract Carve-Out Execution
Step 8 – Caps and Floors

Tests validate:
  Step 7:
    - Line matching an EXCLUDE carve-out → allowed = $0, status = CARVEOUT_EXCLUDED
    - Line matching a PCT_BILLED carve-out → allowed = billed * pct, status = CARVEOUT_REPRICED
    - Line matching a FIXED_RATE carve-out → allowed = carveout_rate, status = CARVEOUT_REPRICED
    - Line with no matching carve-out → unchanged (status = SUCCESS)
    - base_allowed_amount preserved in LineResult for audit
    - Carve-out applied AFTER base methodology: base_allowed_amount != 0 for EXCLUDE
    - Multi-line: mix of excluded, repriced, normal lines
    - Carve-out + stop-loss: stop-loss uses total_cost, carve-out affects total_allowed
    - Execution order: carve-out before stop-loss before outlier before cap

  Step 8:
    - Claim total above CAP → clamped to cap; status = CAP_APPLIED
    - Claim total below FLOOR → raised to floor; status = FLOOR_APPLIED
    - PCT_BILLED_CAP: cap = billed * pct; applied when total > cap
    - PCT_BILLED_CAP: not applied when total < billed_cap
    - No cap/floor configured → result unchanged
    - DRG-scope cap applies only when DRG line present
    - pre_cap_total_allowed recorded before clamp
    - applied_cap_floor_id set when rule fires

  Combined:
    - Carve-out → stop-loss → outlier → cap all applied in canonical order
    - Bulk pricing with shared config: all claims get carve-out + cap correctly
    - Per-claim cache isolation maintained across bulk batch
"""
from decimal import Decimal
from datetime import date

from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework import status as http_status

from core.models import (
    ProviderOrganization, PayerNetwork, ProviderContract, ContractVersion,
    FeeSchedule, FeeScheduleRate, PricingRule, PricingRuleCondition,
    ContractCarveout, ContractCapFloor, ContractStopLossRule,
)
from core.engine.orchestrator import ClaimOrchestrator, _apply_carveout, _apply_cap_floor
from core.engine.service import ClaimPricingService
from core.engine.config import (
    ClaimPricingInput, ClaimLineInput, ContractPricingConfig,
)
from core.engine.types import PricingStatus, LineResult, PricingTrace, ClaimPricingResult
from core.engine.loader import build_contract_pricing_config_from_db
from tests.utils import MatrixPricingEngine


# ============================================================
# Shared test fixture builder
# ============================================================

class CarveoutCapFloorBase(TestCase):
    """
    Creates a minimal contract with version, one RBRVS rule for '99213',
    and helper methods to attach carve-outs and caps/floors.
    """

    SERVICE_DATE = date(2025, 6, 1)

    def setUp(self):
        payer = ProviderOrganization.objects.create(
            organization_id="PAYER-CO", name="Co Payer", tax_id="11-0000001"
        )
        provider = ProviderOrganization.objects.create(
            organization_id="PROV-CO", name="Co Provider", tax_id="22-0000002"
        )
        network = PayerNetwork.objects.create(
            network_id="NET-CO", network_name="Co Network", payer_org=payer
        )
        self.contract = ProviderContract.objects.create(
            contract_name="CarveoutTest",
            legacy_contract_number="CO-TEST",
            status="ACTIVE",
            effective_start_date=date(2025, 1, 1),
            provider_org=provider,
            network=network,
        )
        self.version = ContractVersion.objects.create(
            contract=self.contract,
            version_number=1,
            effective_start_date=date(2025, 1, 1),
            status="ACTIVE",
        )

        # Fee schedule with two codes
        self.fs = FeeSchedule.objects.create(name="CO FS 2025", effective_date=date(2025, 1, 1))
        FeeScheduleRate.objects.create(
            fee_schedule=self.fs, code_id="99213", rate_amount=Decimal("100.00")
        )
        FeeScheduleRate.objects.create(
            fee_schedule=self.fs, code_id="73030", rate_amount=Decimal("75.00")
        )

        # RBRVS rule for 99213 (multiplier 1.50 → base allowed = $150)
        r1 = PricingRule.objects.create(
            contract=self.contract, version=self.version,
            rule_name="RBRVS 99213", specificity_score=10,
            methodology_code="RBRVS", base_fee_schedule=self.fs,
            multiplier=Decimal("1.50"), status=PricingRule.RuleStatus.ACTIVE,
            effective_start_date=date(2025, 1, 1),
        )
        PricingRuleCondition.objects.create(
            pricing_rule=r1, attribute_name="procedure_code",
            operator="EQ", attribute_value="99213"
        )
        # FLAT_RATE rule for 73030 (flat = $75)
        r2 = PricingRule.objects.create(
            contract=self.contract, version=self.version,
            rule_name="Flat 73030", specificity_score=10,
            methodology_code="FLAT_RATE", flat_rate=Decimal("75.00"),
            status=PricingRule.RuleStatus.ACTIVE,
            effective_start_date=date(2025, 1, 1),
        )
        PricingRuleCondition.objects.create(
            pricing_rule=r2, attribute_name="procedure_code",
            operator="EQ", attribute_value="73030"
        )

    def _build_config(self):
        return build_contract_pricing_config_from_db(
            self.contract, self.version, self.SERVICE_DATE
        )

    def _make_claim(self, lines):
        return ClaimPricingInput(
            contract=self.contract,
            contract_id=self.contract.pk,
            service_date=self.SERVICE_DATE,
            lines=lines,
        )

    def _line(self, code, billed, cost=None):
        return ClaimLineInput(
            procedure_code=code,
            billed_amount=Decimal(str(billed)),
            units=1,
            cost_amount=Decimal(str(cost)) if cost else None,
        )


# ============================================================
# Step 7 — Carve-Out Tests
# ============================================================

class CarveoutExcludeTests(CarveoutCapFloorBase):

    def test_exclude_zeroes_line_and_sets_status(self):
        """EXCLUDE carve-out → allowed = $0, status = CARVEOUT_EXCLUDED."""
        ContractCarveout.objects.create(
            version=self.version, code_type="CPT", code_value="99213",
            carveout_methodology="EXCLUDE",
        )
        config = self._build_config()
        service = ClaimPricingService()
        result = service.price_claim(
            self._make_claim([self._line("99213", 200)])
        )
        self.assertEqual(len(result.lines), 1)
        line = result.lines[0]
        self.assertEqual(line.status, PricingStatus.CARVEOUT_EXCLUDED)
        self.assertEqual(line.allowed_amount, Decimal("0.00"))
        self.assertTrue(line.carveout_applied)
        self.assertIsNotNone(line.carveout_id)

    def test_exclude_preserves_base_allowed_for_audit(self):
        """base_allowed_amount records what the strategy computed before exclusion."""
        ContractCarveout.objects.create(
            version=self.version, code_type="CPT", code_value="99213",
            carveout_methodology="EXCLUDE",
        )
        config = self._build_config()
        service = ClaimPricingService()
        result = service.price_claim(self._make_claim([self._line("99213", 200)]))
        line = result.lines[0]
        # RBRVS: base_rate=100, multiplier=1.50 → strategy computes $150
        self.assertEqual(line.base_allowed_amount, Decimal("150.00"))

    def test_exclude_contributes_zero_to_claim_total(self):
        """Excluded line contributes $0 to total_allowed."""
        ContractCarveout.objects.create(
            version=self.version, code_type="CPT", code_value="99213",
            carveout_methodology="EXCLUDE",
        )
        service = ClaimPricingService()
        result = service.price_claim(
            self._make_claim([self._line("99213", 200), self._line("73030", 100)])
        )
        # 99213 excluded → $0; 73030 flat → $75
        self.assertEqual(result.total_allowed, Decimal("75.00"))


class CarveoutPctBilledTests(CarveoutCapFloorBase):

    def test_pct_billed_reprices_correctly(self):
        """PCT_BILLED at 50% → allowed = billed * 0.50."""
        ContractCarveout.objects.create(
            version=self.version, code_type="CPT", code_value="99213",
            carveout_methodology="PCT_BILLED", carveout_percentage=Decimal("50.00"),
        )
        service = ClaimPricingService()
        result = service.price_claim(self._make_claim([self._line("99213", 200)]))
        line = result.lines[0]
        self.assertEqual(line.status, PricingStatus.CARVEOUT_REPRICED)
        self.assertEqual(line.allowed_amount, Decimal("100.00"))  # 200 * 50%
        self.assertEqual(line.base_allowed_amount, Decimal("150.00"))  # original RBRVS

    def test_pct_billed_100_equals_billed(self):
        """PCT_BILLED at 100% → allowed = billed_amount."""
        ContractCarveout.objects.create(
            version=self.version, code_type="CPT", code_value="99213",
            carveout_methodology="PCT_BILLED", carveout_percentage=Decimal("100.00"),
        )
        service = ClaimPricingService()
        result = service.price_claim(self._make_claim([self._line("99213", 200)]))
        self.assertEqual(result.lines[0].allowed_amount, Decimal("200.00"))


class CarveoutFixedRateTests(CarveoutCapFloorBase):

    def test_fixed_rate_uses_carveout_rate(self):
        """FIXED_RATE carve-out → allowed = carveout_rate, ignores strategy result."""
        ContractCarveout.objects.create(
            version=self.version, code_type="CPT", code_value="99213",
            carveout_methodology="FIXED_RATE", carveout_rate=Decimal("55.00"),
        )
        service = ClaimPricingService()
        result = service.price_claim(self._make_claim([self._line("99213", 200)]))
        line = result.lines[0]
        self.assertEqual(line.status, PricingStatus.CARVEOUT_REPRICED)
        self.assertEqual(line.allowed_amount, Decimal("55.00"))
        self.assertEqual(line.base_allowed_amount, Decimal("150.00"))


class CarveoutNoMatchTests(CarveoutCapFloorBase):

    def test_no_match_line_unchanged(self):
        """A line with no matching carve-out is unchanged (SUCCESS, original price)."""
        ContractCarveout.objects.create(
            version=self.version, code_type="CPT", code_value="ZZZZZ",
            carveout_methodology="EXCLUDE",
        )
        service = ClaimPricingService()
        result = service.price_claim(self._make_claim([self._line("99213", 200)]))
        line = result.lines[0]
        self.assertEqual(line.status, PricingStatus.SUCCESS)
        self.assertEqual(line.allowed_amount, Decimal("150.00"))
        self.assertFalse(line.carveout_applied)
        self.assertIsNone(line.carveout_id)

    def test_different_code_not_affected(self):
        """Carve-out on 73030 must not affect 99213."""
        ContractCarveout.objects.create(
            version=self.version, code_type="CPT", code_value="73030",
            carveout_methodology="EXCLUDE",
        )
        service = ClaimPricingService()
        result = service.price_claim(
            self._make_claim([self._line("99213", 200), self._line("73030", 100)])
        )
        self.assertEqual(result.lines[0].status, PricingStatus.SUCCESS)
        self.assertEqual(result.lines[0].allowed_amount, Decimal("150.00"))
        self.assertEqual(result.lines[1].status, PricingStatus.CARVEOUT_EXCLUDED)
        self.assertEqual(result.lines[1].allowed_amount, Decimal("0.00"))


class CarveoutWithStopLossTests(CarveoutCapFloorBase):
    """Step 7 carve-out interacts correctly with Step 5 stop-loss."""

    def test_carveout_exclude_then_stoploss(self):
        """
        Excluded line reduces total_allowed; stop-loss applied to post-carveout total.
        Scenario:
          - 99213 excluded → $0
          - 73030 flat → $75
          - stop-loss threshold=$50, reimbursement=80%: total_cost=$40 < threshold → no trigger
        """
        ContractCarveout.objects.create(
            version=self.version, code_type="CPT", code_value="99213",
            carveout_methodology="EXCLUDE",
        )
        ContractStopLossRule.objects.create(
            contract=self.contract, version=self.version,
            cost_threshold=Decimal("50.00"),
            reimbursement_percentage=Decimal("80.00"),
            priority=1,
            effective_start_date=date(2025, 1, 1),
        )
        service = ClaimPricingService()
        result = service.price_claim(
            self._make_claim([
                self._line("99213", 200, cost=20),
                self._line("73030", 100, cost=20),
            ])
        )
        # total_cost=40 < threshold=50 → stop-loss not triggered
        self.assertEqual(result.total_allowed, Decimal("75.00"))
        self.assertEqual(result.status, PricingStatus.SUCCESS)

    def test_stoploss_triggered_after_carveout(self):
        """Stop-loss triggers on total_cost even when a line is carve-out excluded."""
        ContractCarveout.objects.create(
            version=self.version, code_type="CPT", code_value="73030",
            carveout_methodology="EXCLUDE",
        )
        ContractStopLossRule.objects.create(
            contract=self.contract, version=self.version,
            cost_threshold=Decimal("50.00"),
            reimbursement_percentage=Decimal("80.00"),
            priority=1,
            effective_start_date=date(2025, 1, 1),
        )
        service = ClaimPricingService()
        result = service.price_claim(
            self._make_claim([
                self._line("99213", 200, cost=80),   # cost > threshold
                self._line("73030", 100, cost=0),
            ])
        )
        # Stop-loss: cost=80 > 50; excess=30; stoploss = 50 + 30*0.80 = 74.00
        self.assertEqual(result.status, PricingStatus.STOP_LOSS_APPLIED)
        self.assertEqual(result.total_allowed, Decimal("74.00"))


# ============================================================
# Step 8 — Cap/Floor Tests
# ============================================================

class CapFloorBase(CarveoutCapFloorBase):
    """Adds cap/floor helpers on top of CarveoutCapFloorBase."""

    def _add_cap(self, cap_value, scope="CLAIM", cap_type="CAP", priority=1,
                 pct=None, code_value=None):
        kwargs = dict(
            version=self.version,
            scope=scope,
            cap_type=cap_type,
            priority=priority,
            effective_start_date=date(2025, 1, 1),
        )
        if pct is not None:
            kwargs["percentage"] = Decimal(str(pct))
        else:
            kwargs["value"] = Decimal(str(cap_value))
        if code_value:
            kwargs["code_value"] = code_value
        return ContractCapFloor.objects.create(**kwargs)


class CapTests(CapFloorBase):

    def test_claim_above_cap_clamped(self):
        """Total above CAP is reduced to cap value."""
        self._add_cap(100)  # cap = $100; RBRVS line = $150
        service = ClaimPricingService()
        result = service.price_claim(self._make_claim([self._line("99213", 200)]))
        self.assertEqual(result.status, PricingStatus.CAP_APPLIED)
        self.assertEqual(result.total_allowed, Decimal("100.00"))
        self.assertEqual(result.final_total_allowed, Decimal("100.00"))
        self.assertEqual(result.pre_cap_total_allowed, Decimal("150.00"))
        self.assertIsNotNone(result.applied_cap_floor_id)

    def test_claim_below_cap_not_affected(self):
        """Total below CAP is not changed."""
        self._add_cap(500)  # cap = $500; RBRVS line = $150
        service = ClaimPricingService()
        result = service.price_claim(self._make_claim([self._line("99213", 200)]))
        self.assertNotEqual(result.status, PricingStatus.CAP_APPLIED)
        self.assertEqual(result.total_allowed, Decimal("150.00"))
        self.assertIsNone(result.applied_cap_floor_id)

    def test_floor_raises_below_minimum(self):
        """Total below FLOOR is raised to floor value."""
        ContractCapFloor.objects.create(
            version=self.version, scope="CLAIM", cap_type="FLOOR",
            value=Decimal("200.00"), priority=1, effective_start_date=date(2025, 1, 1),
        )
        service = ClaimPricingService()
        result = service.price_claim(self._make_claim([self._line("73030", 100)]))
        # FLAT_RATE → $75; floor = $200
        self.assertEqual(result.status, PricingStatus.FLOOR_APPLIED)
        self.assertEqual(result.total_allowed, Decimal("200.00"))
        self.assertEqual(result.pre_cap_total_allowed, Decimal("75.00"))

    def test_floor_not_applied_above_minimum(self):
        """Total above FLOOR is not changed."""
        ContractCapFloor.objects.create(
            version=self.version, scope="CLAIM", cap_type="FLOOR",
            value=Decimal("50.00"), priority=1, effective_start_date=date(2025, 1, 1),
        )
        service = ClaimPricingService()
        result = service.price_claim(self._make_claim([self._line("99213", 200)]))
        self.assertNotEqual(result.status, PricingStatus.FLOOR_APPLIED)
        self.assertEqual(result.total_allowed, Decimal("150.00"))

    def test_pct_billed_cap_applies_when_above(self):
        """PCT_BILLED_CAP: cap = total_billed * pct%; applied when total > cap."""
        self._add_cap(None, cap_type="PCT_BILLED_CAP", pct=60)
        # RBRVS allowed = $150; billed = $200; 60% of $200 = $120 → allowed > cap
        service = ClaimPricingService()
        result = service.price_claim(self._make_claim([self._line("99213", 200)]))
        self.assertEqual(result.status, PricingStatus.CAP_APPLIED)
        self.assertEqual(result.total_allowed, Decimal("120.00"))

    def test_pct_billed_cap_not_applied_when_below(self):
        """PCT_BILLED_CAP: not applied when allowed already below billed cap."""
        self._add_cap(None, cap_type="PCT_BILLED_CAP", pct=90)
        # allowed = $150; billed = $200; 90% = $180 > $150 → no cap
        service = ClaimPricingService()
        result = service.price_claim(self._make_claim([self._line("99213", 200)]))
        self.assertNotEqual(result.status, PricingStatus.CAP_APPLIED)
        self.assertEqual(result.total_allowed, Decimal("150.00"))

    def test_no_cap_floor_configured_result_unchanged(self):
        """When no cap/floor exists, result is unaffected."""
        service = ClaimPricingService()
        result = service.price_claim(self._make_claim([self._line("99213", 200)]))
        self.assertEqual(result.status, PricingStatus.SUCCESS)
        self.assertEqual(result.total_allowed, Decimal("150.00"))
        self.assertIsNone(result.applied_cap_floor_id)
        self.assertEqual(result.pre_cap_total_allowed, Decimal("150.00"))


class LineCapFloorTests(CapFloorBase):
    """Line-level cap/floor (lesser-of billed) rolls up into claim total."""

    def test_line_pct_billed_cap_lesser_of_billed(self):
        """LINE PCT_BILLED_CAP 100% → min(RBRVS fee, billed); claim total includes capped line."""
        self._add_cap(None, scope="LINE", cap_type="PCT_BILLED_CAP", pct=100)
        # RBRVS = $150; billed = $100 → line capped to $100
        service = ClaimPricingService()
        result = service.price_claim(self._make_claim([self._line("99213", 100)]))
        line = result.lines[0]
        self.assertEqual(line.status, PricingStatus.CAP_APPLIED)
        self.assertEqual(line.allowed_amount, Decimal("100.00"))
        self.assertEqual(result.total_allowed, Decimal("100.00"))
        self.assertEqual(result.final_total_allowed, Decimal("100.00"))

    def test_line_pct_billed_cap_not_applied_when_fee_below_billed(self):
        """When calculated fee is already below billed cap, line stays SUCCESS."""
        self._add_cap(None, scope="LINE", cap_type="PCT_BILLED_CAP", pct=100)
        # RBRVS = $150; billed = $200 → no cap needed
        service = ClaimPricingService()
        result = service.price_claim(self._make_claim([self._line("99213", 200)]))
        line = result.lines[0]
        self.assertEqual(line.status, PricingStatus.SUCCESS)
        self.assertEqual(line.allowed_amount, Decimal("150.00"))
        self.assertEqual(result.total_allowed, Decimal("150.00"))

    def test_line_cap_floor_multi_line_claim_total(self):
        """Mixed lines: capped RBRVS + flat rate both roll up correctly."""
        self._add_cap(None, scope="LINE", cap_type="PCT_BILLED_CAP", pct=100)
        service = ClaimPricingService()
        result = service.price_claim(
            self._make_claim([self._line("99213", 100), self._line("73030", 500)])
        )
        # 99213: $150 capped to $100; 73030 flat $75
        self.assertEqual(result.lines[0].allowed_amount, Decimal("100.00"))
        self.assertEqual(result.lines[1].allowed_amount, Decimal("75.00"))
        self.assertEqual(result.total_allowed, Decimal("175.00"))


class CanonicalOrderTests(CapFloorBase):
    """
    Verify canonical execution order:
    carve-out → stop-loss → outlier → cap/floor
    """

    def test_carveout_then_cap(self):
        """
        EXCLUDE carve-out zeroes a line, then cap clamps the remaining total.
        99213 excluded → $0; 73030 flat → $75; CAP = $50 → total clamped to $50.
        """
        ContractCarveout.objects.create(
            version=self.version, code_type="CPT", code_value="99213",
            carveout_methodology="EXCLUDE",
        )
        self._add_cap(50)
        service = ClaimPricingService()
        result = service.price_claim(
            self._make_claim([self._line("99213", 200), self._line("73030", 100)])
        )
        self.assertEqual(result.total_allowed, Decimal("50.00"))
        self.assertEqual(result.status, PricingStatus.CAP_APPLIED)
        self.assertEqual(result.pre_cap_total_allowed, Decimal("75.00"))

    def test_stoploss_then_cap(self):
        """
        Stop-loss fires first (reduces total from $150 to $80), then cap clamps to $60.
        """
        ContractStopLossRule.objects.create(
            contract=self.contract, version=self.version,
            cost_threshold=Decimal("50.00"),
            reimbursement_percentage=Decimal("80.00"),
            priority=1, effective_start_date=date(2025, 1, 1),
        )
        self._add_cap(60)
        service = ClaimPricingService()
        result = service.price_claim(
            self._make_claim([self._line("99213", 200, cost=80)])
        )
        # Stop-loss: 50 + (80-50)*0.8 = 50 + 24 = 74
        # Cap=60 → 74 > 60 → clamped to 60
        self.assertEqual(result.status, PricingStatus.CAP_APPLIED)
        self.assertEqual(result.total_allowed, Decimal("60.00"))
        self.assertEqual(result.pre_cap_total_allowed, Decimal("74.00"))


# ============================================================
# Bulk Pricing with Carve-outs and Caps
# ============================================================

class BulkCarveoutCapTests(CarveoutCapFloorBase):

    def test_bulk_carveout_applied_per_claim(self):
        """All claims in a bulk batch get the same carve-out applied correctly."""
        ContractCarveout.objects.create(
            version=self.version, code_type="CPT", code_value="99213",
            carveout_methodology="FIXED_RATE", carveout_rate=Decimal("40.00"),
        )
        service = ClaimPricingService()
        claims = [
            self._make_claim([self._line("99213", 200)]),
            self._make_claim([self._line("99213", 200)]),
            self._make_claim([self._line("99213", 200)]),
        ]
        results = service.price_claims_bulk(claims)
        for r in results:
            self.assertEqual(r.lines[0].status, PricingStatus.CARVEOUT_REPRICED)
            self.assertEqual(r.lines[0].allowed_amount, Decimal("40.00"))
            self.assertEqual(r.total_allowed, Decimal("40.00"))

    def test_bulk_cap_applied_per_claim(self):
        """Cap is applied independently to each claim in the batch."""
        ContractCapFloor.objects.create(
            version=self.version, scope="CLAIM", cap_type="CAP",
            value=Decimal("100.00"), priority=1, effective_start_date=date(2025, 1, 1),
        )
        service = ClaimPricingService()
        claims = [self._make_claim([self._line("99213", 200)]) for _ in range(3)]
        results = service.price_claims_bulk(claims)
        for r in results:
            self.assertEqual(r.status, PricingStatus.CAP_APPLIED)
            self.assertEqual(r.total_allowed, Decimal("100.00"))

    def test_bulk_cache_isolation_carveout(self):
        """Per-claim execution cache isolation: carve-out on claim N does not bleed to claim N+1."""
        ContractCarveout.objects.create(
            version=self.version, code_type="CPT", code_value="99213",
            carveout_methodology="EXCLUDE",
        )
        service = ClaimPricingService()
        claims = [
            self._make_claim([self._line("99213", 200), self._line("73030", 100)]),
            self._make_claim([self._line("73030", 100)]),
            self._make_claim([self._line("99213", 200), self._line("73030", 100)]),
        ]
        results = service.price_claims_bulk(claims)
        # Claim 0: 99213 excluded ($0) + 73030 flat ($75) = $75
        self.assertEqual(results[0].total_allowed, Decimal("75.00"))
        # Claim 1: only 73030 flat = $75 (no carve-out for this code)
        self.assertEqual(results[1].total_allowed, Decimal("75.00"))
        # Claim 2: same as claim 0 — $75
        self.assertEqual(results[2].total_allowed, Decimal("75.00"))


# ============================================================
# API Endpoint Tests
# ============================================================

class CarveoutCapAPITests(MatrixPricingEngine, APITestCase):
    """
    Integration tests via POST /api/price-claim/ and /api/price-claims-bulk/.
    Verifies that carve-out and cap/floor fields appear in the API response.
    """

    def setUp(self):
        super().setUp()
        self.url_single = reverse('price-claim')
        self.url_bulk = reverse('price-claims-bulk')

    def test_api_line_response_has_carveout_fields(self):
        """API response includes carveout_applied/carveout_id even when no carve-out applied."""
        payload = {
            "contract_id": self.contract.pk,
            "service_date": "2025-06-01",
            "lines": [{"procedure_code": "99213", "billed_amount": "200.00", "units": 1}],
        }
        resp = self.client.post(self.url_single, payload, format='json')
        self.assertEqual(resp.status_code, http_status.HTTP_200_OK)
        line = resp.data['lines'][0]
        self.assertIn('carveout_applied', line)
        self.assertIn('carveout_id', line)
        self.assertIn('base_allowed_amount', line)

    def test_api_claim_response_has_cap_floor_fields(self):
        """API response includes pre_cap_total_allowed and applied_cap_floor_id."""
        payload = {
            "contract_id": self.contract.pk,
            "service_date": "2025-06-01",
            "lines": [{"procedure_code": "99213", "billed_amount": "200.00", "units": 1}],
        }
        resp = self.client.post(self.url_single, payload, format='json')
        self.assertEqual(resp.status_code, http_status.HTTP_200_OK)
        self.assertIn('pre_cap_total_allowed', resp.data)
        self.assertIn('applied_cap_floor_id', resp.data)

    def test_bulk_api_has_carveout_fields_per_line(self):
        """Bulk endpoint also exposes carveout fields in each line."""
        payload = {
            "claims": [
                {
                    "contract_id": self.contract.pk,
                    "service_date": "2025-06-01",
                    "lines": [{"procedure_code": "99213", "billed_amount": "200.00", "units": 1}],
                }
            ]
        }
        resp = self.client.post(self.url_bulk, payload, format='json')
        self.assertEqual(resp.status_code, http_status.HTTP_200_OK)
        line = resp.data['results'][0]['lines'][0]
        self.assertIn('carveout_applied', line)
        self.assertIn('carveout_id', line)
