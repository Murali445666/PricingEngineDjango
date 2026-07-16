"""Enrollment guard: unenrolled members must not fall through to contract ambiguity."""
from datetime import date

from django.test import TestCase
from rest_framework.test import APIClient

from core.demo.seed_use_cases import seed_use_cases_atomic
from core.demo.use_cases import CAST
from core.engine.types import RawClaimInput
from core.models import ContractResolutionException
from core.services.contract_resolution_service import (
    ContractResolutionService,
    STATUS_AMBIGUOUS,
    STATUS_NO_CONTRACT,
    STATUS_RESOLVED,
)


class DemoUcEnrollmentGuardTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        seed_use_cases_atomic()

    def setUp(self):
        self.api = APIClient()
        self.svc = ContractResolutionService()
        ContractResolutionException.objects.all().delete()

    def _reprice(self, **kwargs):
        payload = {
            'billing_npi': CAST['billing_npi_in'],
            'member_id': 'DEMO-UC-MEM-A1',
            'service_date': '2025-06-15',
            'claim_type': 'professional',
            'lines': [{
                'procedure_code': '99213',
                'billed_amount': '200.00',
                'units': 1,
                'modifiers': [],
            }],
        }
        payload.update(kwargs)
        return self.api.post('/api/reprice-claim/', payload, format='json')

    def test_f2_no_enrollment_returns_no_contract(self):
        result = self.svc.resolve(RawClaimInput(
            billing_npi=CAST['billing_npi_in'],
            member_id='DEMO-UC-MEM-NOENROLL',
            service_date=date(2025, 6, 15),
            claim_type='professional',
            lines=[],
        ))
        self.assertEqual(result.status, STATUS_NO_CONTRACT)
        self.assertEqual(result.candidates, [])
        self.assertIn('enrollment', result.reason.lower())

    def test_f3_terminated_enrollment_returns_no_contract(self):
        result = self.svc.resolve(RawClaimInput(
            billing_npi=CAST['billing_npi_in'],
            member_id='DEMO-UC-MEM-TERMED',
            service_date=date(2025, 6, 15),
            claim_type='professional',
            lines=[],
        ))
        self.assertEqual(result.status, STATUS_NO_CONTRACT)
        self.assertEqual(result.candidates, [])

    def test_f2_reprice_api_persists_resolution_exception(self):
        before = ContractResolutionException.objects.count()
        response = self._reprice(member_id='DEMO-UC-MEM-NOENROLL')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['status'], STATUS_NO_CONTRACT)
        self.assertEqual(response.data['lines'], [])
        self.assertEqual(ContractResolutionException.objects.count(), before + 1)
        exc = ContractResolutionException.objects.latest('created_at')
        self.assertEqual(exc.status, STATUS_NO_CONTRACT)
        self.assertEqual(exc.gathered_inputs.get('member_id'), 'DEMO-UC-MEM-NOENROLL')

    def test_f3_reprice_api_persists_resolution_exception(self):
        response = self._reprice(member_id='DEMO-UC-MEM-TERMED')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['status'], STATUS_NO_CONTRACT)
        self.assertEqual(
            ContractResolutionException.objects.filter(
                status=STATUS_NO_CONTRACT,
                gathered_inputs__member_id='DEMO-UC-MEM-TERMED',
            ).count(),
            1,
        )

    def test_f4_enrolled_member_still_ambiguous(self):
        """Enrolled member on IN org with many contracts — real ambiguity unchanged."""
        result = self.svc.resolve(RawClaimInput(
            billing_npi=CAST['billing_npi_in'],
            member_id='DEMO-UC-MEM-A1',
            service_date=date(2025, 6, 15),
            claim_type='professional',
            lines=[],
        ))
        self.assertEqual(result.status, STATUS_AMBIGUOUS)
        self.assertGreater(len(result.candidates), 1)

    def test_provider_only_resolution_unaffected(self):
        """member_context=False must not short-circuit when member_id is absent from gather."""
        result = self.svc.resolve(
            RawClaimInput(
                billing_npi=CAST['billing_npi_in'],
                member_id='DEMO-UC-MEM-NOENROLL',
                service_date=date(2025, 6, 15),
                claim_type='professional',
                lines=[],
            ),
            member_context=False,
        )
        self.assertNotEqual(result.status, STATUS_NO_CONTRACT)
        self.assertIn(result.status, (STATUS_AMBIGUOUS, STATUS_RESOLVED, STATUS_NO_CONTRACT))
