"""Phase D5 — claim-type filtering + covered-entity resolution (KEYSTONE scenarios)."""
from datetime import date
from decimal import Decimal

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from core.demo.seed_keystone import KEYS, seed_keystone_atomic
from core.engine.types import RawClaimInput
from core.models import ContractArrangement, ProviderContract
from core.services.contract_resolution_service import (
    ContractResolutionService,
    STATUS_AMBIGUOUS,
    STATUS_RESOLVED,
)

SERVICE_DATE = date(2025, 6, 15)
LINE = {
    'procedure_code': '99213',
    'billed_amount': '300.00',
    'units': 1,
    'modifiers': [],
}


class KeystoneD5Base(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        seed_keystone_atomic()

    def setUp(self):
        self.api = APIClient()
        self.svc = ContractResolutionService()
        # Ensure F1 arrangement is institutional (D5.1 claim-type filter)
        f1 = ProviderContract.objects.get(legacy_contract_number=KEYS['contract_f1'])
        ContractArrangement.objects.filter(contract=f1).update(claim_type='INSTITUTIONAL')

    def _reprice(self, **kwargs):
        payload = {
            'billing_npi': KEYS['npi_idn'],
            'member_id': KEYS['member_id'],
            'service_date': '2025-06-15',
            'claim_type': 'professional',
            'lines': [LINE],
        }
        payload.update(kwargs)
        return self.api.post('/api/reprice-claim/', payload, format='json')

    def _allowed(self, response):
        lines = response.data.get('lines') or []
        self.assertTrue(lines, msg=response.data)
        return Decimal(str(lines[0]['allowed_amount']))


class D51ClaimTypeFilterTests(KeystoneD5Base):
    def test_idn_professional_resolves_130_not_ambiguous(self):
        """Test-1: IDN professional excludes institutional-only C-F1."""
        result = self.svc.resolve(RawClaimInput(
            billing_npi=KEYS['npi_idn'],
            member_id=KEYS['member_id'],
            service_date=SERVICE_DATE,
            claim_type='professional',
            lines=[],
        ))
        self.assertEqual(result.status, STATUS_RESOLVED)
        contract = ProviderContract.objects.get(pk=result.contract_id)
        self.assertEqual(contract.legacy_contract_number, KEYS['contract_idn'])

        response = self._reprice(billing_npi=KEYS['npi_idn'])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['status'], 'SUCCESS')
        self.assertEqual(self._allowed(response), Decimal('130.00'))


class D53CoveredEntityTests(KeystoneD5Base):
    def test_facility_f1_institutional_resolves_200(self):
        response = self._reprice(
            billing_npi=KEYS['npi_idn'],
            facility_npi=KEYS['npi_f1'],
            claim_type='institutional',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['status'], 'SUCCESS')
        self.assertEqual(response.data['contract_id'], ProviderContract.objects.get(
            legacy_contract_number=KEYS['contract_f1'],
        ).contract_id)
        self.assertEqual(self._allowed(response), Decimal('200.00'))

    def test_facility_f2_falls_back_to_idn_130(self):
        response = self._reprice(
            billing_npi=KEYS['npi_idn'],
            facility_npi=KEYS['npi_f2'],
            claim_type='institutional',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['status'], 'SUCCESS')
        self.assertEqual(self._allowed(response), Decimal('130.00'))

    def test_cardiology_still_ambiguous(self):
        result = self.svc.resolve(RawClaimInput(
            billing_npi=KEYS['npi_card'],
            member_id=KEYS['member_id'],
            service_date=SERVICE_DATE,
            claim_type='professional',
            lines=[],
        ))
        self.assertEqual(result.status, STATUS_AMBIGUOUS)
        self.assertEqual(len(result.candidates), 2)

        response = self._reprice(billing_npi=KEYS['npi_card'])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['status'], 'AMBIGUOUS')
        self.assertEqual(response.data['lines'], [])


class D5FeatureFlagTests(KeystoneD5Base):
    @override_settings(FEATURE_COVERAGE_RESOLUTION=False)
    def test_legacy_provider_org_path_with_claim_type_filter(self):
        """Flag off: provider_org path still filters by claim type."""
        result = self.svc.resolve(RawClaimInput(
            billing_npi=KEYS['npi_idn'],
            member_id=KEYS['member_id'],
            service_date=SERVICE_DATE,
            claim_type='professional',
            lines=[],
        ))
        self.assertEqual(result.status, STATUS_RESOLVED)
        contract = ProviderContract.objects.get(pk=result.contract_id)
        self.assertEqual(contract.legacy_contract_number, KEYS['contract_idn'])
