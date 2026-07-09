"""
Resolution layer phases R2–R6 — tests per CONTRACT_AUTHORING_IDEATION.md §12.
"""
from datetime import date
from decimal import Decimal
from uuid import UUID

from django.test import TestCase
from rest_framework.test import APIClient

from core.engine.types import RawClaimInput
from core.models import (
    ClaimHeader,
    ClaimLine,
    ClaimResolutionLog,
    ContractProductScope,
    ContractVersion,
    PayerNetwork,
    PricingRule,
    PricingRuleCondition,
    ProviderContract,
    ProviderOrganization,
    RefProcedureCode,
    RefSpecialty,
)
from core.services.contract_resolver import (
    ContractResolutionAmbiguityError,
    ContractResolver,
)
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
from providers.services import OrgHierarchyDepthError, ProviderLookupService


class ResolutionPhaseBase(TestCase):
    SERVICE_DATE = date(2025, 6, 15)

    def _seed_contract_version(self, contract, version_number=1):
        return ContractVersion.objects.create(
            contract=contract,
            version_number=version_number,
            effective_start_date=date(2025, 1, 1),
            status=ContractVersion.VersionStatus.ACTIVE,
        )

    def setUp(self):
        self.resolver = PricingContextResolver()
        self.contract_resolver = ContractResolver()
        self.api = APIClient()

        self.idn_org = ProviderOrganization.objects.create(
            organization_id='ORG-R-IDN',
            name='IDN Parent',
            npi='IDN-NPI-R',
        )
        self.leaf_org = ProviderOrganization.objects.create(
            organization_id='ORG-R-LEAF',
            name='Leaf Practice',
            npi='LEAF-NPI-R',
            parent_org=self.idn_org,
        )
        self.billing_org = self.leaf_org

        self.core_payer_org = ProviderOrganization.objects.create(
            organization_id='ORG-R-PAYER',
            name='Payer Org',
        )
        self.legacy_network = PayerNetwork.objects.create(
            network_id='NET-R-01',
            network_name='R Network',
            payer_org=self.core_payer_org,
            line_of_business='COMMERCIAL',
        )
        self.products_payer = PayerOrganization.objects.create(
            name='R Products Payer',
            payer_id='PAYER-R-01',
            payer_type='COMMERCIAL',
        )
        self.lob = LineOfBusiness.objects.create(code='COMMERCIAL', name='Commercial')
        self.product = Product.objects.create(
            payer=self.products_payer,
            lob=self.lob,
            name='R Product',
            product_code='PROD-R-01',
            effective_date=date(2025, 1, 1),
        )
        self.network = Network.objects.create(
            payer=self.products_payer,
            name='R Products Network',
            network_type='PPO',
            network_code='R-NET',
            legacy_payer_network=self.legacy_network,
        )
        ProductNetworkConfig.objects.create(
            product=self.product,
            network=self.network,
            claim_type='PROFESSIONAL',
            effective_date=date(2025, 1, 1),
        )
        self.member = Member.objects.create(member_id='MEM-R-001', zip_code='60601')
        Enrollment.objects.create(
            member=self.member,
            product=self.product,
            effective_date=date(2025, 1, 1),
        )
        ProviderNetworkParticipation.objects.create(
            organization=self.billing_org,
            network=self.legacy_network,
            network_new=self.network,
            status='IN_NETWORK',
            effective_date=date(2025, 1, 1),
        )
        self.specialty = RefSpecialty.objects.create(
            specialty_code='FAM', description='Family Medicine'
        )
        self.rendering = Provider.objects.create(
            npi='RENDER-NPI-R',
            first_name='R',
            last_name='Provider',
            primary_specialty=self.specialty,
        )
        ProviderAffiliation.objects.create(
            provider=self.rendering,
            organization=self.billing_org,
            effective_date=date(2025, 1, 1),
        )
        RefProcedureCode.objects.create(code_id='99213', description='Office Visit')

    def _create_contract(
        self,
        *,
        org=None,
        origin='DIRECT',
        priority=10,
        legacy_number='CONT-R-BASE',
    ):
        contract = ProviderContract.objects.create(
            contract_name=f'Contract {legacy_number}',
            legacy_contract_number=legacy_number,
            status='ACTIVE',
            effective_start_date=date(2025, 1, 1),
            provider_org=org or self.billing_org,
            network=self.legacy_network,
            line_of_business='COMMERCIAL',
            contract_origin_type=origin,
            resolution_priority=priority,
        )
        ContractProductScope.objects.create(
            contract=contract,
            lob_code='COMMERCIAL',
            product=self.product,
            effective_date=date(2025, 1, 1),
        )
        rule = PricingRule.objects.create(
            contract=contract,
            rule_name='Flat 99213',
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
        self._seed_contract_version(contract)
        return contract


class R2VersionIdPropagationTests(ResolutionPhaseBase):
    def test_context_version_id_non_null_after_resolve(self):
        contract = self._create_contract()
        raw = RawClaimInput(
            billing_npi='LEAF-NPI-R',
            rendering_npi='RENDER-NPI-R',
            member_id='MEM-R-001',
            service_date=self.SERVICE_DATE,
            claim_type='professional',
            lines=[{'procedure_code': '99213', 'billed_amount': '200.00', 'units': 1}],
        )
        ctx = self.resolver.resolve(raw)
        self.assertIsNotNone(ctx.version_id)
        version = ContractVersion.objects.get(version_id=ctx.version_id)
        self.assertEqual(version.contract_id, contract.contract_id)


class R3TieBreakingTests(ResolutionPhaseBase):
    def test_direct_wins_over_leased_same_org_network(self):
        direct = self._create_contract(
            origin='DIRECT',
            priority=10,
            legacy_number='CONT-R-DIRECT',
        )
        self._create_contract(
            origin='LEASED',
            priority=20,
            legacy_number='CONT-R-LEASED',
        )
        contract_id = self.contract_resolver.resolve(
            org_id=self.billing_org.organization_id,
            network_id=self.network.id,
            lob='COMMERCIAL',
            service_date=self.SERVICE_DATE,
            product_id=self.product.id,
        )
        self.assertEqual(contract_id, direct.contract_id)

    def test_ambiguity_when_same_priority(self):
        self._create_contract(priority=10, legacy_number='CONT-R-A')
        self._create_contract(priority=10, legacy_number='CONT-R-B')
        with self.assertRaises(ContractResolutionAmbiguityError):
            self.contract_resolver.resolve(
                org_id=self.billing_org.organization_id,
                network_id=self.network.id,
                lob='COMMERCIAL',
                service_date=self.SERVICE_DATE,
                product_id=self.product.id,
            )

    def test_reprice_ambiguous_returns_200_not_500(self):
        self._create_contract(priority=10, legacy_number='CONT-R-A')
        self._create_contract(priority=10, legacy_number='CONT-R-B')
        payload = {
            'billing_npi': 'LEAF-NPI-R',
            'member_id': 'MEM-R-001',
            'service_date': '2025-06-15',
            'claim_type': 'professional',
            'lines': [
                {'procedure_code': '99213', 'billed_amount': '200.00', 'units': 1, 'modifiers': []}
            ],
        }
        response = self.api.post('/api/reprice-claim/', payload, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['status'], 'AMBIGUOUS')
        self.assertIsNone(response.data['contract_id'])
        self.assertEqual(response.data['lines'], [])
        self.assertIn('message', response.data)

    def test_resolve_context_ambiguous_returns_200(self):
        self._create_contract(priority=10, legacy_number='CONT-R-A')
        self._create_contract(priority=10, legacy_number='CONT-R-B')
        response = self.api.get(
            '/api/resolve-context/',
            {
                'billing_npi': 'LEAF-NPI-R',
                'member_id': 'MEM-R-001',
                'service_date': '2025-06-15',
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['resolution_mode'], 'AMBIGUOUS')
        self.assertIsNone(response.data['contract_id'])

    def test_reprice_batch_ambiguous_isolated_per_row(self):
        self._create_contract(priority=10, legacy_number='CONT-R-A')
        self._create_contract(priority=10, legacy_number='CONT-R-B')
        payload = {
            'claims': [
                {
                    'billing_npi': 'LEAF-NPI-R',
                    'member_id': 'MEM-R-001',
                    'service_date': '2025-06-15',
                    'claim_type': 'professional',
                    'lines': [
                        {'procedure_code': '99213', 'billed_amount': '200.00', 'units': 1}
                    ],
                },
            ],
        }
        response = self.api.post('/api/reprice-claim-batch/', payload, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 1)
        row = response.data['results'][0]
        self.assertEqual(row['status'], 'AMBIGUOUS')
        self.assertEqual(row['lines'], [])


class R4ResolutionLogTests(ResolutionPhaseBase):
    def test_reprice_twice_creates_two_log_rows_different_versions(self):
        contract = self._create_contract()
        v1 = ContractVersion.objects.get(contract=contract, version_number=1)

        payload = {
            'billing_npi': 'LEAF-NPI-R',
            'member_id': 'MEM-R-001',
            'service_date': '2025-06-15',
            'claim_type': 'professional',
            'lines': [
                {'procedure_code': '99213', 'billed_amount': '200.00', 'units': 1, 'modifiers': []}
            ],
        }
        r1 = self.api.post('/api/reprice-claim/', payload, format='json')
        self.assertEqual(r1.status_code, 200)
        self.assertEqual(
            ClaimResolutionLog.objects.get(pk=r1.data['resolution_log_id']).resolved_version_id,
            v1.version_id,
        )

        v2 = ContractVersion.objects.create(
            contract=contract,
            version_number=2,
            effective_start_date=date(2025, 6, 1),
            status=ContractVersion.VersionStatus.ACTIVE,
        )
        v1.status = ContractVersion.VersionStatus.SUPERSEDED
        v1.save(update_fields=['status'])

        r2 = self.api.post('/api/reprice-claim/', payload, format='json')
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(
            ClaimResolutionLog.objects.get(pk=r2.data['resolution_log_id']).resolved_version_id,
            v2.version_id,
        )

        all_logs = ClaimResolutionLog.objects.filter(resolved_contract=contract).order_by('id')
        self.assertEqual(all_logs.count(), 2)
        version_ids = {log.resolved_version_id for log in all_logs}
        self.assertEqual(version_ids, {v1.version_id, v2.version_id})

    def test_resolution_log_get_by_trace_id(self):
        contract = self._create_contract()
        payload = {
            'billing_npi': 'LEAF-NPI-R',
            'member_id': 'MEM-R-001',
            'service_date': '2025-06-15',
            'claim_type': 'professional',
            'lines': [
                {'procedure_code': '99213', 'billed_amount': '200.00', 'units': 1, 'modifiers': []}
            ],
        }
        resp = self.api.post('/api/reprice-claim/', payload, format='json')
        trace_id = resp.data['trace_id']
        get_resp = self.api.get(f'/api/resolution-log/{trace_id}/')
        self.assertEqual(get_resp.status_code, 200)
        self.assertEqual(get_resp.data['count'], 1)
        UUID(trace_id)


class R5HierarchyTests(ResolutionPhaseBase):
    def test_resolve_org_hierarchy_leaf_to_idn(self):
        svc = ProviderLookupService()
        chain = svc.resolve_org_hierarchy('LEAF-NPI-R', self.SERVICE_DATE)
        self.assertEqual(len(chain), 2)
        self.assertEqual(chain[0].organization_id, 'ORG-R-LEAF')
        self.assertEqual(chain[1].organization_id, 'ORG-R-IDN')

    def test_contract_at_idn_resolves_for_leaf_npi(self):
        idn_contract = ProviderContract.objects.create(
            contract_name='IDN Contract',
            legacy_contract_number='CONT-R-IDN',
            status='ACTIVE',
            effective_start_date=date(2025, 1, 1),
            provider_org=self.idn_org,
            network=self.legacy_network,
            line_of_business='COMMERCIAL',
        )
        ContractProductScope.objects.create(
            contract=idn_contract,
            lob_code='COMMERCIAL',
            product=self.product,
            effective_date=date(2025, 1, 1),
        )
        self._seed_contract_version(idn_contract)

        raw = RawClaimInput(
            billing_npi='LEAF-NPI-R',
            member_id='MEM-R-001',
            service_date=self.SERVICE_DATE,
            claim_type='professional',
            lines=[],
        )
        ctx = self.resolver.resolve(raw)
        self.assertEqual(ctx.contract_id, idn_contract.contract_id)

    def test_hierarchy_cycle_raises(self):
        self.leaf_org.parent_org = self.leaf_org
        self.leaf_org.save(update_fields=['parent_org'])
        svc = ProviderLookupService()
        with self.assertRaises(OrgHierarchyDepthError):
            svc.resolve_org_hierarchy('LEAF-NPI-R', self.SERVICE_DATE)


class R6UnifiedPathTests(ResolutionPhaseBase):
    def test_stored_claim_price_uses_context_resolver(self):
        contract = self._create_contract()
        header = ClaimHeader.objects.create(
            contract=contract,
            member_id='MEM-R-001',
            billing_npi='LEAF-NPI-R',
            service_date=self.SERVICE_DATE,
            claim_type='professional',
        )
        ClaimLine.objects.create(
            claim=header,
            procedure_code='99213',
            billed_amount=Decimal('200.00'),
            units=1,
            sequence=0,
        )
        resp = self.api.post(f'/api/claims/{header.claim_id}/price/', format='json')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('resolution_log_id', resp.data)
        log = ClaimResolutionLog.objects.get(pk=resp.data['resolution_log_id'])
        self.assertEqual(log.claim_header_id, header.claim_id)
        self.assertEqual(log.resolution_path, ClaimResolutionLog.ResolutionPath.CONTEXT_RESOLVER)
