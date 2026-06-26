from datetime import date
from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from core.models import (
    ContractProductScope,
    PayerNetwork,
    PricingRule,
    PricingRuleCondition,
    ProviderContract,
    ProviderOrganization,
    RefProcedureCode,
    RefSpecialty,
)
from members.models import Enrollment, Member
from products.models import (
    LineOfBusiness,
    Network,
    PayerOrganization,
    Product,
    ProductNetworkConfig,
)
from providers.models import Provider, ProviderAffiliation, ProviderNetworkParticipation


class Stage5ContextApiTests(TestCase):
    """Stage 5 — Context-driven pricing and directory APIs."""

    SERVICE_DATE = date(2025, 6, 15)

    def setUp(self):
        self.api = APIClient()

        self.billing_org = ProviderOrganization.objects.create(
            organization_id='ORG-S4-BILLING',
            name='Stage 4 Billing Org',
            tax_id='12-3456789',
            npi='BILLING-NPI-S4',
        )
        self.core_payer_org = ProviderOrganization.objects.create(
            organization_id='ORG-S4-PAYER',
            name='Stage 4 Payer Org',
        )
        self.legacy_network = PayerNetwork.objects.create(
            network_id='NET-S4-01',
            network_name='Stage 4 Network',
            payer_org=self.core_payer_org,
            line_of_business='COMMERCIAL',
        )
        self.other_legacy_network = PayerNetwork.objects.create(
            network_id='NET-S4-OTHER',
            network_name='Other Network',
            payer_org=self.core_payer_org,
        )
        self.contract = ProviderContract.objects.create(
            contract_name='Stage 4 Contract',
            status='ACTIVE',
            effective_start_date=date(2025, 1, 1),
            provider_org=self.billing_org,
            network=self.legacy_network,
            line_of_business='COMMERCIAL',
        )
        self.products_payer = PayerOrganization.objects.create(
            name='Stage 4 Products Payer',
            payer_id='PAYER-S4-01',
            payer_type='COMMERCIAL',
        )
        self.lob = LineOfBusiness.objects.create(
            code='COMMERCIAL',
            name='Commercial',
        )
        self.product = Product.objects.create(
            payer=self.products_payer,
            lob=self.lob,
            name='Stage 4 Product',
            effective_date=date(2025, 1, 1),
        )
        self.network = Network.objects.create(
            payer=self.products_payer,
            name='Stage 4 Products Network',
            network_type='PPO',
            network_code='S4-NET',
            legacy_payer_network=self.legacy_network,
        )
        ProductNetworkConfig.objects.create(
            product=self.product,
            network=self.network,
            claim_type='PROFESSIONAL',
            effective_date=date(2025, 1, 1),
        )
        self.specialty = RefSpecialty.objects.create(
            specialty_code='FAM',
            description='Family Medicine',
        )
        self.rendering_provider = Provider.objects.create(
            npi='RENDER-NPI-S4',
            first_name='Render',
            last_name='Provider',
            primary_specialty=self.specialty,
        )
        ProviderAffiliation.objects.create(
            provider=self.rendering_provider,
            organization=self.billing_org,
            effective_date=date(2025, 1, 1),
        )
        ProviderNetworkParticipation.objects.create(
            organization=self.billing_org,
            network=self.legacy_network,
            network_new=self.network,
            status='IN_NETWORK',
            effective_date=date(2025, 1, 1),
        )
        self.member = Member.objects.create(
            member_id='MEM-S4-001',
            first_name='Test',
            last_name='Member',
            zip_code='60601',
        )
        Enrollment.objects.create(
            member=self.member,
            product=self.product,
            effective_date=date(2025, 1, 1),
        )
        ContractProductScope.objects.create(
            contract=self.contract,
            lob_code='COMMERCIAL',
            product=self.product,
            effective_date=date(2025, 1, 1),
        )
        RefProcedureCode.objects.create(code_id='99213', description='Office Visit')
        rule = PricingRule.objects.create(
            contract=self.contract,
            rule_name='Stage 4 Flat',
            specificity_score=10,
            methodology_code='FLAT_RATE',
            flat_rate=Decimal('100.00'),
            status='ACTIVE',
            effective_start_date=date(2025, 1, 1),
        )
        PricingRuleCondition.objects.create(
            pricing_rule=rule,
            attribute_name='procedure_code',
            operator='EQ',
            attribute_value='99213',
        )

    def _valid_reprice_payload(self, member_id='MEM-S4-001'):
        return {
            'billing_npi': 'BILLING-NPI-S4',
            'rendering_npi': 'RENDER-NPI-S4',
            'member_id': member_id,
            'service_date': '2025-06-15',
            'claim_type': 'professional',
            'lines': [{
                'procedure_code': '99213',
                'billed_amount': '200.00',
                'units': 1,
            }],
        }

    def test_reprice_claim_success(self):
        response = self.api.post('/api/reprice-claim/', self._valid_reprice_payload(), format='json')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['status'], 'SUCCESS')
        self.assertEqual(data['contract_id'], self.contract.contract_id)
        self.assertEqual(data['resolution_mode'], 'RESOLVED')
        self.assertEqual(data['member']['lob'], 'COMMERCIAL')

    def test_reprice_claim_missing_member_id(self):
        payload = self._valid_reprice_payload()
        del payload['member_id']
        response = self.api.post('/api/reprice-claim/', payload, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('errors', response.json())

    def test_reprice_claim_no_lines(self):
        payload = self._valid_reprice_payload()
        payload['lines'] = []
        response = self.api.post('/api/reprice-claim/', payload, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('errors', response.json())

    def test_reprice_claim_unenrolled_member(self):
        payload = self._valid_reprice_payload(member_id='MEM-NOT-ENROLLED')
        payload['billing_npi'] = 'UNKNOWN-NPI'
        response = self.api.post('/api/reprice-claim/', payload, format='json')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn(data['status'], ('OON', 'NO_CONTRACT'))
        self.assertIsNone(data['contract_id'])

    def test_reprice_claim_batch_two_valid(self):
        response = self.api.post('/api/reprice-claim-batch/', {
            'claims': [
                self._valid_reprice_payload(),
                self._valid_reprice_payload(),
            ],
        }, format='json')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['count'], 2)
        self.assertEqual(len(data['results']), 2)
        for row in data['results']:
            self.assertEqual(row['status'], 'SUCCESS')

    def test_reprice_claim_batch_mixed_results(self):
        response = self.api.post('/api/reprice-claim-batch/', {
            'claims': [
                self._valid_reprice_payload(),
                {
                    **self._valid_reprice_payload(member_id='MEM-NOT-ENROLLED'),
                    'billing_npi': 'UNKNOWN-NPI',
                },
            ],
        }, format='json')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['count'], 2)
        self.assertEqual(data['results'][0]['index'], 0)
        self.assertEqual(data['results'][0]['status'], 'SUCCESS')
        self.assertEqual(data['results'][1]['index'], 1)
        self.assertIn(data['results'][1]['status'], ('OON', 'NO_CONTRACT'))

    def test_provider_list_no_filters(self):
        response = self.api.get('/api/providers/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('count', data)
        self.assertIn('page', data)
        self.assertIn('page_size', data)
        self.assertIn('results', data)
        self.assertGreaterEqual(data['count'], 1)

    def test_provider_list_filter_by_npi(self):
        response = self.api.get('/api/providers/', {'npi': 'RENDER-NPI-S4'})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['count'], 1)
        self.assertEqual(data['results'][0]['npi'], 'RENDER-NPI-S4')
        self.assertEqual(data['results'][0]['id'], self.rendering_provider.id)

    def test_member_enrollment_lookup(self):
        response = self.api.get(
            f'/api/members/{self.member.member_id}/enrollment/',
            {'service_date': '2025-06-15'},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['enrolled'])
        self.assertEqual(data['lob'], 'COMMERCIAL')
        self.assertEqual(data['product_id'], self.product.id)

    def test_product_list(self):
        response = self.api.get('/api/products/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('count', data)
        self.assertIn('page', data)
        self.assertIn('page_size', data)
        self.assertIn('results', data)
        self.assertGreaterEqual(data['count'], 1)
