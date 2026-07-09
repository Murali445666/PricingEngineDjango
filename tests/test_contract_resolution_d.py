from datetime import date

from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient

from core.engine.types import RawClaimInput
from core.models import (
    ContractProductScope,
    ContractResolutionException,
    ProviderContract,
)
from core.services.contract_resolution_service import (
    ContractResolutionService,
    STATUS_AMBIGUOUS,
    STATUS_NO_ACTIVE_VERSION,
    STATUS_NO_CONTRACT,
    STATUS_RESOLVED,
    STATUS_UNRESOLVED_ENTITY,
)
from members.models import Enrollment, Member
from products.models import (
    LineOfBusiness,
    Network,
    PayerOrganization,
    Product,
    ProductNetworkConfig,
)
from providers.services import ProviderLookupService
from tests.test_resolution_phases import ResolutionPhaseBase


class ContractResolutionServiceTests(ResolutionPhaseBase):
    def setUp(self):
        super().setUp()
        self.svc = ContractResolutionService()

    def _raw(self, **kwargs):
        defaults = {
            'billing_npi': 'LEAF-NPI-R',
            'member_id': 'MEM-R-001',
            'service_date': self.SERVICE_DATE,
            'claim_type': 'professional',
            'lines': [],
        }
        defaults.update(kwargs)
        return RawClaimInput(**defaults)

    def test_resolved_for_good_claim(self):
        self._create_contract()
        result = self.svc.resolve(self._raw())
        self.assertEqual(result.status, STATUS_RESOLVED)
        self.assertIsNotNone(result.contract_id)
        self.assertIsNotNone(result.version_id)
        self.assertEqual(result.candidates, [])

    def test_ambiguous_returns_candidates(self):
        self._create_contract(priority=10, legacy_number='CONT-D-A')
        self._create_contract(priority=10, legacy_number='CONT-D-B')
        result = self.svc.resolve(self._raw())
        self.assertEqual(result.status, STATUS_AMBIGUOUS)
        self.assertIsNone(result.contract_id)
        self.assertEqual(len(result.candidates), 2)

    def test_no_active_version(self):
        """Legacy contract with no ContractVersion rows still resolves (Part B)."""
        contract = ProviderContract.objects.create(
            contract_name='No Version Contract',
            legacy_contract_number='CONT-NO-VER',
            status='ACTIVE',
            effective_start_date=date(2025, 1, 1),
            provider_org=self.billing_org,
            network=self.legacy_network,
            line_of_business='COMMERCIAL',
        )
        ContractProductScope.objects.create(
            contract=contract,
            lob_code='COMMERCIAL',
            product=self.product,
            effective_date=date(2025, 1, 1),
        )
        result = self.svc.resolve(self._raw())
        self.assertEqual(result.status, STATUS_RESOLVED)
        self.assertEqual(result.contract_id, contract.contract_id)
        self.assertIsNone(result.version_id)

    def test_genuine_no_active_version_blocks(self):
        """Contract with versions but none active on DOS → NO_ACTIVE_VERSION."""
        from core.models import ContractVersion

        contract = self._create_contract(legacy_number='CONT-VER-INACTIVE')
        ContractVersion.objects.filter(contract=contract).update(
            effective_start_date=date(2026, 1, 1),
        )
        result = self.svc.resolve(self._raw())
        self.assertEqual(result.status, STATUS_NO_ACTIVE_VERSION)
        self.assertEqual(result.contract_id, contract.contract_id)
        self.assertIsNone(result.version_id)

    def test_dual_product_enrollment_unresolved_entity(self):
        product_b = Product.objects.create(
            payer=self.products_payer,
            lob=self.lob,
            name='R Product B',
            product_code='PROD-R-02',
            effective_date=date(2025, 1, 1),
        )
        ProductNetworkConfig.objects.create(
            product=product_b,
            network=self.network,
            claim_type='PROFESSIONAL',
            effective_date=date(2025, 1, 1),
        )
        Enrollment.objects.create(
            member=self.member,
            product=product_b,
            effective_date=date(2025, 1, 1),
        )
        result = self.svc.resolve(self._raw())
        self.assertEqual(result.status, STATUS_UNRESOLVED_ENTITY)
        self.assertEqual(result.gathered.get('ambiguous_entity'), 'member')
        self.assertGreaterEqual(len(result.candidates), 2)
        self.assertIsNone(result.contract_id)

    def test_normal_member_still_resolves(self):
        self._create_contract()
        result = self.svc.resolve(self._raw())
        self.assertEqual(result.status, STATUS_RESOLVED)

    @patch.object(
        ProviderLookupService,
        'rendering_provider_ambiguity',
        return_value=(True, [101, 102]),
    )
    def test_dual_rendering_provider_unresolved_entity(self, _mock_ambig):
        result = self.svc.resolve(self._raw(rendering_npi='RENDER-NPI-R'))
        self.assertEqual(result.status, STATUS_UNRESOLVED_ENTITY)
        self.assertEqual(result.gathered.get('ambiguous_entity'), 'rendering')
        self.assertEqual(result.candidates, [101, 102])

    def test_unrelated_billing_orgs_unresolved_entity(self):
        from core.models import ProviderOrganization

        ProviderOrganization.objects.create(
            organization_id='ORG-R-UNRELATED',
            name='Unrelated Org Same NPI',
            npi='LEAF-NPI-R',
        )
        result = self.svc.resolve(self._raw())
        self.assertEqual(result.status, STATUS_UNRESOLVED_ENTITY)
        self.assertEqual(result.gathered.get('ambiguous_entity'), 'billing_org')

    def test_parent_child_same_npi_not_ambiguous(self):
        """Parent/child orgs sharing NPI are R5 hierarchy — not ambiguous."""
        self.idn_org.npi = 'LEAF-NPI-R'
        self.idn_org.save(update_fields=['npi'])
        svc = ProviderLookupService()
        ambiguous, org_ids = svc.billing_org_ambiguity('LEAF-NPI-R')
        self.assertFalse(ambiguous)
        self.assertEqual(len(org_ids), 2)

    def test_no_contract_when_org_missing(self):
        result = self.svc.resolve(self._raw(billing_npi='UNKNOWN-NPI'))
        self.assertEqual(result.status, STATUS_NO_CONTRACT)


class ResolutionExceptionQueueTests(ResolutionPhaseBase):
    def test_ambiguous_reprice_creates_exception_and_review_queue(self):
        self._create_contract(priority=10, legacy_number='CONT-D-A')
        self._create_contract(priority=10, legacy_number='CONT-D-B')
        payload = {
            'billing_npi': 'LEAF-NPI-R',
            'member_id': 'MEM-R-001',
            'service_date': '2025-06-15',
            'claim_type': 'professional',
            'lines': [
                {'procedure_code': '99213', 'billed_amount': '200.00', 'units': 1, 'modifiers': []}
            ],
        }
        before = ContractResolutionException.objects.count()
        response = self.api.post('/api/reprice-claim/', payload, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['status'], 'AMBIGUOUS')
        self.assertEqual(ContractResolutionException.objects.count(), before + 1)

        exc = ContractResolutionException.objects.latest('created_at')
        self.assertEqual(exc.status, 'AMBIGUOUS')
        self.assertEqual(len(exc.candidates), 2)
        self.assertFalse(exc.is_reviewed)

        listing = self.api.get('/api/resolution-exceptions/?status=AMBIGUOUS')
        self.assertEqual(listing.status_code, 200)
        self.assertGreaterEqual(listing.data['count'], 1)
        self.assertTrue(any(r['id'] == exc.id for r in listing.data['results']))

        patch = self.api.patch(
            f'/api/resolution-exceptions/{exc.id}/',
            {'is_reviewed': True, 'review_notes': 'Analyst picked contract manually'},
            format='json',
        )
        self.assertEqual(patch.status_code, 200)
        exc.refresh_from_db()
        self.assertTrue(exc.is_reviewed)
        self.assertEqual(exc.review_notes, 'Analyst picked contract manually')

    def test_success_reprice_does_not_create_exception(self):
        self._create_contract()
        payload = {
            'billing_npi': 'LEAF-NPI-R',
            'member_id': 'MEM-R-001',
            'service_date': '2025-06-15',
            'claim_type': 'professional',
            'lines': [
                {'procedure_code': '99213', 'billed_amount': '200.00', 'units': 1, 'modifiers': []}
            ],
        }
        before = ContractResolutionException.objects.count()
        response = self.api.post('/api/reprice-claim/', payload, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['status'], 'SUCCESS')
        self.assertEqual(ContractResolutionException.objects.count(), before)


class PhaseD4ExceptionQueueTests(ResolutionPhaseBase):
    def test_dual_enrollment_reprice_creates_unresolved_exception(self):
        product_b = Product.objects.create(
            payer=self.products_payer,
            lob=self.lob,
            name='R Product B',
            product_code='PROD-R-02',
            effective_date=date(2025, 1, 1),
        )
        ProductNetworkConfig.objects.create(
            product=product_b,
            network=self.network,
            claim_type='PROFESSIONAL',
            effective_date=date(2025, 1, 1),
        )
        Enrollment.objects.create(
            member=self.member,
            product=product_b,
            effective_date=date(2025, 1, 1),
        )
        payload = {
            'billing_npi': 'LEAF-NPI-R',
            'member_id': 'MEM-R-001',
            'service_date': '2025-06-15',
            'claim_type': 'professional',
            'lines': [
                {'procedure_code': '99213', 'billed_amount': '200.00', 'units': 1, 'modifiers': []}
            ],
        }
        before = ContractResolutionException.objects.count()
        response = self.api.post('/api/reprice-claim/', payload, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['status'], 'UNRESOLVED_ENTITY')
        self.assertEqual(response.data['lines'], [])
        self.assertEqual(ContractResolutionException.objects.count(), before + 1)
        exc = ContractResolutionException.objects.latest('created_at')
        self.assertEqual(exc.status, 'UNRESOLVED_ENTITY')
        self.assertEqual(exc.gathered_inputs.get('ambiguous_entity'), 'member')

    def test_genuine_no_active_version_reprice_blocks_and_queues(self):
        from core.models import ContractVersion

        contract = self._create_contract(legacy_number='CONT-D4-NAV')
        ContractVersion.objects.filter(contract=contract).update(
            effective_start_date=date(2026, 1, 1),
        )
        payload = {
            'billing_npi': 'LEAF-NPI-R',
            'member_id': 'MEM-R-001',
            'service_date': '2025-06-15',
            'claim_type': 'professional',
            'lines': [
                {'procedure_code': '99213', 'billed_amount': '200.00', 'units': 1, 'modifiers': []}
            ],
        }
        before = ContractResolutionException.objects.count()
        response = self.api.post('/api/reprice-claim/', payload, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['status'], 'NO_ACTIVE_VERSION')
        self.assertEqual(response.data['contract_id'], contract.contract_id)
        self.assertEqual(response.data['lines'], [])
        self.assertEqual(ContractResolutionException.objects.count(), before + 1)
