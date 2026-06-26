from django.db import models
from django.db.models import Q


class Provider(models.Model):
    """Individual rendering provider — NPI Type 1."""

    id = models.BigAutoField(primary_key=True)
    npi = models.CharField(max_length=15, unique=True, db_index=True)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    credential = models.CharField(max_length=50, null=True, blank=True)
    primary_taxonomy = models.CharField(max_length=20, null=True, blank=True)
    primary_specialty = models.ForeignKey(
        'core.RefSpecialty',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    status = models.CharField(max_length=20, default='ACTIVE')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'providers'
        indexes = [
            models.Index(fields=['npi']),
        ]

    def __str__(self) -> str:
        return f"{self.last_name}, {self.first_name} ({self.npi})"


class Facility(models.Model):
    """Physical facility — NPI Type 2 for places of service."""

    class FacilityType(models.TextChoices):
        HOSPITAL_INPATIENT = 'HOSPITAL_INPATIENT', 'Hospital Inpatient'
        HOSPITAL_OUTPATIENT = 'HOSPITAL_OUTPATIENT', 'Hospital Outpatient'
        ASC = 'ASC', 'Ambulatory Surgery Center'
        SNF = 'SNF', 'Skilled Nursing Facility'
        FQHC = 'FQHC', 'Federally Qualified Health Center'
        OFFICE = 'OFFICE', 'Office'
        LAB = 'LAB', 'Laboratory'
        IMAGING = 'IMAGING', 'Imaging'

    id = models.BigAutoField(primary_key=True)
    npi = models.CharField(max_length=15, unique=True, db_index=True)
    ccn = models.CharField(max_length=20, null=True, blank=True)
    name = models.CharField(max_length=255)
    facility_type = models.CharField(max_length=50)
    place_of_service_codes = models.JSONField(default=list)
    address_json = models.JSONField(null=True, blank=True)
    status = models.CharField(max_length=20, default='ACTIVE')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'facilities'

    def __str__(self) -> str:
        return f"{self.name} ({self.npi})"


class ProviderAffiliation(models.Model):
    """Dated relationship: rendering provider works under billing org."""

    class Role(models.TextChoices):
        EMPLOYEE = 'EMPLOYEE', 'Employee'
        CONTRACTOR = 'CONTRACTOR', 'Contractor'
        LOCUM = 'LOCUM', 'Locum Tenens'
        ADMITTING = 'ADMITTING', 'Admitting'
        COVERING = 'COVERING', 'Covering'

    id = models.BigAutoField(primary_key=True)
    provider = models.ForeignKey(
        Provider,
        on_delete=models.CASCADE,
        related_name='affiliations',
    )
    organization = models.ForeignKey(
        'core.ProviderOrganization',
        on_delete=models.CASCADE,
        related_name='provider_affiliations',
    )
    role = models.CharField(
        max_length=30,
        default=Role.EMPLOYEE,
        choices=Role.choices,
    )
    effective_date = models.DateField()
    termination_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'provider_affiliations'
        indexes = [
            models.Index(fields=['provider', 'organization', 'effective_date']),
        ]

    def __str__(self) -> str:
        return f"{self.provider_id} @ {self.organization_id} ({self.role})"


class ProviderNetworkParticipation(models.Model):
    """Org or individual provider participation in a payer network on a date range."""

    class Status(models.TextChoices):
        IN_NETWORK = 'IN_NETWORK', 'In-Network'
        OUT_OF_NETWORK = 'OUT_OF_NETWORK', 'Out-of-Network'
        TIER_1 = 'TIER_1', 'Tier 1'
        TIER_2 = 'TIER_2', 'Tier 2'

    class ParticipationSource(models.TextChoices):
        DIRECT_CONTRACT = 'DIRECT_CONTRACT', 'Direct Contract'
        NETWORK_ARRANGEMENT = 'NETWORK_ARRANGEMENT', 'Network Arrangement'

    id = models.BigAutoField(primary_key=True)
    organization = models.ForeignKey(
        'core.ProviderOrganization',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='network_participations',
    )
    provider = models.ForeignKey(
        Provider,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='network_participations',
    )
    network = models.ForeignKey(
        'core.PayerNetwork',
        on_delete=models.CASCADE,
        related_name='provider_participations',
    )
    network_new = models.ForeignKey(
        'products.Network',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column='network_new_id',
        related_name='provider_participations_new',
    )
    contract = models.ForeignKey(
        'core.ProviderContract',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='network_participations',
    )
    participation_source = models.CharField(
        max_length=30,
        choices=ParticipationSource.choices,
        default=ParticipationSource.NETWORK_ARRANGEMENT,
    )
    status = models.CharField(
        max_length=20,
        default=Status.IN_NETWORK,
        choices=Status.choices,
    )
    effective_date = models.DateField()
    termination_date = models.DateField(null=True, blank=True)
    specialty_scope = models.CharField(max_length=50, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'provider_network_participations'
        indexes = [
            models.Index(fields=['organization', 'network', 'effective_date']),
            models.Index(fields=['provider', 'network', 'effective_date']),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(organization__isnull=False) | Q(provider__isnull=False),
                name='participation_must_have_org_or_provider',
            ),
        ]

    def __str__(self) -> str:
        subject = self.organization_id or f"provider:{self.provider_id}"
        return f"{subject} in {self.network_id} ({self.status})"


class FacilityNetworkParticipation(models.Model):
    """Facility participation in a payer network."""

    id = models.BigAutoField(primary_key=True)
    facility = models.ForeignKey(
        Facility,
        on_delete=models.CASCADE,
        related_name='network_participations',
    )
    network = models.ForeignKey(
        'core.PayerNetwork',
        on_delete=models.CASCADE,
    )
    status = models.CharField(max_length=20, default='IN_NETWORK')
    effective_date = models.DateField()
    termination_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'facility_network_participations'
        indexes = [
            models.Index(fields=['facility', 'network', 'effective_date']),
        ]

    def __str__(self) -> str:
        return f"{self.facility_id} in {self.network_id} ({self.status})"
