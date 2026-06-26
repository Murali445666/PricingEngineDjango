from datetime import date
from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from core.engine.service import ClaimPricingService
from core.engine.types import (
    ClaimPricingContext,
    MemberPricingContext,
    PricingStatus,
    ProviderPricingContext,
    RawClaimInput,
)
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
from core.services.contract_resolver import ContractResolutionError, ContractResolver
from core.services.pricing_context_resolver import PricingContextResolver
from members.models import Enrollment, Member
from products.models import (
    LineOfBusiness,
    Network,
    PayerOrganization,
    Product,
    ProductNetworkConfig,
)
from providers.models import Provider, ProviderAffiliation, ProviderNetworkParticipation


class Stage4ContextResolverTests(TestCase):
    """Stage 4 — Pricing Context Resolver and ContractResolver tests."""

    SERVICE_DATE = date(2025, 6, 15)

    def setUp(self):
        self.contract_resolver = ContractResolver()
        self.resolver = PricingContextResolver()
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

    def test_contract_resolver_org_network_lob(self):
        contract_id = self.contract_resolver.resolve(
            org_id=self.billing_org.organization_id,
            network_id=self.network.id,
            lob='COMMERCIAL',
            service_date=self.SERVICE_DATE,
            product_id=self.product.id,
        )
        self.assertEqual(contract_id, self.contract.contract_id)

    def test_contract_resolver_org_only_fallback(self):
        contract_id = self.contract_resolver.resolve(
            org_id=self.billing_org.organization_id,
            network_id=None,
            lob=None,
            service_date=self.SERVICE_DATE,
        )
        self.assertEqual(contract_id, self.contract.contract_id)

    def test_contract_resolver_org_not_found(self):
        with self.assertRaises(ContractResolutionError) as ctx:
            self.contract_resolver.resolve(
                org_id='ORG-DOES-NOT-EXIST',
                network_id=None,
                lob=None,
                service_date=self.SERVICE_DATE,
            )
        self.assertFalse(ctx.exception.is_oon)

    def test_contract_resolver_org_found_no_matching_contract(self):
        wrong_network = Network.objects.create(
            payer=self.products_payer,
            name='Unlinked Network',
            network_type='PPO',
            legacy_payer_network=self.other_legacy_network,
        )
        with self.assertRaises(ContractResolutionError) as ctx:
            self.contract_resolver.resolve(
                org_id=self.billing_org.organization_id,
                network_id=wrong_network.id,
                lob='COMMERCIAL',
                service_date=self.SERVICE_DATE,
                product_id=self.product.id,
            )
        self.assertTrue(ctx.exception.is_oon)

    def test_pricing_context_resolver_full_path(self):
        raw = RawClaimInput(
            billing_npi='BILLING-NPI-S4',
            rendering_npi='RENDER-NPI-S4',
            member_id='MEM-S4-001',
            service_date=self.SERVICE_DATE,
            claim_type='professional',
            lines=[],
        )
        ctx = self.resolver.resolve(raw)
        self.assertEqual(ctx.resolution_mode, 'RESOLVED')
        self.assertEqual(ctx.contract_id, self.contract.contract_id)
        self.assertEqual(ctx.provider.network_status, 'IN_NETWORK')
        self.assertEqual(ctx.member.lob, 'COMMERCIAL')
        self.assertTrue(ctx.provider.affiliation_verified)
        self.assertEqual(ctx.provider.rendering_provider_specialty, 'FAM')

    def test_pricing_context_resolver_oon_no_matching_contract(self):
        wrong_network = Network.objects.create(
            payer=self.products_payer,
            name='OON Network',
            network_type='HMO',
            legacy_payer_network=self.other_legacy_network,
        )
        ProductNetworkConfig.objects.filter(product=self.product).update(
            network=wrong_network,
        )
        ProviderNetworkParticipation.objects.filter(
            organization=self.billing_org,
        ).delete()

        raw = RawClaimInput(
            billing_npi='BILLING-NPI-S4',
            rendering_npi='RENDER-NPI-S4',
            member_id='MEM-S4-001',
            service_date=self.SERVICE_DATE,
            claim_type='professional',
            lines=[],
        )
        with self.assertRaises(ContractResolutionError) as ctx:
            self.resolver.resolve(raw)
        self.assertTrue(ctx.exception.is_oon)

    def test_pricing_context_resolver_provider_only(self):
        raw = RawClaimInput(
            billing_npi='BILLING-NPI-S4',
            service_date=self.SERVICE_DATE,
            claim_type='professional',
            lines=[],
        )
        ctx = self.resolver.resolve_provider_only(raw)
        self.assertEqual(ctx.resolution_mode, 'RESOLVED')
        self.assertEqual(ctx.contract_id, self.contract.contract_id)
        self.assertIsNone(ctx.member.member_id)
        self.assertIsNone(ctx.member.product_id)

    def test_pricing_context_resolver_direct_override(self):
        raw = RawClaimInput(
            override_contract_id=self.contract.contract_id,
            service_date=self.SERVICE_DATE,
            lines=[],
        )
        ctx = self.resolver.resolve(raw)
        self.assertEqual(ctx.resolution_mode, 'DIRECT')
        self.assertEqual(ctx.contract_id, self.contract.contract_id)

    def test_price_claim_from_context_integration(self):
        ctx = ClaimPricingContext(
            resolution_mode='RESOLVED',
            contract_id=self.contract.contract_id,
            version_id=None,
            provider=ProviderPricingContext(
                billing_org_id=self.billing_org.organization_id,
                billing_org_tax_id=None,
                rendering_provider_id=None,
                rendering_provider_specialty=None,
                facility_id=None,
                facility_type=None,
                place_of_service=None,
                network_status='IN_NETWORK',
                network_tier=None,
            ),
            member=MemberPricingContext(
                member_id='MEM-S4-001',
                product_id=self.product.id,
                lob='COMMERCIAL',
                network_id=self.network.id,
                locality_zip='60601',
                enrollment_id=None,
            ),
            service_date=self.SERVICE_DATE,
            pricing_date=self.SERVICE_DATE,
            claim_type='PROFESSIONAL',
            lines=[{
                'procedure_code': '99213',
                'billed_amount': '200.00',
                'units': 1,
            }],
        )
        service = ClaimPricingService()
        result = service.price_claim_from_context(ctx)
        self.assertEqual(result.status, PricingStatus.SUCCESS)
        self.assertEqual(result.total_allowed, Decimal('100.00'))

    def test_resolve_context_api_endpoint(self):
        response = self.api.get(
            '/api/resolve-context/',
            {
                'billing_npi': 'BILLING-NPI-S4',
                'member_id': 'MEM-S4-001',
                'service_date': '2025-06-15',
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['resolution_mode'], 'RESOLVED')
        self.assertEqual(data['contract_id'], self.contract.contract_id)
        self.assertIn('provider', data)
        self.assertIn('member', data)
        self.assertEqual(data['member']['lob'], 'COMMERCIAL')
