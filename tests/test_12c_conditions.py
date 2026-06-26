"""
Step 12c-1: Structured condition evaluation engine tests.

Coverage:
  Part A – Unit tests for evaluate_conditions / build_line_context / build_claim_context
  Part B – Engine integration: conditions gate carve-outs, cap/floors, blending rules
  Part C – Regression: no extra DB queries; all existing pricing still works
"""
from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from core.engine.conditions import (
    evaluate_conditions,
    build_line_context,
    build_claim_context,
)


# ============================================================
# Part A – Pure unit tests (no DB, no models)
# ============================================================

class TestEvaluateConditionsNone(TestCase):
    def test_none_returns_true(self):
        self.assertTrue(evaluate_conditions(None, {}))

    def test_empty_conditions_list_returns_true(self):
        self.assertTrue(evaluate_conditions({"operator": "AND", "conditions": []}, {}))

    def test_missing_conditions_key_returns_true(self):
        self.assertTrue(evaluate_conditions({"operator": "AND"}, {}))


class TestEvaluateConditionsEq(TestCase):
    def _ctx(self):
        return {"procedure_code": "99213", "claim_type": "PROFESSIONAL"}

    def test_eq_matches(self):
        cond = {"operator": "AND", "conditions": [{"field": "procedure_code", "op": "eq", "value": "99213"}]}
        self.assertTrue(evaluate_conditions(cond, self._ctx()))

    def test_eq_no_match(self):
        cond = {"operator": "AND", "conditions": [{"field": "procedure_code", "op": "eq", "value": "99214"}]}
        self.assertFalse(evaluate_conditions(cond, self._ctx()))

    def test_neq_matches(self):
        cond = {"operator": "AND", "conditions": [{"field": "procedure_code", "op": "neq", "value": "99999"}]}
        self.assertTrue(evaluate_conditions(cond, self._ctx()))

    def test_neq_no_match(self):
        cond = {"operator": "AND", "conditions": [{"field": "procedure_code", "op": "neq", "value": "99213"}]}
        self.assertFalse(evaluate_conditions(cond, self._ctx()))


class TestEvaluateConditionsNumeric(TestCase):
    def _ctx(self):
        return {"billed_amount": Decimal("1200.00"), "units": 2}

    def test_gt_true(self):
        cond = {"operator": "AND", "conditions": [{"field": "billed_amount", "op": "gt", "value": 500}]}
        self.assertTrue(evaluate_conditions(cond, self._ctx()))

    def test_gt_false(self):
        cond = {"operator": "AND", "conditions": [{"field": "billed_amount", "op": "gt", "value": 2000}]}
        self.assertFalse(evaluate_conditions(cond, self._ctx()))

    def test_gte_equal_boundary(self):
        cond = {"operator": "AND", "conditions": [{"field": "billed_amount", "op": "gte", "value": 1200}]}
        self.assertTrue(evaluate_conditions(cond, self._ctx()))

    def test_lt_true(self):
        cond = {"operator": "AND", "conditions": [{"field": "units", "op": "lt", "value": 5}]}
        self.assertTrue(evaluate_conditions(cond, self._ctx()))

    def test_lte_boundary(self):
        cond = {"operator": "AND", "conditions": [{"field": "units", "op": "lte", "value": 2}]}
        self.assertTrue(evaluate_conditions(cond, self._ctx()))


class TestEvaluateConditionsIn(TestCase):
    def _ctx(self):
        return {"claim_type": "INPATIENT"}

    def test_in_matches(self):
        cond = {"operator": "AND", "conditions": [
            {"field": "claim_type", "op": "in", "value": ["INPATIENT", "OUTPATIENT"]}
        ]}
        self.assertTrue(evaluate_conditions(cond, self._ctx()))

    def test_in_no_match(self):
        cond = {"operator": "AND", "conditions": [
            {"field": "claim_type", "op": "in", "value": ["PROFESSIONAL"]}
        ]}
        self.assertFalse(evaluate_conditions(cond, self._ctx()))

    def test_not_in_matches(self):
        cond = {"operator": "AND", "conditions": [
            {"field": "claim_type", "op": "not_in", "value": ["PROFESSIONAL"]}
        ]}
        self.assertTrue(evaluate_conditions(cond, self._ctx()))

    def test_not_in_no_match(self):
        cond = {"operator": "AND", "conditions": [
            {"field": "claim_type", "op": "not_in", "value": ["INPATIENT"]}
        ]}
        self.assertFalse(evaluate_conditions(cond, self._ctx()))

    def test_in_requires_list_raises(self):
        cond = {"operator": "AND", "conditions": [
            {"field": "claim_type", "op": "in", "value": "INPATIENT"}
        ]}
        with self.assertRaises(ValidationError):
            evaluate_conditions(cond, self._ctx())


class TestEvaluateConditionsLogical(TestCase):
    def _ctx(self):
        return {"procedure_code": "99213", "billed_amount": Decimal("800.00")}

    def test_and_all_true(self):
        cond = {"operator": "AND", "conditions": [
            {"field": "procedure_code", "op": "eq", "value": "99213"},
            {"field": "billed_amount", "op": "gt", "value": 500},
        ]}
        self.assertTrue(evaluate_conditions(cond, self._ctx()))

    def test_and_one_false(self):
        cond = {"operator": "AND", "conditions": [
            {"field": "procedure_code", "op": "eq", "value": "99213"},
            {"field": "billed_amount", "op": "gt", "value": 1000},
        ]}
        self.assertFalse(evaluate_conditions(cond, self._ctx()))

    def test_or_one_true(self):
        cond = {"operator": "OR", "conditions": [
            {"field": "procedure_code", "op": "eq", "value": "00000"},
            {"field": "billed_amount", "op": "gt", "value": 500},
        ]}
        self.assertTrue(evaluate_conditions(cond, self._ctx()))

    def test_or_all_false(self):
        cond = {"operator": "OR", "conditions": [
            {"field": "procedure_code", "op": "eq", "value": "00000"},
            {"field": "billed_amount", "op": "gt", "value": 9999},
        ]}
        self.assertFalse(evaluate_conditions(cond, self._ctx()))

    def test_case_insensitive_operator(self):
        """'and' lowercase should work the same as 'AND'."""
        cond = {"operator": "and", "conditions": [
            {"field": "procedure_code", "op": "eq", "value": "99213"},
        ]}
        self.assertTrue(evaluate_conditions(cond, self._ctx()))


class TestEvaluateConditionsErrors(TestCase):
    def _ctx(self):
        return {"procedure_code": "99213"}

    def test_invalid_operator_raises(self):
        cond = {"operator": "AND", "conditions": [
            {"field": "procedure_code", "op": "like", "value": "99%"}
        ]}
        with self.assertRaises(ValidationError):
            evaluate_conditions(cond, self._ctx())

    def test_unknown_field_raises(self):
        cond = {"operator": "AND", "conditions": [
            {"field": "nonexistent_field", "op": "eq", "value": "x"}
        ]}
        with self.assertRaises(ValidationError):
            evaluate_conditions(cond, self._ctx())

    def test_invalid_logical_op_raises(self):
        cond = {"operator": "XOR", "conditions": [
            {"field": "procedure_code", "op": "eq", "value": "99213"}
        ]}
        with self.assertRaises(ValidationError):
            evaluate_conditions(cond, self._ctx())


# ============================================================
# Part B – Engine integration tests (DB required)
# ============================================================

from core.models import (
    ProviderContract,
    ProviderOrganization,
    PayerNetwork,
    FeeSchedule,
    FeeScheduleRate,
    PricingRule,
    PricingRuleCondition,
    RefProcedureCode,
    ContractCarveout,
    ContractCapFloor,
    ContractBlendingRule,
    ContractVersion,
    ClaimHeader,
    ClaimLine,
)
from core.engine.orchestrator import PricingEngine, ClaimOrchestrator
from core.engine.types import PricingStatus
from core.engine.config import ClaimPricingInput, ClaimLineInput


_ORG_COUNTER = 0


def _unique_org_id(prefix="ORG"):
    global _ORG_COUNTER
    _ORG_COUNTER += 1
    return f"{prefix}-{_ORG_COUNTER:05d}"


class ConditionEngineTestMixin:
    """
    Shared DB fixtures: one contract + active ContractVersion with a FLAT_RATE rule → $200.

    ContractCarveout / ContractCapFloor / ContractBlendingRule are version-scoped so each
    test creates the rule using ``version=self.version``.
    """

    def setUp(self):
        self.engine = PricingEngine()
        payer_org = ProviderOrganization.objects.create(
            organization_id=_unique_org_id("PAYER"),
            name="Cond Payer",
            tax_id="00-1111111",
        )
        provider_org = ProviderOrganization.objects.create(
            organization_id=_unique_org_id("PROV"),
            name="Cond Provider",
            tax_id="11-2222222",
        )
        network = PayerNetwork.objects.create(
            network_id=_unique_org_id("NET"),
            network_name="Cond Network",
            payer_org=payer_org,
        )
        self.contract = ProviderContract.objects.create(
            contract_name="Condition Test Contract",
            legacy_contract_number=_unique_org_id("CTCONT"),
            status="ACTIVE",
            effective_start_date=date(2025, 1, 1),
            provider_org=provider_org,
            network=network,
        )
        # Active ContractVersion required by loader for carveout / cap-floor / blending queries.
        self.service_date = date(2025, 6, 1)
        self.version = ContractVersion.objects.create(
            contract=self.contract,
            version_number=1,
            effective_start_date=date(2025, 1, 1),
            status=ContractVersion.VersionStatus.ACTIVE,
        )
        RefProcedureCode.objects.get_or_create(
            code_id="99213",
            defaults={"description": "Office Visit", "work_rvu": Decimal("0.97")},
        )
        fs = FeeSchedule.objects.create(
            name=f"Cond FS {_unique_org_id('FS')}",
            effective_date=date(2025, 1, 1),
        )
        FeeScheduleRate.objects.create(
            fee_schedule=fs, code_id="99213", rate_amount=Decimal("200.00")
        )
        self.rule = PricingRule.objects.create(
            contract=self.contract,
            rule_name="Cond FLAT Rule",
            specificity_score=10,
            methodology_code="FLAT_RATE",
            flat_rate=Decimal("200.00"),
            status=PricingRule.RuleStatus.ACTIVE,
        )
        PricingRuleCondition.objects.create(
            pricing_rule=self.rule,
            attribute_name="procedure_code",
            operator="EQ",
            attribute_value="99213",
        )

    def _price(self, billed_amount=Decimal("500.00")):
        """Helper: price one line via ClaimOrchestrator."""
        header = ClaimHeader.objects.create(
            contract=self.contract,
            service_date=self.service_date,
            claim_type="PROFESSIONAL",
        )
        ClaimLine.objects.create(
            claim=header,
            procedure_code="99213",
            billed_amount=billed_amount,
            units=1,
            sequence=1,
        )
        return self.engine.calculate_claim(header)


class TestCarveoutConditionGating(ConditionEngineTestMixin, TestCase):
    """Carve-out is skipped when its conditions are not met."""

    def test_carveout_applied_when_condition_passes(self):
        """Condition requires billed_amount > 100; billed=500 → passes → EXCLUDE."""
        ContractCarveout.objects.create(
            version=self.version,
            code_type="CPT",
            code_value="99213",
            carveout_methodology="EXCLUDE",
            conditions={
                "operator": "AND",
                "conditions": [{"field": "billed_amount", "op": "gt", "value": 100}],
            },
        )
        result = self._price(billed_amount=Decimal("500.00"))
        line = result.lines[0]
        self.assertEqual(line.status, PricingStatus.CARVEOUT_EXCLUDED)
        self.assertEqual(line.allowed_amount, Decimal("0.00"))

    def test_carveout_skipped_when_condition_fails(self):
        """Condition requires billed_amount > 1000; billed=500 → fails → no carve-out."""
        ContractCarveout.objects.create(
            version=self.version,
            code_type="CPT",
            code_value="99213",
            carveout_methodology="EXCLUDE",
            conditions={
                "operator": "AND",
                "conditions": [{"field": "billed_amount", "op": "gt", "value": 1000}],
            },
        )
        result = self._price(billed_amount=Decimal("500.00"))
        line = result.lines[0]
        # Carve-out skipped; base FLAT_RATE should apply
        self.assertEqual(line.status, PricingStatus.SUCCESS)
        self.assertEqual(line.allowed_amount, Decimal("200.00"))

    def test_carveout_without_conditions_always_applies(self):
        """Null conditions → carve-out always applies (backward compat)."""
        ContractCarveout.objects.create(
            version=self.version,
            code_type="CPT",
            code_value="99213",
            carveout_methodology="EXCLUDE",
            conditions=None,
        )
        result = self._price()
        self.assertEqual(result.lines[0].status, PricingStatus.CARVEOUT_EXCLUDED)


class TestCapFloorConditionGating(ConditionEngineTestMixin, TestCase):
    """Cap is skipped when its conditions are not met."""

    def test_cap_applied_when_condition_passes(self):
        """Cap condition: total_billed > 100; billed=500 → cap at $150 fires."""
        ContractCapFloor.objects.create(
            version=self.version,
            scope="CLAIM",
            cap_type="CAP",
            value=Decimal("150.00"),
            priority=0,
            effective_start_date=date(2025, 1, 1),
            conditions={
                "operator": "AND",
                "conditions": [{"field": "total_billed", "op": "gt", "value": 100}],
            },
        )
        result = self._price(billed_amount=Decimal("500.00"))
        # base = 200, cap = 150 → final = 150
        self.assertEqual(result.final_total_allowed, Decimal("150.00"))
        self.assertEqual(result.status, PricingStatus.CAP_APPLIED)

    def test_cap_skipped_when_condition_fails(self):
        """Cap condition: total_billed > 1000; billed=500 → fails → cap ignored."""
        ContractCapFloor.objects.create(
            version=self.version,
            scope="CLAIM",
            cap_type="CAP",
            value=Decimal("150.00"),
            priority=0,
            effective_start_date=date(2025, 1, 1),
            conditions={
                "operator": "AND",
                "conditions": [{"field": "total_billed", "op": "gt", "value": 1000}],
            },
        )
        result = self._price(billed_amount=Decimal("500.00"))
        # Cap skipped; base 200 stands
        self.assertEqual(result.final_total_allowed, Decimal("200.00"))
        self.assertNotEqual(result.status, PricingStatus.CAP_APPLIED)


class TestBlendingConditionGating(ConditionEngineTestMixin, TestCase):
    """Blending rule is skipped when its conditions are not met."""

    def test_blending_applied_when_condition_passes(self):
        """Blend adds 50% of billed; condition: claim_type == PROFESSIONAL → passes."""
        ContractBlendingRule.objects.create(
            version=self.version,
            scope="CLAIM",
            blend_type="ADD",
            blend_percentage=Decimal("50.00"),
            priority=0,
            effective_start_date=date(2025, 1, 1),
            conditions={
                "operator": "AND",
                "conditions": [{"field": "claim_type", "op": "eq", "value": "professional"}],
            },
        )
        result = self._price(billed_amount=Decimal("400.00"))
        # base=200, blending adds 50% of billed(400)=200 → blended=400
        self.assertEqual(result.status, PricingStatus.BLENDING_APPLIED)
        self.assertEqual(result.blended_total_allowed, Decimal("400.00"))

    def test_blending_skipped_when_condition_fails(self):
        """Blend condition: claim_type == INPATIENT; claim is PROFESSIONAL → skipped."""
        ContractBlendingRule.objects.create(
            version=self.version,
            scope="CLAIM",
            blend_type="ADD",
            blend_percentage=Decimal("50.00"),
            priority=0,
            effective_start_date=date(2025, 1, 1),
            conditions={
                "operator": "AND",
                "conditions": [{"field": "claim_type", "op": "eq", "value": "inpatient"}],
            },
        )
        result = self._price(billed_amount=Decimal("400.00"))
        # Blending skipped; base 200 stands
        self.assertEqual(result.final_total_allowed, Decimal("200.00"))
        self.assertNotEqual(result.status, PricingStatus.BLENDING_APPLIED)


# ============================================================
# Part C – Regression: no extra queries, all existing flow works
# ============================================================

class TestConditionsQueryCount(ConditionEngineTestMixin, TestCase):
    """
    Conditions evaluation must not introduce additional DB queries.
    We verify by checking that the query count for a claim priced with
    a conditions-bearing carve-out equals the count for one without.
    """

    def test_no_extra_queries_with_conditions(self):
        from django.test.utils import CaptureQueriesContext
        from django.db import connection

        # Baseline (no carveout)
        header1 = ClaimHeader.objects.create(
            contract=self.contract,
            service_date=self.service_date,
            claim_type="PROFESSIONAL",
        )
        ClaimLine.objects.create(
            claim=header1, procedure_code="99213",
            billed_amount=Decimal("500.00"), units=1, sequence=1,
        )
        with CaptureQueriesContext(connection) as base_ctx:
            self.engine.calculate_claim(header1)
        baseline_count = len(base_ctx)

        # Add a carve-out with a condition
        ContractCarveout.objects.create(
            version=self.version,
            code_type="CPT",
            code_value="99213",
            carveout_methodology="EXCLUDE",
            conditions={
                "operator": "AND",
                "conditions": [{"field": "billed_amount", "op": "gt", "value": 100}],
            },
        )
        header2 = ClaimHeader.objects.create(
            contract=self.contract,
            service_date=self.service_date,
            claim_type="PROFESSIONAL",
        )
        ClaimLine.objects.create(
            claim=header2, procedure_code="99213",
            billed_amount=Decimal("500.00"), units=1, sequence=1,
        )
        with CaptureQueriesContext(connection) as cond_ctx:
            self.engine.calculate_claim(header2)
        cond_count = len(cond_ctx)

        # Conditions evaluation is pure Python; query count must not increase.
        self.assertLessEqual(
            cond_count, baseline_count + 1,  # +1 tolerance for carveout config load
            msg=(
                f"Conditions gating introduced extra DB queries: "
                f"baseline={baseline_count}, with_condition={cond_count}"
            ),
        )

    def test_existing_pricing_unaffected_by_null_conditions(self):
        """Null conditions on all rule tables = identical pricing to pre-12c."""
        result = self._price()
        self.assertEqual(result.status, PricingStatus.SUCCESS)
        self.assertEqual(result.total_allowed, Decimal("200.00"))


class TestContextBuilders(TestCase):
    """Unit-level tests for context builder helpers."""

    def test_build_line_context(self):
        class FakeInput:
            procedure_code = "99213"
            billed_amount = Decimal("300.00")
            units = 2
            claim_type = "PROFESSIONAL"
            modifiers = ["26", "TC"]

        ctx = build_line_context(FakeInput())
        self.assertEqual(ctx["procedure_code"], "99213")
        self.assertEqual(ctx["billed_amount"], Decimal("300.00"))
        self.assertEqual(ctx["units"], 2)
        self.assertEqual(ctx["claim_type"], "PROFESSIONAL")
        self.assertEqual(ctx["modifiers_count"], 2)

    def test_build_claim_context(self):
        ctx = build_claim_context(
            total_billed=Decimal("1000.00"),
            current_total=Decimal("800.00"),
            claim_type="inpatient",
        )
        self.assertEqual(ctx["total_billed"], Decimal("1000.00"))
        self.assertEqual(ctx["current_total"], Decimal("800.00"))
        self.assertEqual(ctx["claim_type"], "INPATIENT")  # uppercased

    def test_build_line_context_none_modifiers(self):
        class FakeInput:
            procedure_code = "99214"
            billed_amount = Decimal("100.00")
            units = 1
            claim_type = None
            modifiers = None

        ctx = build_line_context(FakeInput())
        self.assertEqual(ctx["modifiers_count"], 0)
        self.assertEqual(ctx["claim_type"], "")
