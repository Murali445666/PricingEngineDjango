"""Phase 7: Contract stop-loss rules — cost-based, evaluated before outlier."""
from datetime import date
from decimal import Decimal

from django.test import TestCase

from core.models import (
    ProviderContract,
    ProviderOrganization,
    PayerNetwork,
    FeeSchedule,
    FeeScheduleRate,
    PricingRule,
    PricingRuleCondition,
    RefProcedureCode,
    ContractStopLossRule,
    ContractOutlierRule,
    ClaimHeader,
    ClaimLine,
)
from core.engine.orchestrator import PricingEngine
from core.engine.types import PricingStatus


class StopLossTestMixin:
    """Shared setup: contract with one RBRVS rule (99213 -> $150/line)."""

    def setUp(self):
        self.engine = PricingEngine()
        payer_org = ProviderOrganization.objects.create(
            organization_id="PAYER-SL", name="StopLoss Payer", tax_id="00-0000000"
        )
        provider_org = ProviderOrganization.objects.create(
            organization_id="PROV-SL", name="StopLoss Provider", tax_id="11-1111111"
        )
        network = PayerNetwork.objects.create(
            network_id="NET-SL", network_name="StopLoss Network", payer_org=payer_org
        )
        self.contract = ProviderContract.objects.create(
            contract_name="StopLoss Contract",
            legacy_contract_number="CONT-SL",
            status="ACTIVE",
            effective_start_date=date(2025, 1, 1),
            provider_org=provider_org,
            network=network,
        )
        fs = FeeSchedule.objects.create(name="StopLoss FS", effective_date=date(2025, 1, 1))
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
        """lines_data: list of (procedure_code, billed_amount, cost_amount=0, units=1, sequence).
        cost_amount can be omitted (default 0).
        """
        header = ClaimHeader.objects.create(
            contract=self.contract,
            service_date=service_date,
            claim_type="PROFESSIONAL",
        )
        for i, row in enumerate(lines_data):
            code = row[0]
            billed = row[1]
            cost = row[2] if len(row) > 2 else Decimal("0")
            units = row[3] if len(row) > 3 else 1
            seq = row[4] if len(row) > 4 else i
            ClaimLine.objects.create(
                claim=header,
                procedure_code=code,
                billed_amount=billed,
                cost_amount=cost,
                units=units,
                sequence=seq,
            )
        return header


class TestStopLossBelowThreshold(StopLossTestMixin, TestCase):
    """Below cost threshold → standard pricing."""

    def test_below_threshold_standard_pricing(self):
        ContractStopLossRule.objects.create(
            contract=self.contract,
            cost_threshold=Decimal("10000.00"),
            reimbursement_percentage=Decimal("80.00"),
            priority=0,
            effective_start_date=date(2025, 1, 1),
        )
        claim = self._create_claim(
            date(2025, 6, 15),
            [
                ("99213", Decimal("100.00"), Decimal("50.00")),
                ("99213", Decimal("200.00"), Decimal("100.00")),
            ],
        )
        result = self.engine.calculate_claim(claim)
        self.assertEqual(result.status, PricingStatus.SUCCESS)
        self.assertEqual(result.total_allowed, Decimal("300.00"))
        self.assertEqual(result.original_total_allowed, Decimal("300.00"))
        self.assertEqual(result.final_total_allowed, Decimal("300.00"))
        self.assertIsNone(result.applied_stop_loss_rule_id)
        self.assertIsNone(result.applied_outlier_rule_id)


class TestStopLossAboveThreshold(StopLossTestMixin, TestCase):
    """Above cost threshold → stop-loss payment calculated correctly."""

    def test_above_threshold_stoploss_payment(self):
        rule = ContractStopLossRule.objects.create(
            contract=self.contract,
            cost_threshold=Decimal("500.00"),
            reimbursement_percentage=Decimal("50.00"),
            priority=0,
            effective_start_date=date(2025, 1, 1),
        )
        # total_cost = 200 + 400 = 600. excess = 100. payment = 500 + 100*0.5 = 550
        claim = self._create_claim(
            date(2025, 6, 15),
            [
                ("99213", Decimal("300.00"), Decimal("200.00")),
                ("99213", Decimal("500.00"), Decimal("400.00")),
            ],
        )
        result = self.engine.calculate_claim(claim)
        self.assertEqual(result.status, PricingStatus.STOP_LOSS_APPLIED)
        self.assertEqual(result.total_allowed, Decimal("550.00"))
        self.assertEqual(result.original_total_allowed, Decimal("300.00"))
        self.assertEqual(result.final_total_allowed, Decimal("550.00"))
        self.assertEqual(result.applied_stop_loss_rule_id, rule.id)
        self.assertIsNone(result.applied_outlier_rule_id)
        self.assertTrue(any("STOP_LOSS_APPLIED" in t for t in result.claim_trace))


class TestStopLossPriorityOrdering(StopLossTestMixin, TestCase):
    """Higher priority rule wins when both could apply."""

    def test_priority_desc_first_match_wins(self):
        ContractStopLossRule.objects.create(
            contract=self.contract,
            cost_threshold=Decimal("2000.00"),
            reimbursement_percentage=Decimal("90.00"),
            priority=0,
            effective_start_date=date(2025, 1, 1),
        )
        high_priority_rule = ContractStopLossRule.objects.create(
            contract=self.contract,
            cost_threshold=Decimal("100.00"),
            reimbursement_percentage=Decimal("40.00"),
            priority=10,
            effective_start_date=date(2025, 1, 1),
        )
        # total_cost = 500. First rule (priority 10): excess=400, payment = 100 + 400*0.4 = 260
        claim = self._create_claim(
            date(2025, 6, 15),
            [
                ("99213", Decimal("200.00"), Decimal("200.00")),
                ("99213", Decimal("300.00"), Decimal("300.00")),
            ],
        )
        result = self.engine.calculate_claim(claim)
        self.assertEqual(result.status, PricingStatus.STOP_LOSS_APPLIED)
        self.assertEqual(result.applied_stop_loss_rule_id, high_priority_rule.id)
        self.assertEqual(result.final_total_allowed, Decimal("260.00"))


class TestStopLossEffectiveDating(StopLossTestMixin, TestCase):
    """Only rules valid for service_date apply."""

    def test_effective_start_after_service_date_excluded(self):
        ContractStopLossRule.objects.create(
            contract=self.contract,
            cost_threshold=Decimal("100.00"),
            reimbursement_percentage=Decimal("50.00"),
            priority=0,
            effective_start_date=date(2025, 8, 1),
        )
        claim = self._create_claim(
            date(2025, 6, 15),
            [("99213", Decimal("200.00"), Decimal("200.00"))],
        )
        result = self.engine.calculate_claim(claim)
        self.assertEqual(result.status, PricingStatus.SUCCESS)
        self.assertEqual(result.final_total_allowed, Decimal("150.00"))

    def test_effective_end_before_service_date_excluded(self):
        ContractStopLossRule.objects.create(
            contract=self.contract,
            cost_threshold=Decimal("100.00"),
            reimbursement_percentage=Decimal("50.00"),
            priority=0,
            effective_start_date=date(2025, 1, 1),
            effective_end_date=date(2025, 5, 1),
        )
        claim = self._create_claim(
            date(2025, 6, 15),
            [("99213", Decimal("200.00"), Decimal("200.00"))],
        )
        result = self.engine.calculate_claim(claim)
        self.assertEqual(result.status, PricingStatus.SUCCESS)
        self.assertEqual(result.final_total_allowed, Decimal("150.00"))


class TestStopLossBeforeOutlier(StopLossTestMixin, TestCase):
    """Stop-loss executes before outlier."""

    def test_stoploss_runs_first_then_outlier_can_override(self):
        stoploss_rule = ContractStopLossRule.objects.create(
            contract=self.contract,
            cost_threshold=Decimal("100.00"),
            reimbursement_percentage=Decimal("50.00"),
            priority=0,
            effective_start_date=date(2025, 1, 1),
        )
        outlier_rule = ContractOutlierRule.objects.create(
            contract=self.contract,
            threshold_amount=Decimal("200.00"),
            threshold_scope="PER_CLAIM",
            reimbursement_percentage=Decimal("30.00"),
            priority=0,
            effective_start_date=date(2025, 1, 1),
        )
        # total_cost=300 > 100 -> stoploss: 100 + 200*0.5 = 200. total_billed=400 > 200 -> outlier: 400*0.30 = 120.
        # Outlier overrides -> final = 120, status = OUTLIER_APPLIED, but stop-loss trace entry preserved.
        claim = self._create_claim(
            date(2025, 6, 15),
            [
                ("99213", Decimal("200.00"), Decimal("150.00")),
                ("99213", Decimal("200.00"), Decimal("150.00")),
            ],
        )
        result = self.engine.calculate_claim(claim)
        self.assertEqual(result.status, PricingStatus.OUTLIER_APPLIED)
        self.assertEqual(result.original_total_allowed, Decimal("300.00"))
        self.assertEqual(result.final_total_allowed, Decimal("120.00"))
        self.assertEqual(result.applied_outlier_rule_id, outlier_rule.id)
        self.assertEqual(result.applied_stop_loss_rule_id, stoploss_rule.id)
        self.assertTrue(any("STOP_LOSS_APPLIED" in t for t in result.claim_trace))
        self.assertTrue(any("OUTLIER_APPLIED" in t for t in result.claim_trace))


class TestStopLossAuditFields(StopLossTestMixin, TestCase):
    """Audit fields correctly populated."""

    def test_stoploss_audit_fields(self):
        rule = ContractStopLossRule.objects.create(
            contract=self.contract,
            cost_threshold=Decimal("100.00"),
            reimbursement_percentage=Decimal("50.00"),
            priority=0,
            effective_start_date=date(2025, 1, 1),
        )
        claim = self._create_claim(
            date(2025, 6, 15),
            [("99213", Decimal("200.00"), Decimal("150.00"))],
        )
        result = self.engine.calculate_claim(claim)
        self.assertEqual(result.status, PricingStatus.STOP_LOSS_APPLIED)
        self.assertEqual(result.original_total_allowed, Decimal("150.00"))
        self.assertEqual(result.final_total_allowed, Decimal("125.00"))  # 100 + 50*0.5
        self.assertEqual(result.applied_stop_loss_rule_id, rule.id)
        self.assertIsNone(result.applied_outlier_rule_id)
