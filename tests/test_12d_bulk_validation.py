"""
Step 12d – Bulk contract validation API and ValidationService.bulk_validate.

API:
  - POST /api/validate-contracts/bulk/ — mixed clean + conflicted contracts; 200 + per-row shape.
  - Batch over cap returns 400.
  - ?save=1 persists ValidationResult rows.
"""
from unittest.mock import patch

import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
try:
    django.setup()
except RuntimeError:
    pass

from datetime import date

from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from core.models import (
    ProviderContract,
    ContractVersion,
    ContractMethodology,
    ValidationResult,
)
from core.services.validation_service import (
    ValidationService,
    BULK_VALIDATE_MAX_CONTRACT_IDS,
)


_obj_counter = 0


def _make_contract(name="Bulk Test Contract") -> ProviderContract:
    global _obj_counter
    from core.models import ProviderOrganization, PayerNetwork

    _obj_counter += 1
    n = _obj_counter
    payer_org = ProviderOrganization.objects.create(
        organization_id=f"12D-PAYER-{n:04d}",
        name=f"Payer {n}",
    )
    network = PayerNetwork.objects.create(
        network_id=f"12D-NET-{n:04d}",
        network_name=f"Net {n}",
        payer_org=payer_org,
    )
    provider_org = ProviderOrganization.objects.create(
        organization_id=f"12D-PROV-{n:04d}",
        name=f"Prov {n}",
    )
    return ProviderContract.objects.create(
        contract_name=name,
        status="ACTIVE",
        effective_start_date=date(2025, 1, 1),
        provider_org=provider_org,
        network=network,
    )


def _add_methodology_collision(contract: ProviderContract) -> None:
    """Two overlapping DRG methodologies on the same version → METHODOLOGY_COLLISION."""
    version = ContractVersion.objects.create(
        contract=contract,
        version_number=1,
        effective_start_date=date(2025, 1, 1),
        effective_end_date=None,
        status=ContractVersion.VersionStatus.DRAFT,
    )
    ContractMethodology.objects.create(
        contract=contract,
        version=version,
        methodology_type="DRG",
        effective_date=date(2025, 1, 1),
        termination_date=None,
        priority=0,
    )
    ContractMethodology.objects.create(
        contract=contract,
        version=version,
        methodology_type="DRG",
        effective_date=date(2025, 6, 1),
        termination_date=None,
        priority=0,
    )


class TestBulkValidateService(TestCase):

    def test_one_contract_exception_does_not_abort_others(self):
        a = _make_contract("Bulk A")
        b = _make_contract("Bulk B")

        _real = ValidationService.validate_contract

        def fake_validate(cid):
            if cid == a.pk:
                raise RuntimeError('simulated failure')
            return _real(cid)

        with patch.object(ValidationService, 'validate_contract', side_effect=fake_validate):
            rows = ValidationService.bulk_validate([a.pk, b.pk], persist=False)
        self.assertEqual(len(rows), 2)
        by_id = {r['contract_id']: r for r in rows}
        self.assertIn('errors', by_id[a.pk])
        self.assertIn('simulated failure', by_id[a.pk]['errors'])
        self.assertNotIn('errors', by_id[b.pk])

    def test_bulk_validate_mixed_contracts(self):
        clean = _make_contract("Clean bulk")
        dirty = _make_contract("Dirty bulk")
        _add_methodology_collision(dirty)
        rows = ValidationService.bulk_validate([clean.pk, dirty.pk], persist=False)
        self.assertEqual(len(rows), 2)
        by_id = {r["contract_id"]: r for r in rows}
        self.assertEqual(by_id[clean.pk]["error_count"], 0)
        self.assertEqual(by_id[clean.pk]["warning_count"], 0)
        self.assertEqual(by_id[clean.pk]["conflicts"], [])
        self.assertNotIn("errors", by_id[clean.pk])
        self.assertGreaterEqual(by_id[dirty.pk]["error_count"], 1)
        self.assertTrue(
            any(c["conflict_type"] == "METHODOLOGY_COLLISION" for c in by_id[dirty.pk]["conflicts"]),
        )

    def test_bulk_validate_persist_writes_validation_results(self):
        dirty = _make_contract("Persist bulk")
        _add_methodology_collision(dirty)
        ValidationService.bulk_validate([dirty.pk], persist=True)
        qs = ValidationResult.objects.filter(contract=dirty, resolved=False)
        self.assertGreater(qs.count(), 0)
        types = set(qs.values_list("conflict_type", flat=True))
        self.assertIn("METHODOLOGY_COLLISION", types)


@override_settings(ALLOWED_HOSTS=['testserver', 'localhost', '127.0.0.1'])
class TestValidateContractsBulkAPI(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.url = reverse("api-validate-contracts-bulk")

    def test_happy_path_two_contracts(self):
        clean = _make_contract("API clean")
        dirty = _make_contract("API dirty")
        _add_methodology_collision(dirty)
        resp = self.client.post(
            self.url,
            {"contract_ids": [clean.pk, dirty.pk]},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data), 2)
        by_id = {row["contract_id"]: row for row in resp.data}
        self.assertEqual(by_id[clean.pk]["error_count"], 0)
        self.assertEqual(by_id[clean.pk]["warning_count"], 0)
        self.assertGreaterEqual(by_id[dirty.pk]["error_count"], 1)
        collision_rows = [
            c for c in by_id[dirty.pk]["conflicts"]
            if c["conflict_type"] == "METHODOLOGY_COLLISION"
        ]
        self.assertTrue(len(collision_rows) >= 1)

    def test_batch_too_large_returns_400(self):
        ids = list(range(1, BULK_VALIDATE_MAX_CONTRACT_IDS + 2))
        resp = self.client.post(self.url, {"contract_ids": ids}, format="json")
        self.assertEqual(resp.status_code, 400)

    def test_save_query_param_persists(self):
        dirty = _make_contract("API save")
        _add_methodology_collision(dirty)
        ValidationResult.objects.filter(contract=dirty).delete()
        resp = self.client.post(
            self.url + "?save=1",
            {"contract_ids": [dirty.pk]},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertGreater(ValidationResult.objects.filter(contract=dirty, resolved=False).count(), 0)
