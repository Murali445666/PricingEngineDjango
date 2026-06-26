"""Phase 6: Contract outlier rules — precedence, effective dating, and audit trace."""
from datetime import date
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APITestCase

from core.models import (
    ProviderContract,
    ProviderOrganization,
    PayerNetwork,
    FeeSchedule,
    FeeScheduleRate,
    PricingRule,
    PricingRuleCondition,
    RefProcedureCode,
    ContractOutlierRule,
    ClaimHeader,
    ClaimLine,
)
from core.engine.orchestrator import PricingEngine
from core.engine.types import PricingStatus


class OutlierTestMixin:
    """Shared setup: contract with one RBRVS rule (99213 -> $150/line)."""

    def setUp(self):
        self.engine = PricingEngine()
        payer_org = ProviderOrganization.objects.create(
            organization_id="PAYER-OUT", name="Outlier Payer", tax_id="00-0000000"
        )
        provider_org = ProviderOrganization.objects.create(
            organization_id="PROV-OUT", name="Outlier Provider", tax_id="11-1111111"
        )
        network = PayerNetwork.objects.create(
            network_id="NET-OUT", network_name="Outlier Network", payer_org=payer_org
        )
        self.contract = ProviderContract.objects.create(
            contract_name="Outlier Contract",
            legacy_contract_number="CONT-OUT",
            status="ACTIVE",
            effective_start_date=date(2025, 1, 1),
            provider_org=provider_org,
            network=network,
        )
        fs = FeeSchedule.objects.create(name="Outlier FS", effective_date=date(2025, 1, 1))
        RefProcedureCode.objects.create(
            code_id="99213", description="Office Visit", work_rvu=Decimal("0.97")
        )
        FeeScheduleRate.objects.create(
            fee_schedule=fs, code_id="99213", rate_amount=Decimal("100.00")
        )
        rule = PricingRule.objects.create(
            contract=self.contract,
            rule_name="RBRVS 99213",
            specificity_score=10,
            methodology_code="RBRVS",
            base_fee_schedule=fs,
            multiplier=Decimal("1.50"),
            status=PricingRule.RuleStatus.ACTIVE,
        )
        PricingRuleCondition.objects.create(
            pricing_rule=rule,
            attribute_name="procedure_code",
            operator="EQ",
            attribute_value="99213",
        )

    def _create_claim(self, service_date, lines_data):
        """lines_data: list of (procedure_code, billed_amount, units=1, sequence=0)."""
        header = ClaimHeader.objects.create(
            contract=self.contract,
            service_date=service_date,
            claim_type="PROFESSIONAL",
        )
        for i, row in enumerate(lines_data):
            code = row[0]
            billed = row[1]
            units = row[2] if len(row) > 2 else 1
            seq = row[3] if len(row) > 3 else i
            ClaimLine.objects.create(
                claim=header,
                procedure_code=code,
                billed_amount=billed,
                units=units,
                sequence=seq,
            )
        return header


class TestOutlierNoRules(OutlierTestMixin, TestCase):
    """No outlier rules: claim pricing runs normally; audit fields match."""

    def test_no_rules_standard_pricing_audit_fields(self):
        # No ContractOutlierRule created.
        claim = self._create_claim(
            date(2025, 6, 15),
            [("99213", Decimal("100.00")), ("99213", Decimal("200.00"))],
        )
        result = self.engine.calculate_claim(claim)
        self.assertEqual(result.status, PricingStatus.SUCCESS)
        self.assertEqual(result.total_allowed, Decimal("300.00"))
        self.assertEqual(result.original_total_allowed, Decimal("300.00"))
        self.assertEqual(result.final_total_allowed, Decimal("300.00"))
        self.assertIsNone(result.applied_outlier_rule_id)
        self.assertEqual(len(result.claim_trace), 0)


class TestOutlierPerLineRejected(OutlierTestMixin, APITestCase):
    """PER_LINE scope is rejected by API to prevent runtime NotImplementedError."""

    def test_post_per_line_returns_400(self):
        url = reverse("api-contract-outlier-rules", kwargs={"pk": self.contract.pk})
        payload = {
            "threshold_amount": "1000.00",
            "threshold_scope": "PER_LINE",
            "reimbursement_percentage": "50.00",
            "priority": 0,
            "effective_start_date": "2025-01-01",
        }
        response = self.client.post(url, payload, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("PER_LINE", str(response.data))


class TestOutlierBelowThreshold(OutlierTestMixin, TestCase):
    """Below threshold → standard pricing applies."""

    def test_below_threshold_standard_pricing(self):
        # Rule: threshold 10_000, 50% reimbursement. Claim total billed = 300 < 10_000.
        ContractOutlierRule.objects.create(
            contract=self.contract,
            threshold_amount=Decimal("10000.00"),
            threshold_scope="PER_CLAIM",
            reimbursement_percentage=Decimal("50.00"),
            priority=0,
            effective_start_date=date(2025, 1, 1),
        )
        claim = self._create_claim(
            date(2025, 6, 15),
            [("99213", Decimal("100.00")), ("99213", Decimal("200.00"))],
        )
        result = self.engine.calculate_claim(claim)
        # Standard: 2 lines × $150 = $300
        self.assertEqual(result.status, PricingStatus.SUCCESS)
        self.assertEqual(result.total_allowed, Decimal("300.00"))
        self.assertEqual(len(result.claim_trace), 0)


class TestOutlierAboveThreshold(OutlierTestMixin, TestCase):
    """Above threshold → claim total overridden correctly."""

    def test_above_threshold_reimbursement_percentage(self):
        # total_billed = 500 + 500 = 1000. threshold 500. 50% -> 500.
        rule = ContractOutlierRule.objects.create(
            contract=self.contract,
            threshold_amount=Decimal("500.00"),
            threshold_scope="PER_CLAIM",
            reimbursement_percentage=Decimal("50.00"),
            priority=0,
            effective_start_date=date(2025, 1, 1),
        )
        claim = self._create_claim(
            date(2025, 6, 15),
            [("99213", Decimal("500.00")), ("99213", Decimal("500.00"))],
        )
        result = self.engine.calculate_claim(claim)
        self.assertEqual(result.status, PricingStatus.OUTLIER_APPLIED)
        self.assertEqual(result.total_allowed, Decimal("500.00"))  # 1000 * 0.50
        self.assertEqual(result.original_total_allowed, Decimal("300.00"))  # 2 × 150
        self.assertEqual(result.final_total_allowed, Decimal("500.00"))
        self.assertEqual(result.applied_outlier_rule_id, rule.id)
        self.assertTrue(any("OUTLIER_APPLIED" in t for t in result.claim_trace))
        # Line allowed amounts are NOT modified; only claim total is overridden.
        self.assertEqual(result.lines[0].allowed_amount, Decimal("150.00"))
        self.assertEqual(result.lines[1].allowed_amount, Decimal("150.00"))

    def test_above_threshold_cost_to_charge_ratio(self):
        ContractOutlierRule.objects.create(
            contract=self.contract,
            threshold_amount=Decimal("100.00"),
            threshold_scope="PER_CLAIM",
            cost_to_charge_ratio=Decimal("0.25"),
            priority=0,
            effective_start_date=date(2025, 1, 1),
        )
        claim = self._create_claim(
            date(2025, 6, 15),
            [("99213", Decimal("200.00")), ("99213", Decimal("200.00"))],
        )
        result = self.engine.calculate_claim(claim)
        self.assertEqual(result.status, PricingStatus.OUTLIER_APPLIED)
        self.assertEqual(result.total_allowed, Decimal("100.00"))  # 400 * 0.25

    def test_reimbursement_percentage_takes_precedence_over_ccr(self):
        """When both set, reimbursement_percentage is used."""
        ContractOutlierRule.objects.create(
            contract=self.contract,
            threshold_amount=Decimal("100.00"),
            threshold_scope="PER_CLAIM",
            reimbursement_percentage=Decimal("50.00"),
            cost_to_charge_ratio=Decimal("0.10"),
            priority=0,
            effective_start_date=date(2025, 1, 1),
        )
        claim = self._create_claim(
            date(2025, 6, 15),
            [("99213", Decimal("200.00"))],
        )
        result = self.engine.calculate_claim(claim)
        self.assertEqual(result.status, PricingStatus.OUTLIER_APPLIED)
        # 50% of 200 = 100, not 0.10 * 200 = 20
        self.assertEqual(result.total_allowed, Decimal("100.00"))


class TestOutlierPriorityOrdering(OutlierTestMixin, TestCase):
    """Higher priority rule wins when both could apply."""

    def test_priority_desc_first_match_wins(self):
        # Low priority: threshold 1000, 80%. High priority: threshold 500, 40%.
        # total_billed = 600. Both apply. Order by priority DESC so high (40%) runs first.
        ContractOutlierRule.objects.create(
            contract=self.contract,
            threshold_amount=Decimal("1000.00"),
            threshold_scope="PER_CLAIM",
            reimbursement_percentage=Decimal("80.00"),
            priority=0,
            effective_start_date=date(2025, 1, 1),
        )
        ContractOutlierRule.objects.create(
            contract=self.contract,
            threshold_amount=Decimal("500.00"),
            threshold_scope="PER_CLAIM",
            reimbursement_percentage=Decimal("40.00"),
            priority=10,
            effective_start_date=date(2025, 1, 1),
        )
        claim = self._create_claim(
            date(2025, 6, 15),
            [("99213", Decimal("300.00")), ("99213", Decimal("300.00"))],
        )
        result = self.engine.calculate_claim(claim)
        self.assertEqual(result.status, PricingStatus.OUTLIER_APPLIED)
        # First matching rule (priority 10): 600 * 0.40 = 240
        self.assertEqual(result.total_allowed, Decimal("240.00"))


class TestOutlierEffectiveDating(OutlierTestMixin, TestCase):
    """Only rules valid for service_date apply."""

    def test_effective_start_after_service_date_excluded(self):
        ContractOutlierRule.objects.create(
            contract=self.contract,
            threshold_amount=Decimal("100.00"),
            threshold_scope="PER_CLAIM",
            reimbursement_percentage=Decimal("50.00"),
            priority=0,
            effective_start_date=date(2025, 7, 1),
            effective_end_date=None,
        )
        claim = self._create_claim(
            date(2025, 6, 15),
            [("99213", Decimal("200.00"))],
        )
        result = self.engine.calculate_claim(claim)
        # Rule not active on 2025-06-15
        self.assertEqual(result.status, PricingStatus.SUCCESS)
        self.assertEqual(result.total_allowed, Decimal("150.00"))

    def test_effective_end_before_service_date_excluded(self):
        ContractOutlierRule.objects.create(
            contract=self.contract,
            threshold_amount=Decimal("100.00"),
            threshold_scope="PER_CLAIM",
            reimbursement_percentage=Decimal("50.00"),
            priority=0,
            effective_start_date=date(2025, 1, 1),
            effective_end_date=date(2025, 5, 1),
        )
        claim = self._create_claim(
            date(2025, 6, 15),
            [("99213", Decimal("200.00"))],
        )
        result = self.engine.calculate_claim(claim)
        self.assertEqual(result.status, PricingStatus.SUCCESS)
        self.assertEqual(result.total_allowed, Decimal("150.00"))

    def test_effective_range_includes_service_date(self):
        ContractOutlierRule.objects.create(
            contract=self.contract,
            threshold_amount=Decimal("100.00"),
            threshold_scope="PER_CLAIM",
            reimbursement_percentage=Decimal("50.00"),
            priority=0,
            effective_start_date=date(2025, 1, 1),
            effective_end_date=date(2025, 12, 31),
        )
        claim = self._create_claim(
            date(2025, 6, 15),
            [("99213", Decimal("200.00"))],
        )
        result = self.engine.calculate_claim(claim)
        self.assertEqual(result.status, PricingStatus.OUTLIER_APPLIED)
        self.assertEqual(result.total_allowed, Decimal("100.00"))


class TestOutlierShortCircuit(OutlierTestMixin, TestCase):
    """Stop after first applicable rule; no second rule applied."""

    def test_short_circuit_after_first_match(self):
        # First rule (priority 10): threshold 200, 30%. Second (priority 0): threshold 100, 80%.
        # total_billed = 300. First rule triggers -> 90. Second rule must not run.
        ContractOutlierRule.objects.create(
            contract=self.contract,
            threshold_amount=Decimal("100.00"),
            threshold_scope="PER_CLAIM",
            reimbursement_percentage=Decimal("80.00"),
            priority=0,
            effective_start_date=date(2025, 1, 1),
        )
        ContractOutlierRule.objects.create(
            contract=self.contract,
            threshold_amount=Decimal("200.00"),
            threshold_scope="PER_CLAIM",
            reimbursement_percentage=Decimal("30.00"),
            priority=10,
            effective_start_date=date(2025, 1, 1),
        )
        claim = self._create_claim(
            date(2025, 6, 15),
            [("99213", Decimal("150.00")), ("99213", Decimal("150.00"))],
        )
        result = self.engine.calculate_claim(claim)
        self.assertEqual(result.status, PricingStatus.OUTLIER_APPLIED)
        # Only first (priority 10): 300 * 0.30 = 90
        self.assertEqual(result.total_allowed, Decimal("90.00"))
