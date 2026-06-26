from django.db import models


class Member(models.Model):
    """Individual covered by an insurance product."""

    class Relationship(models.TextChoices):
        SELF = 'SELF', 'Self'
        SPOUSE = 'SPOUSE', 'Spouse'
        DEPENDENT = 'DEPENDENT', 'Dependent'
        OTHER = 'OTHER', 'Other'

    id = models.BigAutoField(primary_key=True)
    member_id = models.CharField(max_length=64, unique=True, db_index=True)
    first_name = models.CharField(max_length=100, null=True, blank=True)
    last_name = models.CharField(max_length=100, null=True, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    zip_code = models.CharField(max_length=10, null=True, blank=True)
    subscriber_id = models.CharField(max_length=64, null=True, blank=True, db_index=True)
    relationship_to_subscriber = models.CharField(
        max_length=20,
        default=Relationship.SELF,
        choices=Relationship.choices,
    )
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'members'
        indexes = [
            models.Index(fields=['member_id']),
        ]

    def __str__(self) -> str:
        return f"{self.member_id} ({self.last_name}, {self.first_name})"


class Enrollment(models.Model):
    """Member's enrollment in a specific Product on a date range."""

    id = models.BigAutoField(primary_key=True)
    member = models.ForeignKey(
        Member,
        on_delete=models.CASCADE,
        related_name='enrollments',
    )
    product = models.ForeignKey(
        'products.Product',
        on_delete=models.PROTECT,
        related_name='enrollments',
    )
    effective_date = models.DateField(db_index=True)
    termination_date = models.DateField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'enrollments'
        indexes = [
            models.Index(fields=['member', 'effective_date']),
            models.Index(fields=['member', 'termination_date']),
        ]

    def __str__(self) -> str:
        return f"{self.member_id} → {self.product_id} ({self.effective_date})"
