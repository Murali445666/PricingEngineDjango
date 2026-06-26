"""
Step 12c-2: Condition schema validation and model/API integration tests.
"""
from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APITestCase

from core.services.condition_validation_service import (
    validate_condition_schema,
    ALLOWED_CONDITION_FIELDS,
    ALLOWED_OPERATORS,
    LOGICAL_OPERATORS,
)
from core.models import (
    ProviderContract,
    ProviderOrganization,
    PayerNetwork,
    ContractVersion,
    ContractMethodology,
    ContractCarveout,
    ContractCapFloor,
    ContractBlendingRule,
)


# ============================================================
# Part 1 – Unit tests for validate_condition_schema
# ============================================================

class TestValidateConditionSchemaNone(TestCase):
    def test_none_is_valid(self):
        validate_condition_schema(None)  # no raise


class TestValidateConditionSchemaValid(TestCase):
    def test_valid_and_single_condition_passes(self):
        payload = {
            "operator": "AND",
            "conditions": [
                {"field": "procedure_code", "op": "eq", "value": "99213"},
            ],
        }
        validate_condition_schema(payload)  # no raise

    def test_valid_or_multiple_conditions_passes(self):
        payload = {
            "operator": "OR",
            "conditions": [
                {"field": "billed_amount", "op": "gt", "value": 500},
                {"field": "claim_type", "op": "in", "value": ["INPATIENT", "OUTPATIENT"]},
            ],
        }
        validate_condition_schema(payload)  # no raise

    def test_units_int_and_decimal_value_passes(self):
        payload = {
            "operator": "AND",
            "conditions": [
                {"field": "units", "op": "gte", "value": 1},
                {"field": "billed_amount", "op": "lte", "value": "1000.50"},
            ],
        }
        validate_condition_schema(payload)  # no raise


class TestValidateConditionSchemaInvalidField(TestCase):
    def test_unknown_field_raises(self):
        payload = {
            "operator": "AND",
            "conditions": [
                {"field": "unknown_field", "op": "eq", "value": "x"},
            ],
        }
        with self.assertRaises(ValidationError) as ctx:
            validate_condition_schema(payload)
        self.assertIn("conditions", ctx.exception.message_dict)
        self.assertIn("Unknown field", str(ctx.exception.message_dict["conditions"]))


class TestValidateConditionSchemaInvalidOperator(TestCase):
    def test_unknown_op_raises(self):
        payload = {
            "operator": "AND",
            "conditions": [
                {"field": "procedure_code", "op": "like", "value": "99%"},
            ],
        }
        with self.assertRaises(ValidationError) as ctx:
            validate_condition_schema(payload)
        self.assertIn("conditions", ctx.exception.message_dict)


class TestValidateConditionSchemaWrongValueType(TestCase):
    def test_billed_amount_requires_numeric_raises(self):
        payload = {
            "operator": "AND",
            "conditions": [
                {"field": "billed_amount", "op": "gt", "value": "not_a_number"},
            ],
        }
        with self.assertRaises(ValidationError) as ctx:
            validate_condition_schema(payload)
        self.assertIn("conditions", ctx.exception.message_dict)

    def test_units_requires_int_raises(self):
        payload = {
            "operator": "AND",
            "conditions": [
                {"field": "units", "op": "eq", "value": "three"},
            ],
        }
        with self.assertRaises(ValidationError) as ctx:
            validate_condition_schema(payload)
        self.assertIn("conditions", ctx.exception.message_dict)

    def test_in_requires_list_raises(self):
        payload = {
            "operator": "AND",
            "conditions": [
                {"field": "claim_type", "op": "in", "value": "INPATIENT"},
            ],
        }
        with self.assertRaises(ValidationError) as ctx:
            validate_condition_schema(payload)
        self.assertIn("conditions", ctx.exception.message_dict)


class TestValidateConditionSchemaStructure(TestCase):
    def test_missing_operator_raises(self):
        payload = {"conditions": [{"field": "procedure_code", "op": "eq", "value": "x"}]}
        with self.assertRaises(ValidationError) as ctx:
            validate_condition_schema(payload)
        self.assertIn("conditions", ctx.exception.message_dict)

    def test_missing_conditions_key_raises(self):
        payload = {"operator": "AND"}
        with self.assertRaises(ValidationError) as ctx:
            validate_condition_schema(payload)
        self.assertIn("conditions", ctx.exception.message_dict)

    def test_empty_conditions_list_raises(self):
        payload = {"operator": "AND", "conditions": []}
        with self.assertRaises(ValidationError) as ctx:
            validate_condition_schema(payload)
        self.assertIn("conditions", ctx.exception.message_dict)

    def test_invalid_logical_operator_raises(self):
        payload = {"operator": "XOR", "conditions": [{"field": "procedure_code", "op": "eq", "value": "x"}]}
        with self.assertRaises(ValidationError) as ctx:
            validate_condition_schema(payload)
        self.assertIn("conditions", ctx.exception.message_dict)

    def test_condition_missing_field_op_value_raises(self):
        payload = {"operator": "AND", "conditions": [{"field": "procedure_code"}]}
        with self.assertRaises(ValidationError) as ctx:
            validate_condition_schema(payload)
        self.assertIn("conditions", ctx.exception.message_dict)

    def test_nested_group_rejected(self):
        # Nested object with operator/conditions instead of field/op/value
        payload = {
            "operator": "AND",
            "conditions": [
                {"operator": "OR", "conditions": [{"field": "procedure_code", "op": "eq", "value": "x"}]},
            ],
        }
        with self.assertRaises(ValidationError) as ctx:
            validate_condition_schema(payload)
        self.assertIn("conditions", ctx.exception.message_dict)


class TestValidateConditionSchemaConstants(TestCase):
    def test_allowed_fields_include_spec_and_claim_level(self):
        expected = {
            "procedure_code", "billed_amount", "units", "claim_type", "modifiers_count",
            "total_billed", "current_total",
        }
        self.assertEqual(set(ALLOWED_CONDITION_FIELDS.keys()), expected)

    def test_allowed_operators_match_spec(self):
        expected = {"eq", "neq", "gt", "gte", "lt", "lte", "in", "not_in"}
        self.assertEqual(ALLOWED_OPERATORS, expected)

    def test_logical_operators_are_and_or(self):
        self.assertEqual(LOGICAL_OPERATORS, {"AND", "OR"})


# ============================================================
# Part 2 – Model clean() integration
# ============================================================

def _make_contract_and_version():
    payer = ProviderOrganization.objects.create(
        organization_id="VAL-PAYER", name="Val Payer", tax_id="00-0000001"
    )
    prov = ProviderOrganization.objects.create(
        organization_id="VAL-PROV", name="Val Prov", tax_id="11-1111111"
    )
    net = PayerNetwork.objects.create(
        network_id="VAL-NET", network_name="Val Net", payer_org=payer
    )
    contract = ProviderContract.objects.create(
        contract_name="Val Contract",
        legacy_contract_number="VAL-C",
        status="ACTIVE",
        effective_start_date=date(2025, 1, 1),
        provider_org=prov,
        network=net,
    )
    version = ContractVersion.objects.create(
        contract=contract,
        version_number=1,
        effective_start_date=date(2025, 1, 1),
        status=ContractVersion.VersionStatus.ACTIVE,
    )
    return contract, version


class TestContractMethodologyCleanBlocksInvalidSchema(TestCase):
    def test_full_clean_raises_on_invalid_conditions(self):
        contract, _ = _make_contract_and_version()
        m = ContractMethodology(
            contract=contract,
            methodology_type="RBRVS",
            effective_date=date(2025, 1, 1),
            conditions={"operator": "AND", "conditions": [{"field": "bad_field", "op": "eq", "value": "x"}]},
        )
        with self.assertRaises(ValidationError):
            m.full_clean()

    def test_full_clean_passes_with_null_conditions(self):
        contract, _ = _make_contract_and_version()
        m = ContractMethodology(
            contract=contract,
            methodology_type="RBRVS",
            effective_date=date(2025, 1, 1),
            conditions=None,
        )
        m.full_clean()  # no raise


class TestContractCarveoutCleanBlocksInvalidSchema(TestCase):
    def test_full_clean_raises_on_invalid_conditions(self):
        _, version = _make_contract_and_version()
        c = ContractCarveout(
            version=version,
            code_type="CPT",
            code_value="99213",
            carveout_methodology="EXCLUDE",
            conditions={"operator": "INVALID", "conditions": [{"field": "procedure_code", "op": "eq", "value": "x"}]},
        )
        with self.assertRaises(ValidationError):
            c.full_clean()


class TestContractCapFloorCleanBlocksInvalidSchema(TestCase):
    def test_full_clean_raises_on_invalid_conditions(self):
        _, version = _make_contract_and_version()
        cf = ContractCapFloor(
            version=version,
            scope="CLAIM",
            cap_type="CAP",
            value=Decimal("100.00"),
            priority=0,
            effective_start_date=date(2025, 1, 1),
            conditions={"operator": "AND", "conditions": []},
        )
        with self.assertRaises(ValidationError):
            cf.full_clean()

    def test_full_clean_passes_with_valid_schema(self):
        _, version = _make_contract_and_version()
        cf = ContractCapFloor(
            version=version,
            scope="CLAIM",
            cap_type="CAP",
            value=Decimal("100.00"),
            priority=0,
            effective_start_date=date(2025, 1, 1),
            conditions={
                "operator": "AND",
                "conditions": [{"field": "total_billed", "op": "gt", "value": 0}],
            },
        )
        # Note: build_claim_context uses total_billed, current_total, claim_type - not in ALLOWED_CONDITION_FIELDS
        # for validation service. So we use a field that IS allowed for cap/floor context. Actually the validation
        # allowlist is procedure_code, billed_amount, units, claim_type, modifiers_count - for line/claim context.
        # So for cap/floor we'd use claim_type or we need to add total_billed to the allowlist. Checking the spec:
        # ALLOWED_CONDITION_FIELDS = procedure_code, billed_amount, units, claim_type, modifiers_count.
        # So total_billed is NOT in the allowlist. So the valid schema for cap/floor would use claim_type or
        # total_billed - but the task said allowed fields are those five. So claim_type is allowed. Let me use
        # claim_type for the "valid" test.
        cf.conditions = {
            "operator": "AND",
            "conditions": [{"field": "claim_type", "op": "eq", "value": "PROFESSIONAL"}],
        }
        cf.full_clean()  # no raise


class TestContractBlendingRuleCleanBlocksInvalidSchema(TestCase):
    def test_full_clean_raises_on_invalid_conditions(self):
        _, version = _make_contract_and_version()
        br = ContractBlendingRule(
            version=version,
            scope="CLAIM",
            blend_type="ADD",
            blend_percentage=Decimal("10"),
            priority=0,
            effective_start_date=date(2025, 1, 1),
            conditions={"operator": "AND", "conditions": [{"field": "x", "op": "eq", "value": "y"}]},
        )
        with self.assertRaises(ValidationError):
            br.full_clean()


# ============================================================
# Part 3 – API tests (methodology create/update)
# ============================================================

class TestMethodologyConditionsAPI(APITestCase):
    def setUp(self):
        payer = ProviderOrganization.objects.create(
            organization_id="API-PAYER", name="API Payer", tax_id="00-0000002"
        )
        prov = ProviderOrganization.objects.create(
            organization_id="API-PROV", name="API Prov", tax_id="22-2222222"
        )
        net = PayerNetwork.objects.create(
            network_id="API-NET", network_name="API Net", payer_org=payer
        )
        self.contract = ProviderContract.objects.create(
            contract_name="API Contract",
            legacy_contract_number="API-C",
            status="ACTIVE",
            effective_start_date=date(2025, 1, 1),
            provider_org=prov,
            network=net,
        )

    def test_post_invalid_condition_returns_400(self):
        url = reverse("api-contract-methodologies", kwargs={"pk": self.contract.pk})
        payload = {
            "methodology_type": "RBRVS",
            "effective_date": "2025-01-01",
            "conditions": {
                "operator": "AND",
                "conditions": [{"field": "invalid_field", "op": "eq", "value": "x"}],
            },
        }
        response = self.client.post(url, payload, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("conditions", response.data)

    def test_post_valid_condition_saves_successfully(self):
        url = reverse("api-contract-methodologies", kwargs={"pk": self.contract.pk})
        payload = {
            "methodology_type": "FLAT_RATE",
            "effective_date": "2025-01-01",
            "conditions": {
                "operator": "AND",
                "conditions": [{"field": "procedure_code", "op": "eq", "value": "99213"}],
            },
        }
        response = self.client.post(url, payload, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data.get("conditions"), payload["conditions"])

    def test_post_null_conditions_saves_successfully(self):
        url = reverse("api-contract-methodologies", kwargs={"pk": self.contract.pk})
        payload = {
            "methodology_type": "RBRVS",
            "effective_date": "2025-01-01",
        }
        response = self.client.post(url, payload, format="json")
        self.assertEqual(response.status_code, 201)


# ============================================================
# Part 4 – Regression: pricing path unchanged
# ============================================================

class TestConditionValidationNoPricingImpact(TestCase):
    """Ensure validation service is not imported in pricing path."""

    def test_validate_condition_schema_not_imported_in_orchestrator(self):
        import core.engine.orchestrator as orch
        self.assertNotIn("validate_condition_schema", dir(orch))

    def test_conditions_module_has_evaluate_not_validate(self):
        import core.engine.conditions as cond_mod
        self.assertTrue(hasattr(cond_mod, "evaluate_conditions"))
        self.assertFalse(hasattr(cond_mod, "validate_condition_schema"))
