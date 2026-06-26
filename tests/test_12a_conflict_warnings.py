"""
Step 12a – Conflict Warnings Panel tests.

Covers:
  Unit tests
    1. GET returns only unresolved conflicts by default.
    2. GET ?all=1 returns both resolved and unresolved.
    3. PATCH resolve=true sets resolved=True.
    4. PATCH resolve=false un-resolves a resolved record.
    5. 404 for unknown contract.
    6. 404 for result_id that belongs to a different contract.

  API tests (via DRF test client)
    7. ContractConflictsView returns correct fields.
    8. ContractConflictResolveView updates resolved field.
    9. Contract list response includes open_error_count, open_warning_count.

  Regression tests
    10. pricing engine result unchanged after ValidationResult rows exist.
    11. ValidationService is NOT imported anywhere in pricing path.
"""
import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
try:
    django.setup()
except RuntimeError:
    pass

from datetime import date
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from core.models import (
    ProviderContract,
    ValidationResult,
    ProviderOrganization,
    PayerNetwork,
    PricingRule,
    ContractMethodology,
    FeeSchedule,
    ClaimHeader,
    ClaimLine,
)
from core.engine.service import ClaimPricingService
from core.engine.config import ClaimPricingInput, ClaimLineInput


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_obj_counter = 0

def _make_contract(name="Test Contract") -> ProviderContract:
    """
    Creates a minimal but fully valid ProviderContract:
      ProviderOrganization (payer) → PayerNetwork → ProviderOrganization (provider) → ProviderContract
    """
    global _obj_counter
    _obj_counter += 1
    n = _obj_counter

    payer_org = ProviderOrganization.objects.create(
        organization_id=f"PAYER-{n:04d}",
        name=f"Payer Org {n}",
    )
    network = PayerNetwork.objects.create(
        network_id=f"NET-{n:04d}",
        network_name=f"Network {n}",
        payer_org=payer_org,
    )
    provider_org = ProviderOrganization.objects.create(
        organization_id=f"PROV-{n:04d}",
        name=f"Provider Org {n}",
    )
    return ProviderContract.objects.create(
        contract_name=name,
        status="ACTIVE",
        effective_start_date=date(2025, 1, 1),
        provider_org=provider_org,
        network=network,
    )


def _make_result(contract, severity, resolved=False, conflict_type="SCOPE_OVERLAP"):
    return ValidationResult.objects.create(
        contract=contract,
        conflict_type=conflict_type,
        severity=severity,
        message=f"Test {severity} message",
        suggested_action="Fix it",
        resolved=resolved,
    )


# ---------------------------------------------------------------------------
# Unit: fetch & resolve
# ---------------------------------------------------------------------------

class TestConflictsModelAccess(TestCase):

    def setUp(self):
        self.contract = _make_contract("Unit Contract")
        self.error_open = _make_result(self.contract, "ERROR", resolved=False)
        self.warning_open = _make_result(self.contract, "WARNING", resolved=False)
        self.error_resolved = _make_result(self.contract, "ERROR", resolved=True)

    def test_filter_unresolved_returns_open_only(self):
        qs = ValidationResult.objects.filter(
            contract=self.contract, resolved=False
        )
        ids = list(qs.values_list("pk", flat=True))
        self.assertIn(self.error_open.pk, ids)
        self.assertIn(self.warning_open.pk, ids)
        self.assertNotIn(self.error_resolved.pk, ids)

    def test_filter_all_returns_every_record(self):
        qs = ValidationResult.objects.filter(contract=self.contract)
        self.assertEqual(qs.count(), 3)

    def test_resolve_mutation_sets_flag(self):
        self.error_open.resolved = True
        self.error_open.save()
        refreshed = ValidationResult.objects.get(pk=self.error_open.pk)
        self.assertTrue(refreshed.resolved)

    def test_unresolve_mutation_clears_flag(self):
        self.error_resolved.resolved = False
        self.error_resolved.save()
        refreshed = ValidationResult.objects.get(pk=self.error_resolved.pk)
        self.assertFalse(refreshed.resolved)


# ---------------------------------------------------------------------------
# API: GET /api/contracts/<pk>/conflicts/
# ---------------------------------------------------------------------------

class TestContractConflictsGetAPI(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.contract = _make_contract("API Contract")
        self.err = _make_result(self.contract, "ERROR")
        self.warn = _make_result(self.contract, "WARNING")
        _make_result(self.contract, "ERROR", resolved=True)  # should be excluded by default
        self.url = reverse("api-contract-conflicts", kwargs={"pk": self.contract.pk})

    def test_default_returns_only_unresolved(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        ids = [r["id"] for r in resp.data]
        self.assertIn(self.err.pk, ids)
        self.assertIn(self.warn.pk, ids)
        self.assertEqual(len(ids), 2, "Only two unresolved rows expected")

    def test_all_param_includes_resolved(self):
        resp = self.client.get(self.url + "?all=1")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data), 3)

    def test_response_contains_required_fields(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        row = resp.data[0]
        for field in ("id", "severity", "conflict_type", "message",
                      "affected_objects", "suggested_action", "validated_at", "resolved"):
            self.assertIn(field, row, f"Field '{field}' missing from response")

    def test_404_for_unknown_contract(self):
        url = reverse("api-contract-conflicts", kwargs={"pk": 99999})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 404)

    def test_empty_list_for_conflict_free_contract(self):
        clean_contract = _make_contract("Clean Contract")
        url = reverse("api-contract-conflicts", kwargs={"pk": clean_contract.pk})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data, [])


# ---------------------------------------------------------------------------
# API: PATCH /api/contracts/<pk>/conflicts/<result_id>/resolve/
# ---------------------------------------------------------------------------

class TestContractConflictResolveAPI(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.contract = _make_contract("Resolve Contract")
        self.result = _make_result(self.contract, "ERROR", resolved=False)
        self.url = reverse(
            "api-contract-conflict-resolve",
            kwargs={"pk": self.contract.pk, "result_id": self.result.pk},
        )

    def test_patch_marks_resolved_true(self):
        resp = self.client.patch(self.url, {"resolved": True}, format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.data["resolved"])
        self.result.refresh_from_db()
        self.assertTrue(self.result.resolved)

    def test_patch_can_unresolve(self):
        self.result.resolved = True
        self.result.save()
        resp = self.client.patch(self.url, {"resolved": False}, format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.data["resolved"])

    def test_404_for_wrong_contract(self):
        other = _make_contract("Other Contract")
        url = reverse(
            "api-contract-conflict-resolve",
            kwargs={"pk": other.pk, "result_id": self.result.pk},
        )
        resp = self.client.patch(url, {"resolved": True}, format="json")
        self.assertEqual(resp.status_code, 404)

    def test_404_for_unknown_result_id(self):
        url = reverse(
            "api-contract-conflict-resolve",
            kwargs={"pk": self.contract.pk, "result_id": 99999},
        )
        resp = self.client.patch(url, {"resolved": True}, format="json")
        self.assertEqual(resp.status_code, 404)


# ---------------------------------------------------------------------------
# API: Contract list includes open_error_count / open_warning_count
# ---------------------------------------------------------------------------

class TestContractListAnnotations(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.contract = _make_contract("Annotated Contract")
        _make_result(self.contract, "ERROR", resolved=False)
        _make_result(self.contract, "ERROR", resolved=False)
        _make_result(self.contract, "WARNING", resolved=False)
        _make_result(self.contract, "ERROR", resolved=True)   # should NOT count

    def test_error_count_excludes_resolved(self):
        resp = self.client.get(reverse("api-contract-list"))
        self.assertEqual(resp.status_code, 200)
        row = next(
            (r for r in resp.data if r["contract_id"] == self.contract.pk), None
        )
        self.assertIsNotNone(row, "Contract not found in list response")
        self.assertEqual(row["open_error_count"], 2)
        self.assertEqual(row["open_warning_count"], 1)

    def test_clean_contract_returns_zero_counts(self):
        clean = _make_contract("Clean Annotated")
        resp = self.client.get(reverse("api-contract-list"))
        row = next((r for r in resp.data if r["contract_id"] == clean.pk), None)
        self.assertIsNotNone(row)
        self.assertEqual(row["open_error_count"], 0)
        self.assertEqual(row["open_warning_count"], 0)


# ---------------------------------------------------------------------------
# Regression: pricing engine unaffected by ValidationResult rows
# ---------------------------------------------------------------------------

class TestPricingUnaffectedByConflictRecords(TestCase):
    """
    ValidationResult rows must never alter claim pricing output.
    This test prices a simple FLAT_RATE claim, creates a ValidationResult
    for the same contract, then re-prices and confirms identical totals.
    """

    def setUp(self):
        payer_org = ProviderOrganization.objects.create(
            organization_id="PAYER-REG-01", name="Regression Payer"
        )
        network = PayerNetwork.objects.create(
            network_id="NET-REG-01", network_name="Regression Network", payer_org=payer_org
        )
        provider_org = ProviderOrganization.objects.create(
            organization_id="PROV-REG-01", name="Regression Provider"
        )
        self.contract = ProviderContract.objects.create(
            contract_name="Regression Contract",
            status="ACTIVE",
            effective_start_date=date(2025, 1, 1),
            provider_org=provider_org,
            network=network,
        )
        fs = FeeSchedule.objects.create(name="Reg FS", version=1)
        ContractMethodology.objects.create(
            contract=self.contract,
            methodology_type="FLAT_RATE",
            base_percentage=Decimal("100.00"),
            effective_date=date(2024, 1, 1),
            fee_schedule=fs,
        )
        self.rule = PricingRule.objects.create(
            rule_name="Flat Rule",
            rule_type="BASE",
            methodology_code="FLAT_RATE",
            flat_rate=Decimal("50.00"),
            contract=self.contract,
            status="ACTIVE",
            effective_start_date=date(2024, 1, 1),
            specificity_score=10,
        )
        self.claim = ClaimHeader.objects.create(
            contract=self.contract,
            service_date=date(2025, 1, 15),
            claim_type="professional",
        )
        ClaimLine.objects.create(
            claim=self.claim,
            procedure_code="99213",
            billed_amount=Decimal("100.00"),
            units=1,
            cost_amount=Decimal("40.00"),
        )

    def _price(self):
        service = ClaimPricingService()
        inp = ClaimPricingInput(
            contract_id=self.contract.pk,
            service_date=self.claim.service_date,
            lines=[
                ClaimLineInput(
                    procedure_code="99213",
                    billed_amount=Decimal("100.00"),
                    units=1,
                )
            ],
        )
        return service.price_claim(inp)

    def test_pricing_unchanged_before_and_after_conflict_records(self):
        result_before = self._price()

        # Add a conflict record for this contract
        _make_result(self.contract, "ERROR")
        _make_result(self.contract, "WARNING")

        result_after = self._price()

        self.assertEqual(
            result_before.total_allowed,
            result_after.total_allowed,
            "Pricing total must not change when ValidationResult rows are present",
        )

    def test_validation_service_not_in_pricing_path(self):
        """
        Confirm ValidationService is not imported anywhere in the pricing engine modules.
        This is a structural guard — the service must remain validation-only.
        """
        pricing_modules = [
            "core.engine.service",
            "core.engine.orchestrator",
            "core.engine.resolver",
            "core.engine.loader",
            "core.engine.strategies.rbrvs",
            "core.engine.strategies.drg",
            "core.engine.strategies.apc",
            "core.engine.strategies.drug",
        ]
        import importlib
        import inspect

        for mod_name in pricing_modules:
            try:
                mod = importlib.import_module(mod_name)
            except ModuleNotFoundError:
                continue  # optional strategies not present in all envs
            source = inspect.getsource(mod)
            self.assertNotIn(
                "ValidationService",
                source,
                f"ValidationService must not appear in {mod_name}",
            )
