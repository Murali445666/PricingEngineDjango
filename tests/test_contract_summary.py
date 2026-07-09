"""Unit tests for ContractSummaryService (§13 layer read model)."""
from datetime import date
from decimal import Decimal

from django.core.exceptions import ObjectDoesNotExist
from django.test import TestCase

from core.models import (
    ContractArrangement,
    ContractCoveredEntity,
    ContractProductScope,
    ContractScope,
    PayerNetwork,
    PricingRule,
    ProviderContract,
    ProviderOrganization,
)
from core.services.contract_summary import ContractSummaryService


class ContractSummaryServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        payer_side = ProviderOrganization.objects.create(
            organization_id='SUM-PAYER-ORG',
            name='Summary Payer Side Org',
            npi='9000000001',
        )
        provider_org = ProviderOrganization.objects.create(
            organization_id='SUM-PROV-ORG',
            name='Summary Provider Org',
            npi='9000000002',
        )
        network = PayerNetwork.objects.create(
            network_id='SUM-NET',
            network_name='Summary Network',
            payer_org=payer_side,
        )
        cls.contract = ProviderContract.objects.create(
            contract_name='Summary Test Contract',
            provider_org=provider_org,
            network=network,
            status='ACTIVE',
            effective_start_date=date(2025, 1, 1),
        )
        ContractCoveredEntity.objects.create(
            contract=cls.contract,
            entity_type=ContractCoveredEntity.EntityType.ORG,
            organization=provider_org,
            is_primary=True,
            effective_start_date=date(2025, 1, 1),
        )
        cls.arrangement = ContractArrangement.objects.create(
            contract=cls.contract,
            name='RBRVS Fee Schedule (RBRVS)',
            arrangement_type=ContractArrangement.ArrangementType.FEE_SCHEDULE,
            status='ACTIVE',
            effective_start_date=date(2025, 1, 1),
        )
        PricingRule.objects.create(
            contract=cls.contract,
            rule_name='Summary RBRVS Rule',
            rule_type='BASE',
            methodology_code='RBRVS',
            multiplier=Decimal('1.0000'),
            status='ACTIVE',
            effective_start_date=date(2025, 1, 1),
            arrangement=cls.arrangement,
        )
        ContractScope.objects.create(
            contract=cls.contract,
            line_of_business='COMMERCIAL',
            priority=100,
        )
        ContractProductScope.objects.create(
            contract=cls.contract,
            lob_code='COMMERCIAL',
        )

    def test_build_returns_layered_view(self):
        summary = ContractSummaryService.build(self.contract.contract_id)

        self.assertEqual(summary['contract_id'], self.contract.contract_id)
        self.assertEqual(summary['contract_name'], 'Summary Test Contract')
        self.assertIn('parties', summary)
        self.assertEqual(summary['parties']['provider_org']['organization_id'], 'SUM-PROV-ORG')
        self.assertEqual(summary['parties']['network']['network_id'], 'SUM-NET')
        self.assertIsNone(summary['parties']['payer_org'])

        self.assertEqual(len(summary['covered_entities']), 1)
        self.assertTrue(summary['covered_entities'][0]['is_primary'])
        self.assertEqual(summary['covered_entities'][0]['entity_type'], 'ORG')

        self.assertEqual(len(summary['arrangements']), 1)
        self.assertEqual(summary['arrangements'][0]['arrangement_type'], 'FEE_SCHEDULE')
        self.assertEqual(len(summary['arrangements'][0]['rules']), 1)
        self.assertEqual(summary['arrangements'][0]['rules'][0]['methodology_code'], 'RBRVS')

        self.assertEqual(len(summary['scopes']), 1)
        self.assertEqual(len(summary['product_scopes']), 1)
        self.assertIsInstance(summary['documents'], list)
        self.assertIsInstance(summary['amendments'], list)

    def test_build_raises_for_missing_contract(self):
        with self.assertRaises(ObjectDoesNotExist):
            ContractSummaryService.build(self.contract.contract_id + 99999)
