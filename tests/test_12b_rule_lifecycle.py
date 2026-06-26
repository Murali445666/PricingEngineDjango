"""
Step 12b – Rule Lifecycle & Version Audit tests.

Covers:
  Service unit tests
    1.  DRAFT version → ACTIVE via activate_version.
    2.  Overlapping ACTIVE version auto-superseded when new one activates.
    3.  Audit record created for every transition.
    4.  Non-DRAFT version raises ValidationError on activate.
    5.  DRAFT → ARCHIVED via archive_version.
    6.  SUPERSEDED → ARCHIVED via archive_version.
    7.  ACTIVE version cannot be archived (raises ValidationError).
    8.  Rule object (ContractCarveout) DRAFT → ACTIVE via activate_rule.
    9.  Rule object cannot be activated if parent version is not ACTIVE.
    10. Rule object ACTIVE → SUPERSEDED via supersede_rule.
    11. Rule object cannot be archived if ACTIVE.
    12. Rule DRAFT → ARCHIVED via archive_rule.

  API tests
    13. POST activate/ returns 200 + new_status ACTIVE.
    14. POST activate/ on non-DRAFT returns 400.
    15. POST archive/ returns 200 + new_status ARCHIVED.
    16. POST archive/ on ACTIVE returns 400.
    17. GET /contract-versions/<id>/ includes audit_records.
    18. GET /contracts/<pk>/version-audit/ returns audit rows.
    19. 404 for unknown version id.

  Resolver regression
    20. Only ACTIVE versions are returned by resolve_active_contract_version.
    21. DRAFT versions are never resolved.
    22. SUPERSEDED versions are never resolved.
"""
import os
import django
from datetime import date, timedelta
from decimal import Decimal

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
try:
    django.setup()
except RuntimeError:
    pass

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from core.models import (
    ProviderOrganization,
    PayerNetwork,
    ProviderContract,
    ContractVersion,
    ContractVersionAudit,
    ContractCarveout,
    FeeSchedule,
    ContractMethodology,
)
from core.services.rule_lifecycle_service import RuleLifecycleService
from core.engine.loader import resolve_active_contract_version


# ---------------------------------------------------------------------------
# Shared factory helpers
# ---------------------------------------------------------------------------

_counter = 0


def _make_contract(name="LC Contract") -> ProviderContract:
    global _counter
    _counter += 1
    n = _counter
    payer_org = ProviderOrganization.objects.create(
        organization_id=f"LC-PAYER-{n:04d}", name=f"LC Payer {n}"
    )
    network = PayerNetwork.objects.create(
        network_id=f"LC-NET-{n:04d}", network_name=f"LC Net {n}", payer_org=payer_org
    )
    prov_org = ProviderOrganization.objects.create(
        organization_id=f"LC-PROV-{n:04d}", name=f"LC Prov {n}"
    )
    return ProviderContract.objects.create(
        contract_name=name,
        status="ACTIVE",
        effective_start_date=date(2025, 1, 1),
        provider_org=prov_org,
        network=network,
    )


def _make_version(contract, version_number=1, status="DRAFT",
                  start=date(2025, 1, 1), end=None) -> ContractVersion:
    return ContractVersion.objects.create(
        contract=contract,
        version_number=version_number,
        status=status,
        effective_start_date=start,
        effective_end_date=end,
    )


def _make_carveout(version, status="DRAFT") -> ContractCarveout:
    return ContractCarveout.objects.create(
        version=version,
        code_type="CPT",
        code_value="99213",
        carveout_methodology="EXCLUDE",
        status=status,
    )


# ---------------------------------------------------------------------------
# Service: activate_version
# ---------------------------------------------------------------------------

class TestActivateVersion(TestCase):

    def setUp(self):
        self.contract = _make_contract("Activate Contract")
        self.v1 = _make_version(self.contract, version_number=1, status="DRAFT")

    def test_draft_to_active(self):
        RuleLifecycleService.activate_version(self.v1.version_id)
        self.v1.refresh_from_db()
        self.assertEqual(self.v1.status, "ACTIVE")

    def test_audit_record_created(self):
        RuleLifecycleService.activate_version(self.v1.version_id)
        audit = ContractVersionAudit.objects.filter(version=self.v1).first()
        self.assertIsNotNone(audit)
        self.assertEqual(audit.change_type, "ACTIVATED")
        self.assertEqual(audit.previous_status, "DRAFT")
        self.assertEqual(audit.new_status, "ACTIVE")

    def test_non_draft_raises_error(self):
        self.v1.status = "ACTIVE"
        self.v1.save()
        with self.assertRaises(ValidationError):
            RuleLifecycleService.activate_version(self.v1.version_id)

    def test_overlapping_active_is_superseded(self):
        # v_old is already ACTIVE and overlaps with v1
        v_old = _make_version(
            self.contract, version_number=0, status="ACTIVE",
            start=date(2025, 1, 1), end=None,
        )
        RuleLifecycleService.activate_version(self.v1.version_id)
        v_old.refresh_from_db()
        self.assertEqual(v_old.status, "SUPERSEDED")

    def test_supersede_audit_record_created_for_old_version(self):
        v_old = _make_version(
            self.contract, version_number=0, status="ACTIVE",
            start=date(2025, 1, 1), end=None,
        )
        RuleLifecycleService.activate_version(self.v1.version_id)
        supersede_audit = ContractVersionAudit.objects.filter(
            version=v_old, change_type="SUPERSEDED"
        ).first()
        self.assertIsNotNone(supersede_audit)
        self.assertEqual(supersede_audit.metadata.get("superseded_by_version"), self.v1.version_id)

    def test_non_overlapping_active_not_superseded(self):
        """A version with dates that do NOT overlap the new version must stay ACTIVE."""
        v_old = _make_version(
            self.contract, version_number=0, status="ACTIVE",
            start=date(2023, 1, 1), end=date(2024, 12, 31),  # past; no overlap with 2025
        )
        RuleLifecycleService.activate_version(self.v1.version_id)
        v_old.refresh_from_db()
        self.assertEqual(v_old.status, "ACTIVE")


# ---------------------------------------------------------------------------
# Service: archive_version
# ---------------------------------------------------------------------------

class TestArchiveVersion(TestCase):

    def setUp(self):
        self.contract = _make_contract("Archive Contract")

    def test_draft_to_archived(self):
        v = _make_version(self.contract, status="DRAFT")
        RuleLifecycleService.archive_version(v.version_id)
        v.refresh_from_db()
        self.assertEqual(v.status, "ARCHIVED")

    def test_superseded_to_archived(self):
        v = _make_version(self.contract, status="SUPERSEDED")
        RuleLifecycleService.archive_version(v.version_id)
        v.refresh_from_db()
        self.assertEqual(v.status, "ARCHIVED")

    def test_active_cannot_be_archived(self):
        v = _make_version(self.contract, status="ACTIVE")
        with self.assertRaises(ValidationError):
            RuleLifecycleService.archive_version(v.version_id)

    def test_audit_record_created(self):
        v = _make_version(self.contract, status="DRAFT")
        RuleLifecycleService.archive_version(v.version_id)
        audit = ContractVersionAudit.objects.filter(version=v, change_type="ARCHIVED").first()
        self.assertIsNotNone(audit)
        self.assertEqual(audit.new_status, "ARCHIVED")


# ---------------------------------------------------------------------------
# Service: activate_rule / supersede_rule / archive_rule
# ---------------------------------------------------------------------------

class TestRuleObjectLifecycle(TestCase):

    def setUp(self):
        self.contract = _make_contract("Rule Lifecycle Contract")
        self.active_version = _make_version(self.contract, status="ACTIVE")
        self.draft_version = _make_version(self.contract, version_number=2, status="DRAFT")

    def test_activate_rule_with_active_version(self):
        carveout = _make_carveout(self.active_version, status="DRAFT")
        RuleLifecycleService.activate_rule(carveout)
        carveout.refresh_from_db()
        self.assertEqual(carveout.status, "ACTIVE")

    def test_activate_rule_fails_if_version_not_active(self):
        carveout = _make_carveout(self.draft_version, status="DRAFT")
        with self.assertRaises(ValidationError):
            RuleLifecycleService.activate_rule(carveout)

    def test_activate_rule_fails_if_already_active(self):
        carveout = _make_carveout(self.active_version, status="ACTIVE")
        with self.assertRaises(ValidationError):
            RuleLifecycleService.activate_rule(carveout)

    def test_supersede_rule(self):
        carveout = _make_carveout(self.active_version, status="ACTIVE")
        RuleLifecycleService.supersede_rule(carveout)
        carveout.refresh_from_db()
        self.assertEqual(carveout.status, "SUPERSEDED")

    def test_supersede_rule_fails_if_not_active(self):
        carveout = _make_carveout(self.active_version, status="DRAFT")
        with self.assertRaises(ValidationError):
            RuleLifecycleService.supersede_rule(carveout)

    def test_archive_rule(self):
        carveout = _make_carveout(self.active_version, status="DRAFT")
        RuleLifecycleService.archive_rule(carveout)
        carveout.refresh_from_db()
        self.assertEqual(carveout.status, "ARCHIVED")

    def test_archive_rule_fails_if_active(self):
        carveout = _make_carveout(self.active_version, status="ACTIVE")
        with self.assertRaises(ValidationError):
            RuleLifecycleService.archive_rule(carveout)

    def test_activate_rule_writes_audit_row(self):
        carveout = _make_carveout(self.active_version, status="DRAFT")
        RuleLifecycleService.activate_rule(carveout)
        audit = ContractVersionAudit.objects.filter(
            version=self.active_version,
            change_type="ACTIVATED",
        ).first()
        self.assertIsNotNone(audit)
        self.assertEqual(audit.metadata.get("rule_type"), "ContractCarveout")


# ---------------------------------------------------------------------------
# API tests
# ---------------------------------------------------------------------------

class TestVersionLifecycleAPI(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.contract = _make_contract("API Lifecycle Contract")
        self.draft_v = _make_version(self.contract, version_number=1, status="DRAFT")
        self.active_v = _make_version(self.contract, version_number=0, status="ACTIVE",
                                      start=date(2023, 1, 1), end=date(2024, 12, 31))

    def test_activate_returns_200_and_active_status(self):
        url = reverse("api-contract-version-activate", kwargs={"pk": self.draft_v.version_id})
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["new_status"], "ACTIVE")
        self.draft_v.refresh_from_db()
        self.assertEqual(self.draft_v.status, "ACTIVE")

    def test_activate_non_draft_returns_400(self):
        url = reverse("api-contract-version-activate", kwargs={"pk": self.active_v.version_id})
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 400)

    def test_archive_draft_returns_200(self):
        url = reverse("api-contract-version-archive", kwargs={"pk": self.draft_v.version_id})
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["new_status"], "ARCHIVED")

    def test_archive_active_returns_400(self):
        url = reverse("api-contract-version-archive", kwargs={"pk": self.active_v.version_id})
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 400)

    def test_activate_unknown_id_returns_404(self):
        url = reverse("api-contract-version-activate", kwargs={"pk": 99999})
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 404)

    def test_version_detail_includes_audit_records(self):
        RuleLifecycleService.activate_version(self.draft_v.version_id)
        url = reverse("api-contract-version-detail", kwargs={"pk": self.draft_v.version_id})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("audit_records", resp.data)
        self.assertGreater(len(resp.data["audit_records"]), 0)

    def test_contract_version_audit_endpoint(self):
        RuleLifecycleService.activate_version(self.draft_v.version_id)
        url = reverse("api-contract-version-audit", kwargs={"pk": self.contract.pk})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertGreater(len(resp.data), 0)
        row = resp.data[0]
        for field in ("id", "version", "change_type", "previous_status", "new_status", "timestamp"):
            self.assertIn(field, row)


# ---------------------------------------------------------------------------
# Resolver regression
# ---------------------------------------------------------------------------

class TestResolverOnlyReturnsActiveVersions(TestCase):
    """
    Confirm that the pricing resolver's version filter works correctly.
    This test makes NO changes to pricing math; it only exercises
    resolve_active_contract_version() which is used by the engine.
    """

    def setUp(self):
        self.contract = _make_contract("Resolver Regression Contract")
        self.service_date = date(2025, 6, 15)

    def test_active_version_resolved(self):
        v = _make_version(self.contract, status="ACTIVE",
                          start=date(2025, 1, 1), end=None)
        resolved = resolve_active_contract_version(self.contract, self.service_date)
        self.assertIsNotNone(resolved)
        self.assertEqual(resolved.version_id, v.version_id)

    def test_draft_version_not_resolved(self):
        _make_version(self.contract, status="DRAFT",
                      start=date(2025, 1, 1), end=None)
        resolved = resolve_active_contract_version(self.contract, self.service_date)
        self.assertIsNone(resolved)

    def test_superseded_version_not_resolved(self):
        _make_version(self.contract, status="SUPERSEDED",
                      start=date(2025, 1, 1), end=None)
        resolved = resolve_active_contract_version(self.contract, self.service_date)
        self.assertIsNone(resolved)

    def test_archived_version_not_resolved(self):
        _make_version(self.contract, status="ARCHIVED",
                      start=date(2025, 1, 1), end=None)
        resolved = resolve_active_contract_version(self.contract, self.service_date)
        self.assertIsNone(resolved)

    def test_no_version_returns_none(self):
        resolved = resolve_active_contract_version(self.contract, self.service_date)
        self.assertIsNone(resolved)

    def test_lifecycle_service_not_imported_in_pricing_modules(self):
        """Structural guard: RuleLifecycleService must not appear in pricing path."""
        import importlib, inspect

        pricing_modules = [
            "core.engine.service",
            "core.engine.orchestrator",
            "core.engine.resolver",
            "core.engine.loader",
        ]
        for mod_name in pricing_modules:
            try:
                mod = importlib.import_module(mod_name)
            except ModuleNotFoundError:
                continue
            source = inspect.getsource(mod)
            self.assertNotIn(
                "RuleLifecycleService", source,
                f"RuleLifecycleService must not appear in {mod_name}",
            )
