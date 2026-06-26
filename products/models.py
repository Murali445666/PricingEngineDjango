from django.db import models


class PayerOrganization(models.Model):
    """A payer: insurance company, TPA, or government payer."""

    class PayerType(models.TextChoices):
        COMMERCIAL = 'COMMERCIAL', 'Commercial'
        MEDICARE_ADVANTAGE = 'MEDICARE_ADVANTAGE', 'Medicare Advantage'
        MEDICAID = 'MEDICAID', 'Medicaid'
        SELF_FUNDED = 'SELF_FUNDED', 'Self-Funded'
        TPA = 'TPA', 'TPA'
        CMS = 'CMS', 'CMS/Medicare FFS'

    id = models.BigAutoField(primary_key=True)
    name = models.CharField(max_length=255)
    payer_id = models.CharField(max_length=50, unique=True, db_index=True)
    payer_type = models.CharField(max_length=30, choices=PayerType.choices)
    parent_name = models.CharField(max_length=255, null=True, blank=True)
    legacy_provider_org = models.OneToOneField(
        'core.ProviderOrganization',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column='legacy_provider_org_id',
        related_name='payer_org_record',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'payer_organizations'

    def __str__(self) -> str:
        return f"{self.name} ({self.payer_id})"


class LineOfBusiness(models.Model):
    """Top-level segment: Commercial, MA, Medicaid, Exchange, Self-Funded."""

    class Code(models.TextChoices):
        COMMERCIAL = 'COMMERCIAL', 'Commercial'
        MEDICARE_ADVANTAGE = 'MEDICARE_ADVANTAGE', 'Medicare Advantage'
        MEDICAID = 'MEDICAID', 'Medicaid'
        EXCHANGE = 'EXCHANGE', 'Exchange / ACA'
        SELF_FUNDED = 'SELF_FUNDED', 'Self-Funded'
        MEDICARE_FFS = 'MEDICARE_FFS', 'Medicare Fee-for-Service'

    id = models.BigAutoField(primary_key=True)
    code = models.CharField(max_length=30, unique=True, choices=Code.choices)
    name = models.CharField(max_length=100)

    class Meta:
        db_table = 'lines_of_business'
        verbose_name_plural = 'Lines of Business'

    def __str__(self) -> str:
        return f"{self.code} — {self.name}"


class Product(models.Model):
    """A named insurance product offered by a payer under a specific LOB."""

    id = models.BigAutoField(primary_key=True)
    payer = models.ForeignKey(
        PayerOrganization,
        on_delete=models.CASCADE,
        related_name='products',
    )
    lob = models.ForeignKey(
        LineOfBusiness,
        on_delete=models.PROTECT,
        related_name='products',
    )
    name = models.CharField(max_length=255)
    product_code = models.CharField(max_length=50, null=True, blank=True)
    effective_date = models.DateField()
    termination_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'products'
        indexes = [
            models.Index(fields=['payer', 'effective_date']),
        ]

    def __str__(self) -> str:
        return self.name


class Network(models.Model):
    """First-class network model bridged to legacy core.PayerNetwork."""

    class NetworkType(models.TextChoices):
        PPO = 'PPO', 'PPO'
        HMO = 'HMO', 'HMO'
        EPO = 'EPO', 'EPO'
        POS = 'POS', 'POS'
        ACO = 'ACO', 'ACO'
        NARROW = 'NARROW', 'Narrow'
        TIERED = 'TIERED', 'Tiered'

    id = models.BigAutoField(primary_key=True)
    payer = models.ForeignKey(
        PayerOrganization,
        on_delete=models.CASCADE,
        related_name='networks',
    )
    name = models.CharField(max_length=255)
    network_code = models.CharField(max_length=50, null=True, blank=True, db_index=True)
    network_type = models.CharField(max_length=20, choices=NetworkType.choices)
    legacy_payer_network = models.OneToOneField(
        'core.PayerNetwork',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='network_record',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'networks'

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.legacy_payer_network_id is None:
            raise ValidationError({
                'legacy_payer_network': (
                    'Network must be linked to a core.PayerNetwork via '
                    'legacy_payer_network for contract resolution to work. '
                    'Create or identify the corresponding PayerNetwork first.'
                )
            })

    def __str__(self) -> str:
        return self.name


class ProductNetworkConfig(models.Model):
    """Which network a product uses for a given claim type and date range."""

    class ClaimType(models.TextChoices):
        ALL = 'ALL', 'All'
        PROFESSIONAL = 'PROFESSIONAL', 'Professional'
        INSTITUTIONAL = 'INSTITUTIONAL', 'Institutional'
        BEHAVIORAL_HEALTH = 'BEHAVIORAL_HEALTH', 'Behavioral Health'

    id = models.BigAutoField(primary_key=True)
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='network_configs',
    )
    network = models.ForeignKey(
        Network,
        on_delete=models.CASCADE,
        related_name='product_configs',
    )
    claim_type = models.CharField(
        max_length=30,
        default=ClaimType.ALL,
        choices=ClaimType.choices,
    )
    effective_date = models.DateField()
    termination_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'product_network_configs'
        indexes = [
            models.Index(fields=['product', 'claim_type', 'effective_date']),
        ]

    def __str__(self) -> str:
        return f"{self.product_id} → {self.network_id} ({self.claim_type})"
