from datetime import date

from django.db import IntegrityError
from django.test import TestCase

from core.models import PayerNetwork, ProviderOrganization
from providers.models import (
    Facility,
    Provider,
    ProviderAffiliation,
    ProviderNetworkParticipation,
)
from providers.services import ProviderLookupService


class Stage1ProviderDomainTests(TestCase):
    """Stage 1 — Provider domain model and lookup service tests."""

    def setUp(self):
        self.lookup = ProviderLookupService()

    def test_create_provider_and_retrieve_by_npi(self):
        provider = Provider.objects.create(
            npi='1234567890',
            first_name='Jane',
            last_name='Smith',
            credential='MD',
        )
        resolved = self.lookup.resolve_provider_by_rendering_npi('1234567890')
        self.assertIsNotNone(resolved)
        self.assertEqual(resolved.pk, provider.pk)
        self.assertEqual(resolved.last_name, 'Smith')
        self.assertIsNone(self.lookup.resolve_provider_by_rendering_npi('0000000000'))

    def test_create_facility_with_pos_codes_and_retrieve_by_npi(self):
        facility = Facility.objects.create(
            npi='1987654321',
            name='Metro Imaging Center',
            facility_type='IMAGING',
            place_of_service_codes=['22', '49'],
        )
        resolved = self.lookup.resolve_facility_by_npi('1987654321')
        self.assertIsNotNone(resolved)
        self.assertEqual(resolved.pk, facility.pk)
        self.assertEqual(resolved.place_of_service_codes, ['22', '49'])
        self.assertIsNone(self.lookup.resolve_facility_by_npi('0000000001'))

    def test_check_affiliation_date_scoping(self):
        org = ProviderOrganization.objects.create(
            organization_id='ORG-AFF-01',
            name='Affiliation Test Org',
        )
        provider = Provider.objects.create(
            npi='1111111111',
            first_name='John',
            last_name='Doe',
        )
        ProviderAffiliation.objects.create(
            provider=provider,
            organization=org,
            effective_date=date(2025, 1, 1),
            termination_date=date(2025, 12, 31),
        )
        self.assertTrue(
            self.lookup.check_affiliation(provider.pk, org.organization_id, date(2025, 6, 15))
        )
        self.assertFalse(
            self.lookup.check_affiliation(provider.pk, org.organization_id, date(2024, 12, 31))
        )
        self.assertFalse(
            self.lookup.check_affiliation(provider.pk, org.organization_id, date(2026, 1, 1))
        )

    def test_check_org_network_participation_date_scoping(self):
        payer_org = ProviderOrganization.objects.create(
            organization_id='PAYER-NET-01',
            name='Payer Org',
        )
        provider_org = ProviderOrganization.objects.create(
            organization_id='PROV-NET-01',
            name='Provider Org',
            npi='2222222222',
        )
        network = PayerNetwork.objects.create(
            network_id='NET-STAGE1-01',
            network_name='Stage 1 Network',
            payer_org=payer_org,
        )
        ProviderNetworkParticipation.objects.create(
            organization=provider_org,
            network=network,
            status='TIER_1',
            effective_date=date(2025, 1, 1),
            termination_date=date(2025, 6, 30),
        )
        self.assertEqual(
            self.lookup.check_org_network_participation(
                provider_org.organization_id,
                network.network_id,
                date(2025, 3, 1),
            ),
            'TIER_1',
        )
        self.assertIsNone(
            self.lookup.check_org_network_participation(
                provider_org.organization_id,
                network.network_id,
                date(2025, 7, 1),
            )
        )

    def test_provider_network_participation_requires_org_or_provider(self):
        payer_org = ProviderOrganization.objects.create(
            organization_id='PAYER-CHK-01',
            name='Payer Org Check',
        )
        network = PayerNetwork.objects.create(
            network_id='NET-CHK-01',
            network_name='Check Network',
            payer_org=payer_org,
        )
        with self.assertRaises(IntegrityError):
            ProviderNetworkParticipation.objects.create(
                organization=None,
                provider=None,
                network=network,
                effective_date=date(2025, 1, 1),
            )

    def test_provider_organization_new_fields_nullable(self):
        org = ProviderOrganization.objects.create(
            organization_id='ORG-LEGACY-01',
            name='Legacy Org Without New Fields',
        )
        loaded = ProviderOrganization.objects.get(pk=org.organization_id)
        self.assertIsNone(loaded.org_type)
        self.assertIsNone(loaded.parent_org_id)
        self.assertIsNone(loaded.npi_type)

        parent = ProviderOrganization.objects.create(
            organization_id='ORG-PARENT-01',
            name='Parent Health System',
            org_type='HEALTH_SYSTEM',
            npi_type='2',
        )
        child = ProviderOrganization.objects.create(
            organization_id='ORG-CHILD-01',
            name='Child Group',
            org_type='GROUP',
            parent_org=parent,
            npi_type='2',
        )
        self.assertEqual(child.parent_org_id, parent.organization_id)
        self.assertEqual(child.org_type, 'GROUP')
        self.assertEqual(child.npi_type, '2')

        billing_org = ProviderOrganization.objects.create(
            organization_id='ORG-BILLING-01',
            name='Billing Org',
            npi='3333333333',
        )
        resolved = self.lookup.resolve_org_by_billing_npi('3333333333')
        self.assertIsNotNone(resolved)
        self.assertEqual(resolved.organization_id, billing_org.organization_id)
