from datetime import date

from django.db.models import Q

from members.models import Enrollment, Member
from products.models import Product


class MemberLookupService:
    """Read-only lookups for member enrollment and product context."""

    def resolve_enrollment(
        self, member_id: str, service_date: date
    ) -> Enrollment | None:
        """
        Return the active Enrollment for member_id on service_date.
        Filter: effective_date <= service_date AND
                (termination_date is null OR termination_date >= service_date).
        If multiple active enrollments exist, return the most recently effective one.
        Returns None if member not found or no active enrollment.
        """
        if not member_id:
            return None
        member = Member.objects.filter(member_id=member_id).first()
        if member is None:
            return None
        return (
            Enrollment.objects.filter(
                member=member,
                effective_date__lte=service_date,
            )
            .filter(
                Q(termination_date__isnull=True)
                | Q(termination_date__gte=service_date)
            )
            .select_related('product', 'product__lob')
            .order_by('-effective_date')
            .first()
        )

    def get_product(
        self, member_id: str, service_date: date
    ) -> Product | None:
        """Return the Product from the active enrollment, or None."""
        enrollment = self.resolve_enrollment(member_id, service_date)
        if enrollment is None:
            return None
        return enrollment.product

    def get_lob(
        self, member_id: str, service_date: date
    ) -> str | None:
        """Return the LineOfBusiness.code from the active enrollment, or None."""
        enrollment = self.resolve_enrollment(member_id, service_date)
        if enrollment is None or enrollment.product_id is None:
            return None
        return enrollment.product.lob.code

    def get_locality_zip(self, member_id: str) -> str | None:
        """Return Member.zip_code for the given member_id string, or None."""
        if not member_id:
            return None
        member = Member.objects.filter(member_id=member_id).only('zip_code').first()
        if member is None:
            return None
        return member.zip_code
