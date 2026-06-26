from datetime import date

from django.core.exceptions import ValidationError
from django.test import TestCase
from rest_framework.test import APIClient

from core.models import (
    ClaimHeader,
    ContractProductScope,
    ContractScope,
    PayerNetwork,
    ProviderContract,
    ProviderOrganization,
)
from core.services.contract_resolver import ContractResolver
from members.models import Member
from products.models import LineOfBusiness, Network, PayerOrganization, Product


class CleanupRedundanciesTests(TestCase):
    """Cleanup pass — ContractScope, member_fk, Network validation, payer bridge."""

    SERVICE_DATE = date(2025, 6, 15)

    def setUp(self):
        self.resolver = ContractResolver()
        self.api = APIClient(raise_request_exception=False)

        self.billing_org = ProviderOrganization.objects.create(
            organization_id='ORG-CLEANUP-BILL',
            name='Cleanup Billing Org',
        )
        self.core_payer_org = ProviderOrganization.objects.create(
            organization_id='ORG-CLEANUP-PAYER',
            name='Cleanup Payer Org',
        )
        self.legacy_network = PayerNetwork.objects.create(
            network_id='NET-CLEANUP-01',
            network_name='Cleanup Network',
            payer_org=self.core_payer_org,
        )
        self.products_payer = PayerOrganization.objects.create(
            name='Cleanup Products Payer',
            payer_id='PAYER-CLEANUP-01',
            payer_type='COMMERCIAL',
        )
        self.network = Network.objects.create(
            payer=self.products_payer,
            name='Cleanup Products Network',
            network_type='PPO',
            legacy_payer_network=self.legacy_network,
        )
        self.lob = LineOfBusiness.objects.create(
            code='COMMERCIAL',
            name='Commercial',
        )
        self.product = Product.objects.create(
            payer=self.products_payer,
            lob=self.lob,
            name='Cleanup Product',
            effective_date=date(2025, 1, 1),
        )

    def _create_contract(self, **kwargs):
        defaults = {
            'contract_name': 'Cleanup Contract',
            'status': 'ACTIVE',
            'effective_start_date': date(2025, 1, 1),
            'provider_org': self.billing_org,
            'network': self.legacy_network,
        }
        defaults.update(kwargs)
        return ProviderContract.objects.create(**defaults)

    def test_contract_resolver_respects_contract_scope(self):
        contract = self._create_contract(line_of_business=None)
        ContractScope.objects.create(
            contract=contract,
            line_of_business='COMMERCIAL',
            priority=100,
        )
        contract_id = self.resolver.resolve(
            org_id=self.billing_org.organization_id,
            network_id=self.network.id,
            lob='COMMERCIAL',
            service_date=self.SERVICE_DATE,
        )
        self.assertEqual(contract_id, contract.contract_id)

    def test_contract_resolver_respects_contract_product_scope_regression(self):
        contract = self._create_contract(line_of_business='COMMERCIAL')
        ContractProductScope.objects.create(
            contract=contract,
            lob_code='COMMERCIAL',
            product=self.product,
            effective_date=date(2025, 1, 1),
        )
        contract_id = self.resolver.resolve(
            org_id=self.billing_org.organization_id,
            network_id=self.network.id,
            lob='COMMERCIAL',
            service_date=self.SERVICE_DATE,
            product_id=self.product.id,
        )
        self.assertEqual(contract_id, contract.contract_id)

    def test_claim_header_member_fk_auto_populated(self):
        member = Member.objects.create(member_id='M-TEST-001', last_name='Test')
        contract = self._create_contract()
        before_count = ClaimHeader.objects.count()
        response = self.api.post(
            '/api/claims/',
            {
                'contract_id': contract.contract_id,
                'member_id': 'M-TEST-001',
                'service_date': '2025-06-15',
                'lines': [{
                    'procedure_code': '99213',
                    'billed_amount': '100.00',
                }],
            },
            format='json',
        )
        self.assertEqual(response.status_code, 201)
        header = ClaimHeader.objects.get(pk=response.data['claim_id'])
        self.assertEqual(ClaimHeader.objects.count(), before_count + 1)
        self.assertEqual(header.member_id, 'M-TEST-001')
        self.assertEqual(header.member_fk_id, member.pk)

    def test_claim_header_member_fk_not_set_when_no_member_match(self):
        contract = self._create_contract()
        before_count = ClaimHeader.objects.count()
        response = self.api.post(
            '/api/claims/',
            {
                'contract_id': contract.contract_id,
                'member_id': 'UNKNOWN-99',
                'service_date': '2025-06-15',
                'lines': [{
                    'procedure_code': '99213',
                    'billed_amount': '100.00',
                }],
            },
            format='json',
        )
        self.assertEqual(response.status_code, 201)
        header = ClaimHeader.objects.get(pk=response.data['claim_id'])
        self.assertEqual(ClaimHeader.objects.count(), before_count + 1)
        self.assertEqual(header.member_id, 'UNKNOWN-99')
        self.assertIsNone(header.member_fk_id)

    def test_network_clean_blocks_null_legacy_payer_network(self):
        network = Network(
            payer=self.products_payer,
            name='Unlinked Network',
            network_type='PPO',
            legacy_payer_network=None,
        )
        with self.assertRaises(ValidationError) as ctx:
            network.full_clean()
        self.assertIn('legacy_payer_network', ctx.exception.message_dict)

    def test_network_clean_passes_with_legacy_payer_network(self):
        self.network.full_clean()

    def test_payer_organization_legacy_provider_org_bridge(self):
        payer_org = PayerOrganization.objects.create(
            name='Bridged Payer Org',
            payer_id='PAYER-BRIDGE-CLEANUP',
            payer_type='COMMERCIAL',
            legacy_provider_org=self.core_payer_org,
        )
        self.assertEqual(
            self.core_payer_org.payer_org_record.pk,
            payer_org.pk,
        )
