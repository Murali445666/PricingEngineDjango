from datetime import date
from decimal import Decimal

from django.test import TestCase

from core.engine.orchestrator import PricingEngine
from core.engine.types import PricingInput
from core.models import (
    ContractProductScope,
    PayerNetwork,
    PricingRule,
    PricingRuleCondition,
    ProviderContract,
    ProviderOrganization,
    RefProcedureCode,
)
from products.models import (
    LineOfBusiness,
    Network,
    PayerOrganization,
    Product,
    ProductNetworkConfig,
)
from products.services import NetworkLookupService
from providers.models import ProviderNetworkParticipation


class Stage2ProductDomainTests(TestCase):
    """Stage 2 — Payer / Product / LOB / Network domain tests."""

    def setUp(self):
        self.lookup = NetworkLookupService()

    def test_payer_lob_product_fk_links(self):
        payer = PayerOrganization.objects.create(
            name='Acme Health Plan',
            payer_id='PAYER-ACME-01',
            payer_type='COMMERCIAL',
        )
        lob = LineOfBusiness.objects.create(
            code='COMMERCIAL',
            name='Commercial',
        )
        product = Product.objects.create(
            payer=payer,
            lob=lob,
            name='Acme PPO Gold',
            product_code='PPO-GOLD',
            effective_date=date(2025, 1, 1),
        )
        self.assertEqual(product.payer_id, payer.pk)
        self.assertEqual(product.lob_id, lob.pk)
        self.assertEqual(payer.products.count(), 1)
        self.assertEqual(lob.products.count(), 1)

    def test_network_legacy_payer_network_onetoone(self):
        core_payer_org = ProviderOrganization.objects.create(
            organization_id='CORE-PAYER-01',
            name='Legacy Payer Org',
        )
        legacy_network = PayerNetwork.objects.create(
            network_id='NET-LEGACY-01',
            network_name='Legacy Commercial Network',
            payer_org=core_payer_org,
        )
        payer = PayerOrganization.objects.create(
            name='Bridge Payer',
            payer_id='PAYER-BRIDGE-01',
            payer_type='COMMERCIAL',
        )
        network = Network.objects.create(
            payer=payer,
            name='Bridged Network',
            network_type='PPO',
            network_code='BRIDGE-PPO',
            legacy_payer_network=legacy_network,
        )
        legacy_network.refresh_from_db()
        self.assertEqual(network.legacy_payer_network_id, legacy_network.network_id)
        self.assertEqual(legacy_network.network_record.pk, network.pk)

    def test_resolve_network_date_scoping_and_claim_type_preference(self):
        payer = PayerOrganization.objects.create(
            name='Resolve Payer',
            payer_id='PAYER-RESOLVE-01',
            payer_type='COMMERCIAL',
        )
        lob = LineOfBusiness.objects.create(code='COMMERCIAL', name='Commercial')
        product = Product.objects.create(
            payer=payer,
            lob=lob,
            name='Resolve Product',
            effective_date=date(2025, 1, 1),
        )
        network_all = Network.objects.create(
            payer=payer,
            name='All Claims Network',
            network_type='PPO',
        )
        network_professional = Network.objects.create(
            payer=payer,
            name='Professional Network',
            network_type='PPO',
        )
        ProductNetworkConfig.objects.create(
            product=product,
            network=network_all,
            claim_type='ALL',
            effective_date=date(2025, 1, 1),
            termination_date=date(2025, 12, 31),
        )
        ProductNetworkConfig.objects.create(
            product=product,
            network=network_professional,
            claim_type='PROFESSIONAL',
            effective_date=date(2025, 1, 1),
            termination_date=date(2025, 12, 31),
        )

        resolved = self.lookup.resolve_network(
            product.pk, 'PROFESSIONAL', date(2025, 6, 1)
        )
        self.assertIsNotNone(resolved)
        self.assertEqual(resolved.pk, network_professional.pk)

        resolved_all = self.lookup.resolve_network(
            product.pk, 'INSTITUTIONAL', date(2025, 6, 1)
        )
        self.assertIsNotNone(resolved_all)
        self.assertEqual(resolved_all.pk, network_all.pk)

        self.assertIsNone(
            self.lookup.resolve_network(product.pk, 'PROFESSIONAL', date(2026, 1, 1))
        )

    def test_contract_product_scope_and_pricing_still_works(self):
        payer_org = ProviderOrganization.objects.create(
            organization_id='PAYER-SCOPE-01',
            name='Scope Payer',
        )
        provider_org = ProviderOrganization.objects.create(
            organization_id='PROV-SCOPE-01',
            name='Scope Provider',
        )
        legacy_network = PayerNetwork.objects.create(
            network_id='NET-SCOPE-01',
            network_name='Scope Network',
            payer_org=payer_org,
        )
        contract = ProviderContract.objects.create(
            contract_name='Scope Contract',
            status='ACTIVE',
            effective_start_date=date(2025, 1, 1),
            provider_org=provider_org,
            network=legacy_network,
        )
        payer = PayerOrganization.objects.create(
            name='Product Scope Payer',
            payer_id='PAYER-SCOPE-PROD',
            payer_type='COMMERCIAL',
        )
        lob = LineOfBusiness.objects.create(code='COMMERCIAL', name='Commercial')
        product = Product.objects.create(
            payer=payer,
            lob=lob,
            name='Scoped Product',
            effective_date=date(2025, 1, 1),
        )
        scope = ContractProductScope.objects.create(
            contract=contract,
            lob_code='COMMERCIAL',
            product=product,
            effective_date=date(2025, 1, 1),
        )
        self.assertEqual(scope.contract_id, contract.contract_id)
        self.assertEqual(scope.product_id, product.pk)

        RefProcedureCode.objects.create(code_id='99213', description='Office Visit')
        rule = PricingRule.objects.create(
            contract=contract,
            rule_name='Flat Scope Rule',
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
        engine = PricingEngine()
        result = engine.calculate_line(
            contract,
            PricingInput(procedure_code='99213', billed_amount=Decimal('200.00')),
        )
        self.assertEqual(result.allowed_amount, Decimal('100.00'))
        self.assertEqual(result.status.value, 'SUCCESS')

    def test_payer_network_network_type_nullable(self):
        payer_org = ProviderOrganization.objects.create(
            organization_id='PAYER-NT-01',
            name='NT Payer',
        )
        legacy = PayerNetwork.objects.create(
            network_id='NET-NT-01',
            network_name='Legacy Without Type',
            payer_org=payer_org,
        )
        loaded = PayerNetwork.objects.get(pk=legacy.network_id)
        self.assertIsNone(loaded.network_type)

    def test_provider_network_participation_network_new(self):
        payer_org = ProviderOrganization.objects.create(
            organization_id='PAYER-PNP-01',
            name='PNP Payer',
        )
        legacy_network = PayerNetwork.objects.create(
            network_id='NET-PNP-01',
            network_name='PNP Legacy',
            payer_org=payer_org,
        )
        provider_org = ProviderOrganization.objects.create(
            organization_id='ORG-PNP-01',
            name='PNP Provider Org',
        )
        legacy_participation = ProviderNetworkParticipation.objects.create(
            organization=provider_org,
            network=legacy_network,
            status='IN_NETWORK',
            effective_date=date(2025, 1, 1),
        )
        self.assertIsNone(legacy_participation.network_new_id)

        payer = PayerOrganization.objects.create(
            name='PNP Products Payer',
            payer_id='PAYER-PNP-PROD',
            payer_type='COMMERCIAL',
        )
        network_new = Network.objects.create(
            payer=payer,
            name='New Network Record',
            network_type='PPO',
            legacy_payer_network=legacy_network,
        )
        new_participation = ProviderNetworkParticipation.objects.create(
            organization=provider_org,
            network=legacy_network,
            network_new=network_new,
            status='TIER_1',
            effective_date=date(2025, 1, 1),
        )
        self.assertEqual(new_participation.network_new_id, network_new.pk)

        status_via_new = self.lookup.check_org_participation(
            provider_org.organization_id,
            network_new.pk,
            date(2025, 6, 1),
        )
        self.assertEqual(status_via_new, 'TIER_1')

        legacy_only_org = ProviderOrganization.objects.create(
            organization_id='ORG-PNP-LEGACY',
            name='Legacy Only Org',
        )
        legacy_only = ProviderNetworkParticipation.objects.create(
            organization=legacy_only_org,
            network=legacy_network,
            status='OUT_OF_NETWORK',
            effective_date=date(2025, 1, 1),
        )
        self.assertIsNone(legacy_only.network_new_id)
        status_via_legacy_fallback = self.lookup.check_org_participation(
            legacy_only_org.organization_id,
            network_new.pk,
            date(2025, 6, 1),
        )
        self.assertEqual(status_via_legacy_fallback, 'OUT_OF_NETWORK')
