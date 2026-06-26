from datetime import date

from django.test import TestCase

from core.models import ClaimHeader, ProviderOrganization
from members.models import Enrollment, Member
from members.services import MemberLookupService
from products.models import LineOfBusiness, PayerOrganization, Product
from providers.models import Facility, Provider


class Stage3MemberDomainTests(TestCase):
    """Stage 3 — Member / Enrollment domain and ClaimHeader enrichment tests."""

    def setUp(self):
        self.lookup = MemberLookupService()
        self.payer = PayerOrganization.objects.create(
            name='Stage 3 Payer',
            payer_id='PAYER-S3-01',
            payer_type='COMMERCIAL',
        )
        self.lob = LineOfBusiness.objects.create(
            code='COMMERCIAL',
            name='Commercial',
        )
        self.product = Product.objects.create(
            payer=self.payer,
            lob=self.lob,
            name='Stage 3 Product',
            effective_date=date(2025, 1, 1),
        )

    def test_create_member_and_retrieve_by_member_id(self):
        member = Member.objects.create(
            member_id='MEM-S3-001',
            first_name='Alice',
            last_name='Johnson',
            zip_code='90210',
        )
        loaded = Member.objects.get(member_id='MEM-S3-001')
        self.assertEqual(loaded.pk, member.pk)
        self.assertEqual(loaded.last_name, 'Johnson')

    def test_enrollment_links_member_to_product(self):
        member = Member.objects.create(member_id='MEM-S3-ENR-01', last_name='Lee')
        enrollment = Enrollment.objects.create(
            member=member,
            product=self.product,
            effective_date=date(2025, 1, 1),
        )
        self.assertEqual(enrollment.member_id, member.pk)
        self.assertEqual(enrollment.product_id, self.product.pk)
        self.assertEqual(member.enrollments.count(), 1)

    def test_resolve_enrollment_date_scoping(self):
        member = Member.objects.create(member_id='MEM-S3-RES-01', last_name='Brown')
        enrollment = Enrollment.objects.create(
            member=member,
            product=self.product,
            effective_date=date(2025, 1, 1),
            termination_date=date(2025, 12, 31),
        )
        resolved = self.lookup.resolve_enrollment('MEM-S3-RES-01', date(2025, 6, 15))
        self.assertIsNotNone(resolved)
        self.assertEqual(resolved.pk, enrollment.pk)

        self.assertIsNone(
            self.lookup.resolve_enrollment('MEM-S3-RES-01', date(2024, 12, 31))
        )
        self.assertIsNone(
            self.lookup.resolve_enrollment('MEM-S3-RES-01', date(2026, 1, 1))
        )
        self.assertIsNone(
            self.lookup.resolve_enrollment('MEM-NOT-FOUND', date(2025, 6, 15))
        )

    def test_resolve_enrollment_prefers_most_recent_effective(self):
        member = Member.objects.create(member_id='MEM-S3-MULTI', last_name='Multi')
        older_product = Product.objects.create(
            payer=self.payer,
            lob=self.lob,
            name='Older Product',
            effective_date=date(2024, 1, 1),
        )
        newer_product = Product.objects.create(
            payer=self.payer,
            lob=self.lob,
            name='Newer Product',
            effective_date=date(2025, 1, 1),
        )
        Enrollment.objects.create(
            member=member,
            product=older_product,
            effective_date=date(2025, 1, 1),
            termination_date=None,
        )
        newer_enrollment = Enrollment.objects.create(
            member=member,
            product=newer_product,
            effective_date=date(2025, 6, 1),
            termination_date=None,
        )
        resolved = self.lookup.resolve_enrollment('MEM-S3-MULTI', date(2025, 7, 1))
        self.assertEqual(resolved.pk, newer_enrollment.pk)
        self.assertEqual(resolved.product_id, newer_product.pk)

    def test_get_lob_for_active_enrollment(self):
        member = Member.objects.create(member_id='MEM-S3-LOB', last_name='Lob')
        Enrollment.objects.create(
            member=member,
            product=self.product,
            effective_date=date(2025, 1, 1),
        )
        self.assertEqual(
            self.lookup.get_lob('MEM-S3-LOB', date(2025, 6, 1)),
            'COMMERCIAL',
        )
        self.assertIsNone(
            self.lookup.get_lob('MEM-S3-LOB', date(2024, 1, 1))
        )

    def test_get_locality_zip(self):
        Member.objects.create(
            member_id='MEM-S3-ZIP',
            last_name='Zip',
            zip_code='10001',
        )
        self.assertEqual(self.lookup.get_locality_zip('MEM-S3-ZIP'), '10001')
        self.assertIsNone(self.lookup.get_locality_zip('MEM-MISSING'))

    def test_get_product_from_active_enrollment(self):
        member = Member.objects.create(member_id='MEM-S3-PROD', last_name='Prod')
        Enrollment.objects.create(
            member=member,
            product=self.product,
            effective_date=date(2025, 1, 1),
        )
        product = self.lookup.get_product('MEM-S3-PROD', date(2025, 6, 1))
        self.assertIsNotNone(product)
        self.assertEqual(product.pk, self.product.pk)

    def test_claim_header_with_all_new_fields_populated(self):
        provider_org = ProviderOrganization.objects.create(
            organization_id='ORG-S3-CLAIM',
            name='Claim Org',
        )
        provider = Provider.objects.create(
            npi='1558555555',
            first_name='Render',
            last_name='Provider',
        )
        facility = Facility.objects.create(
            npi='1668666666',
            name='Stage 3 Facility',
            facility_type='OFFICE',
        )
        member = Member.objects.create(
            member_id='MEM-S3-CLAIM',
            last_name='ClaimMember',
        )
        claim = ClaimHeader.objects.create(
            provider_org=provider_org,
            npi='1778777777',
            member_id='MEM-S3-CLAIM',
            service_date=date(2025, 6, 1),
            rendering_provider=provider,
            facility=facility,
            member_fk=member,
            billing_npi='1888888888',
        )
        loaded = ClaimHeader.objects.select_related(
            'rendering_provider', 'facility', 'member_fk'
        ).get(pk=claim.pk)
        self.assertEqual(loaded.rendering_provider_id, provider.pk)
        self.assertEqual(loaded.facility_id, facility.pk)
        self.assertEqual(loaded.member_fk_id, member.pk)
        self.assertEqual(loaded.billing_npi, '1888888888')
        self.assertEqual(loaded.npi, '1778777777')
        self.assertEqual(loaded.member_id, 'MEM-S3-CLAIM')

    def test_claim_header_without_new_fields_still_works(self):
        provider_org = ProviderOrganization.objects.create(
            organization_id='ORG-S3-LEGACY',
            name='Legacy Claim Org',
        )
        claim = ClaimHeader.objects.create(
            provider_org=provider_org,
            npi='1999999999',
            member_id='LEGACY-MEMBER-STR',
            service_date=date(2025, 6, 1),
        )
        loaded = ClaimHeader.objects.get(pk=claim.pk)
        self.assertIsNone(loaded.rendering_provider_id)
        self.assertIsNone(loaded.facility_id)
        self.assertIsNone(loaded.member_fk_id)
        self.assertIsNone(loaded.billing_npi)
        self.assertEqual(loaded.npi, '1999999999')
        self.assertEqual(loaded.member_id, 'LEGACY-MEMBER-STR')

    def test_legacy_claim_header_new_fields_are_null(self):
        """Simulates pre-Stage-3 ClaimHeader rows: new FK columns remain null."""
        claim = ClaimHeader.objects.create(
            service_date=date(2025, 1, 15),
            claim_type='PROFESSIONAL',
        )
        reloaded = ClaimHeader.objects.get(pk=claim.claim_id)
        self.assertIsNone(reloaded.rendering_provider_id)
        self.assertIsNone(reloaded.facility_id)
        self.assertIsNone(reloaded.member_fk_id)
        self.assertIsNone(reloaded.billing_npi)
        self.assertIsNone(reloaded.npi)
        self.assertIsNone(reloaded.member_id)
