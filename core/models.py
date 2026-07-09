from django.db import models
from django.db.models import Q

# ==========================================
# 1. REFERENCE DATA (The Foundation)
# ==========================================

class RefProcedureCode(models.Model):
    # Physical Table: ref_procedure_codes (Composite PK: code_id + code_type)
    # Django Constraint: Must have one single primary_key=True field.
    # Logic: We treat code_id as the primary handle, but enforcing uniqueness via unique_together.
    code_id = models.CharField(max_length=20, primary_key=True) 
    code_type = models.CharField(max_length=8) # ENUM: 'CPT', 'HCPCS', 'DRG', 'REV_CODE'
    description = models.CharField(max_length=255, null=True, blank=True)
    
    # RBRVS Columns
    work_rvu = models.DecimalField(max_digits=10, decimal_places=4, default=0.0000)
    pe_rvu = models.DecimalField(max_digits=10, decimal_places=4, default=0.0000)
    mp_rvu = models.DecimalField(max_digits=10, decimal_places=4, default=0.0000)
    conversion_factor = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    
    effective_start_date = models.DateField(default='1900-01-01')
    effective_end_date = models.DateField(null=True, blank=True)

    class Meta:
        managed = True # Django will NOT create/alter this table
        db_table = 'ref_procedure_codes'
        unique_together = (('code_id', 'code_type'),)

class RefModifier(models.Model):
    # Physical Table: ref_modifiers
    modifier_code = models.CharField(max_length=5, primary_key=True)
    description = models.CharField(max_length=255, null=True, blank=True)
    impact_type = models.CharField(max_length=50, null=True, blank=True)
    percentage_adjustment = models.DecimalField(max_digits=5, decimal_places=2, default=100.00)

    class Meta:
        managed = True
        db_table = 'ref_modifiers'

class RefGeoIndex(models.Model):
    # Physical Table: ref_geo_indices
    geo_id = models.AutoField(primary_key=True)
    locality_code = models.CharField(max_length=20, null=True, blank=True)
    description = models.CharField(max_length=100, null=True, blank=True)
    gpci_work = models.DecimalField(max_digits=6, decimal_places=4, null=True, blank=True)
    gpci_pe = models.DecimalField(max_digits=6, decimal_places=4, null=True, blank=True)
    gpci_mp = models.DecimalField(max_digits=6, decimal_places=4, null=True, blank=True)
    year = models.IntegerField()

    class Meta:
        managed = True
        db_table = 'ref_geo_indices'


class RefCptHcpcsCode(models.Model):
    """CPT/HCPCS code master (Phase 1). Separate from RVU/rate data."""
    code = models.CharField(max_length=20, primary_key=True)
    code_type = models.CharField(max_length=8)  # CPT, HCPCS
    description = models.CharField(max_length=255, null=True, blank=True)
    status_indicator = models.CharField(max_length=10, null=True, blank=True)
    effective_year = models.IntegerField()

    class Meta:
        managed = True
        db_table = 'ref_cpt_hcpcs_codes'


class RefMpfsRvu(models.Model):
    """MPFS RVU by code and year (Phase 1). Used for RBRVS when (code, year) exists."""
    id = models.BigAutoField(primary_key=True)
    code = models.CharField(max_length=20, db_index=True)
    year = models.IntegerField(db_index=True)
    work_rvu = models.DecimalField(max_digits=10, decimal_places=4, default=0)
    pe_rvu = models.DecimalField(max_digits=10, decimal_places=4, default=0)
    mp_rvu = models.DecimalField(max_digits=10, decimal_places=4, default=0)
    total_rvu = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    status_indicator = models.CharField(max_length=10, null=True, blank=True)

    class Meta:
        managed = True
        db_table = 'ref_mpfs_rvu'
        constraints = [
            models.UniqueConstraint(fields=['code', 'year'], name='ref_mpfs_rvu_code_year_uniq'),
        ]


class RefDrg(models.Model):
    """DRG reference (Phase 2). Engine uses relative_weight; fallback to RefProcedureCode.work_rvu."""
    drg_code = models.CharField(max_length=20, primary_key=True)
    description = models.CharField(max_length=255, null=True, blank=True)
    relative_weight = models.DecimalField(max_digits=12, decimal_places=6, default=0)
    geometric_mean_los = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    arithmetic_mean_los = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    mdc = models.CharField(max_length=10, null=True, blank=True)
    year = models.IntegerField(db_index=True)

    class Meta:
        managed = True
        db_table = 'ref_drg'
        indexes = [
            models.Index(fields=['drg_code', 'year'], name='ref_drg_code_year_idx'),
        ]


class RefApc(models.Model):
    """APC reference (Phase 2). Optional use in loader/strategies when APC methodology is introduced."""
    apc_code = models.CharField(max_length=20, primary_key=True)
    description = models.CharField(max_length=255, null=True, blank=True)
    relative_weight = models.DecimalField(max_digits=12, decimal_places=6, default=0)
    status_indicator = models.CharField(max_length=10, null=True, blank=True)
    payment_rate = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    year = models.IntegerField(db_index=True)

    class Meta:
        managed = True
        db_table = 'ref_apc'
        indexes = [
            models.Index(fields=['apc_code', 'year'], name='ref_apc_code_year_idx'),
        ]


# ==========================================
# Phase 3: ICD-10 and ASP reference tables
# ==========================================

class RefIcd10Cm(models.Model):
    """ICD-10-CM diagnosis codes (Phase 3)."""
    diagnosis_code = models.CharField(max_length=20, primary_key=True)
    description = models.CharField(max_length=500, null=True, blank=True)
    billable_flag = models.BooleanField(default=True)
    effective_year = models.IntegerField(db_index=True)

    class Meta:
        managed = True
        db_table = 'ref_icd10_cm'


class RefIcd10Pcs(models.Model):
    """ICD-10-PCS procedure codes (Phase 3, optional)."""
    procedure_code = models.CharField(max_length=20, primary_key=True)
    description = models.CharField(max_length=500, null=True, blank=True)
    section = models.CharField(max_length=20, null=True, blank=True)
    body_system = models.CharField(max_length=50, null=True, blank=True)
    year = models.IntegerField(db_index=True)

    class Meta:
        managed = True
        db_table = 'ref_icd10_pcs'


class RefAspPricing(models.Model):
    """ASP pricing for drug J-codes (Phase 3). Unique on (hcpcs_code, quarter)."""
    id = models.BigAutoField(primary_key=True)
    hcpcs_code = models.CharField(max_length=20, db_index=True)
    quarter = models.CharField(max_length=10, db_index=True)
    asp = models.DecimalField(max_digits=12, decimal_places=4)
    payment_limit = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    class Meta:
        managed = True
        db_table = 'ref_asp_pricing'
        constraints = [
            models.UniqueConstraint(fields=['hcpcs_code', 'quarter'], name='asp_hcpcs_quarter_uniq'),
        ]


# ==========================================
# Phase 4: Revenue codes and specialties
# ==========================================

class RefRevenueCode(models.Model):
    """Revenue codes (Phase 4)."""
    revenue_code = models.CharField(max_length=20, primary_key=True)
    description = models.CharField(max_length=255, null=True, blank=True)
    category = models.CharField(max_length=50, null=True, blank=True)

    class Meta:
        managed = True
        db_table = 'ref_revenue_codes'


class RefSpecialty(models.Model):
    """Provider specialties (Phase 4)."""
    specialty_code = models.CharField(max_length=20, primary_key=True)
    description = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        managed = True
        db_table = 'ref_specialties'


# ==========================================
# 2. ORGANIZATION & NETWORK LAYER
# ==========================================

class ProviderOrganization(models.Model):
    # Physical Table: provider_organizations
    organization_id = models.CharField(max_length=50, primary_key=True)
    name = models.CharField(max_length=255)
    tax_id = models.CharField(max_length=20, null=True, blank=True)
    npi = models.CharField(max_length=15, null=True, blank=True)
    address_json = models.JSONField(null=True, blank=True)
    # Phase 4: link to specialty for carve-outs
    primary_specialty = models.ForeignKey(
        RefSpecialty,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column='primary_specialty_id',
        related_name='organizations',
    )
    org_type = models.CharField(
        max_length=30,
        null=True,
        blank=True,
        choices=[
            ('SOLO', 'Solo Practice'),
            ('GROUP', 'Group Practice'),
            ('IDS', 'Integrated Delivery System'),
            ('HEALTH_SYSTEM', 'Health System'),
            ('FACILITY', 'Facility/Hospital'),
        ],
    )
    parent_org = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column='parent_org_id',
        related_name='child_orgs',
    )
    npi_type = models.CharField(
        max_length=1,
        null=True,
        blank=True,
        choices=[('1', 'Type 1 - Individual'), ('2', 'Type 2 - Organization')],
    )

    class Meta:
        managed = True
        db_table = 'provider_organizations'


class PayerNetwork(models.Model):
    # Physical Table: payer_networks
    network_id = models.CharField(max_length=50, primary_key=True)
    network_name = models.CharField(max_length=100, null=True, blank=True)
    payer_org = models.ForeignKey(ProviderOrganization, on_delete=models.CASCADE, db_column='payer_org_id')
    line_of_business = models.CharField(max_length=50, null=True, blank=True)
    network_type = models.CharField(max_length=20, null=True, blank=True)

    class Meta:
        managed = True
        db_table = 'payer_networks'

class ProviderContract(models.Model):
    # Physical Table: contracts
    class ContractOriginType(models.TextChoices):
        DIRECT = 'DIRECT', 'Direct'
        LEASED = 'LEASED', 'Leased Network'
        DELEGATED = 'DELEGATED', 'Delegated'

    contract_id = models.AutoField(primary_key=True)
    legacy_contract_number = models.CharField(max_length=100, null=True, blank=True)
    contract_name = models.CharField(max_length=150, null=True, blank=True)
    # Phase 2B: line_of_business (nullable; network also has line_of_business)
    line_of_business = models.CharField(max_length=50, null=True, blank=True)

    # Relationships
    provider_org = models.ForeignKey(ProviderOrganization, on_delete=models.CASCADE, db_column='provider_org_id')
    network = models.ForeignKey(PayerNetwork, on_delete=models.CASCADE, db_column='network_id')
    payer_org = models.ForeignKey(
        'products.PayerOrganization',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column='payer_org_id',
        related_name='contracts',
    )

    status = models.CharField(max_length=10, default='DRAFT')
    effective_start_date = models.DateField()
    effective_end_date = models.DateField(null=True, blank=True)
    contract_origin_type = models.CharField(
        max_length=20,
        choices=ContractOriginType.choices,
        default=ContractOriginType.DIRECT,
    )
    resolution_priority = models.SmallIntegerField(
        default=10,
        help_text="Lower value wins on tie. DIRECT=10, DELEGATED=15, LEASED=20.",
    )

    class Meta:
        managed = True
        db_table = 'contracts'


class ContractScope(models.Model):
    """Phase 8: Hierarchical contract scoping for deterministic resolution (line_of_business, specialty, site, geo)."""
    id = models.BigAutoField(primary_key=True)
    contract = models.ForeignKey(
        ProviderContract,
        on_delete=models.CASCADE,
        db_column='contract_id',
        related_name='scopes',
    )
    line_of_business = models.CharField(max_length=50, null=True, blank=True)
    specialty_code = models.ForeignKey(
        RefSpecialty,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        to_field='specialty_code',
        db_column='specialty_code',
        related_name='contract_scopes',
    )
    site_of_service = models.CharField(max_length=20, null=True, blank=True)
    geo = models.ForeignKey(
        RefGeoIndex,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        db_column='geo_id',
        related_name='contract_scopes',
    )
    priority = models.IntegerField(default=100)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = True
        db_table = 'contract_scopes'
        ordering = ['contract', 'priority']
        indexes = [
            models.Index(fields=['contract', 'priority'], name='scope_contract_priority_idx'),
            models.Index(
                fields=['line_of_business', 'specialty_code', 'site_of_service', 'geo'],
                name='scope_dims_idx',
            ),
        ]

    def clean(self):
        from django.core.exceptions import ValidationError
        qs = ContractScope.objects.filter(
            contract=self.contract,
            line_of_business=self.line_of_business or None,
            specialty_code=self.specialty_code,
            site_of_service=self.site_of_service or None,
            geo=self.geo,
            priority=self.priority,
        )
        if self.pk:
            qs = qs.exclude(pk=self.pk)
        if qs.exists():
            raise ValidationError(
                'A scope with the same contract, dimensions, and priority already exists. '
                'Use a different priority to establish precedence.'
            )


class ContractProductScope(models.Model):
    """
    Links a ProviderContract to the LOB and/or Product it applies to.
    If no record exists for a contract, the contract is LOB-agnostic (matches all).
    """
    id = models.BigAutoField(primary_key=True)
    contract = models.ForeignKey(
        ProviderContract,
        on_delete=models.CASCADE,
        related_name='product_scopes',
    )
    lob_code = models.CharField(max_length=30, null=True, blank=True)
    product = models.ForeignKey(
        'products.Product',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    effective_date = models.DateField(null=True, blank=True)
    termination_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'contract_product_scopes'


class ContractScopeUnified(models.Model):
    """
    Gap E (§16): Unified contract scope — superset of ContractScope + ContractProductScope.
    Resolver reads this table only; legacy tables remain for deprecation period.
    """

    class MigrationSource(models.TextChoices):
        CONTRACT_SCOPE = 'CONTRACT_SCOPE', 'ContractScope'
        PRODUCT_SCOPE = 'PRODUCT_SCOPE', 'ContractProductScope'

    id = models.BigAutoField(primary_key=True)
    contract = models.ForeignKey(
        ProviderContract,
        on_delete=models.CASCADE,
        db_column='contract_id',
        related_name='unified_scopes',
    )
    lob_code = models.CharField(max_length=50, null=True, blank=True)
    product = models.ForeignKey(
        'products.Product',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    specialty_code = models.ForeignKey(
        RefSpecialty,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        to_field='specialty_code',
        db_column='specialty_code',
        related_name='unified_contract_scopes',
    )
    site_of_service = models.CharField(max_length=20, null=True, blank=True)
    geo = models.ForeignKey(
        RefGeoIndex,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        db_column='geo_id',
        related_name='unified_contract_scopes',
    )
    effective_date = models.DateField(null=True, blank=True)
    termination_date = models.DateField(null=True, blank=True)
    priority = models.IntegerField(default=100)
    migration_source = models.CharField(
        max_length=20,
        choices=MigrationSource.choices,
        db_index=True,
    )
    migration_source_id = models.BigIntegerField(db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        managed = True
        db_table = 'contract_scopes_unified'
        ordering = ['contract', 'priority', 'id']
        constraints = [
            models.UniqueConstraint(
                fields=['migration_source', 'migration_source_id'],
                name='contract_scope_unified_source_uniq',
            ),
        ]
        indexes = [
            models.Index(fields=['contract', 'lob_code'], name='cs_unified_cntr_lob_idx'),
            models.Index(fields=['contract', 'product'], name='cs_unified_cntr_prod_idx'),
        ]

    def __str__(self) -> str:
        return f'UnifiedScope(contract={self.contract_id} lob={self.lob_code!r} product={self.product_id})'


class ContractProviderParticipation(models.Model):
    """Phase 8: Which providers (org or NPI) participate in a contract and when."""
    id = models.BigAutoField(primary_key=True)
    contract = models.ForeignKey(
        ProviderContract,
        on_delete=models.CASCADE,
        db_column='contract_id',
        related_name='participations',
    )
    organization = models.ForeignKey(
        ProviderOrganization,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        db_column='organization_id',
        related_name='contract_participations',
    )
    npi = models.CharField(max_length=15, null=True, blank=True)
    effective_start_date = models.DateField()
    effective_end_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = True
        db_table = 'contract_provider_participations'
        ordering = ['contract', '-effective_start_date']
        constraints = [
            models.CheckConstraint(
                condition=Q(organization__isnull=False) | Q(npi__isnull=False),
                name='participation_org_or_npi',
            ),
        ]
        indexes = [
            models.Index(
                fields=['contract', 'organization', 'npi'],
                name='part_cntr_org_npi_idx',
            ),
            models.Index(
                fields=['effective_start_date', 'effective_end_date'],
                name='participation_dates_idx',
            ),
        ]

    def clean(self):
        from django.core.exceptions import ValidationError
        if not self.organization_id and not (self.npi and str(self.npi).strip()):
            raise ValidationError('At least one of organization or npi must be set.')


class ContractDocument(models.Model):
    """Provenance layer: links a contract to its source paper, exhibits, and amendments."""

    class DocType(models.TextChoices):
        AGREEMENT = 'AGREEMENT', 'Agreement'
        RATE_EXHIBIT = 'RATE_EXHIBIT', 'Rate Exhibit'
        AMENDMENT = 'AMENDMENT', 'Amendment'
        OTHER = 'OTHER', 'Other'

    id = models.BigAutoField(primary_key=True)
    contract = models.ForeignKey(
        ProviderContract,
        on_delete=models.CASCADE,
        db_column='contract_id',
        related_name='documents',
    )
    doc_type = models.CharField(max_length=20, choices=DocType.choices)
    reference = models.CharField(
        max_length=500,
        help_text='Path, URL, or external identifier for the source document.',
    )
    title = models.CharField(max_length=255)
    notes = models.TextField(null=True, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'contract_documents'
        ordering = ['contract', '-uploaded_at']

    def __str__(self) -> str:
        return f"{self.title} ({self.doc_type})"


class ContractCoveredEntity(models.Model):
    """Layer 3: which orgs, facilities, and providers a contract covers."""

    class EntityType(models.TextChoices):
        ORG = 'ORG', 'Organization'
        FACILITY = 'FACILITY', 'Facility'
        PROVIDER = 'PROVIDER', 'Provider'

    id = models.BigAutoField(primary_key=True)
    contract = models.ForeignKey(
        ProviderContract,
        on_delete=models.CASCADE,
        db_column='contract_id',
        related_name='covered_entities',
    )
    entity_type = models.CharField(max_length=20, choices=EntityType.choices)
    organization = models.ForeignKey(
        ProviderOrganization,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        db_column='organization_id',
        related_name='contract_covered_entities',
    )
    facility = models.ForeignKey(
        'providers.Facility',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        db_column='facility_id',
        related_name='contract_covered_entities',
    )
    provider = models.ForeignKey(
        'providers.Provider',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        db_column='provider_id',
        related_name='contract_covered_entities',
    )
    is_primary = models.BooleanField(default=False)
    effective_start_date = models.DateField(null=True, blank=True)
    effective_end_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'contract_covered_entities'
        indexes = [
            models.Index(fields=['contract', 'entity_type'], name='cce_contract_entity_idx'),
            models.Index(fields=['organization'], name='cce_organization_idx'),
            models.Index(fields=['facility'], name='cce_facility_idx'),
            models.Index(fields=['provider'], name='cce_provider_idx'),
        ]
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(entity_type='ORG', organization__isnull=False, facility__isnull=True, provider__isnull=True)
                    | Q(entity_type='FACILITY', facility__isnull=False, organization__isnull=True, provider__isnull=True)
                    | Q(entity_type='PROVIDER', provider__isnull=False, organization__isnull=True, facility__isnull=True)
                ),
                name='cce_entity_type_matches_fk',
            ),
        ]

    def __str__(self) -> str:
        if self.entity_type == self.EntityType.ORG:
            return f"ORG {self.organization_id} on contract {self.contract_id}"
        if self.entity_type == self.EntityType.FACILITY:
            return f"FACILITY {self.facility_id} on contract {self.contract_id}"
        return f"PROVIDER {self.provider_id} on contract {self.contract_id}"


class ContractVersion(models.Model):
    """Phase 7: Contract versioning. Term periods, amendments, version-scoped methodologies and rules."""

    class VersionStatus(models.TextChoices):
        DRAFT = 'DRAFT', 'Draft'
        ACTIVE = 'ACTIVE', 'Active'
        SUPERSEDED = 'SUPERSEDED', 'Superseded'
        ARCHIVED = 'ARCHIVED', 'Archived'

    version_id = models.BigAutoField(primary_key=True)
    contract = models.ForeignKey(
        ProviderContract,
        on_delete=models.CASCADE,
        db_column='contract_id',
        related_name='versions',
    )
    version_number = models.IntegerField()
    effective_start_date = models.DateField()
    effective_end_date = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=VersionStatus.choices,
        default=VersionStatus.DRAFT,
        db_index=True,
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class PricingEngineMode(models.TextChoices):
        LEGACY = 'LEGACY', 'Legacy'
        STAGED = 'STAGED', 'Staged'

    pricing_engine_mode = models.CharField(
        max_length=10,
        choices=PricingEngineMode.choices,
        default=PricingEngineMode.LEGACY,
        db_column='pricing_engine_mode',
    )
    # Phase E: when True, claim-level DRG runs (one payment = FacilityBaseRate × DRG weight); default False.
    claim_level_drg_enabled = models.BooleanField(default=False, db_column='claim_level_drg_enabled')
    # Step 14a: optional product/plan key for tiered resolution; null = wildcard for this version row
    product_id = models.CharField(max_length=100, null=True, blank=True, db_column='product_id')
    # Step 14a: higher value wins when sorting rule candidates (with FEATURE_TIERED_RESOLUTION)
    tier_priority = models.IntegerField(default=0, db_column='tier_priority')

    class Meta:
        managed = True
        db_table = 'contract_versions'
        ordering = ['contract', '-version_number']
        indexes = [
            models.Index(
                fields=['product_id', 'tier_priority'],
                name='contract_version_prod_tier_idx',
            ),
        ]


class ContractArrangement(models.Model):
    """Layer 5: named, typed pricing arrangement grouping rules under a contract."""

    class ArrangementType(models.TextChoices):
        FEE_SCHEDULE = 'FEE_SCHEDULE', 'Fee Schedule'
        DRG_CASE_RATE = 'DRG_CASE_RATE', 'DRG Case Rate'
        PER_DIEM = 'PER_DIEM', 'Per Diem'
        APC = 'APC', 'APC'
        ANESTHESIA = 'ANESTHESIA', 'Anesthesia'
        DRUG_ASP = 'DRUG_ASP', 'Drug ASP'
        CAPITATION = 'CAPITATION', 'Capitation'
        BUNDLED = 'BUNDLED', 'Bundled'
        VALUE_BASED = 'VALUE_BASED', 'Value Based'

    id = models.BigAutoField(primary_key=True)
    contract = models.ForeignKey(
        ProviderContract,
        on_delete=models.CASCADE,
        db_column='contract_id',
        related_name='arrangements',
    )
    name = models.CharField(max_length=150)
    arrangement_type = models.CharField(max_length=30, choices=ArrangementType.choices)
    claim_type = models.CharField(max_length=20, null=True, blank=True)
    effective_start_date = models.DateField(null=True, blank=True)
    effective_end_date = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=ContractVersion.VersionStatus.choices,
        default=ContractVersion.VersionStatus.DRAFT,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'contract_arrangements'
        ordering = ['contract', 'name']

    def __str__(self) -> str:
        return f"{self.name} ({self.arrangement_type})"


class ContractAmendment(models.Model):
    """Layer 6/2: first-class, dated contract amendments."""

    id = models.BigAutoField(primary_key=True)
    contract = models.ForeignKey(
        ProviderContract,
        on_delete=models.CASCADE,
        db_column='contract_id',
        related_name='amendments',
    )
    amendment_number = models.CharField(max_length=50)
    effective_date = models.DateField()
    description = models.TextField()
    what_changed = models.JSONField(null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=ContractVersion.VersionStatus.choices,
        default=ContractVersion.VersionStatus.DRAFT,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'contract_amendments'
        ordering = ['contract', '-effective_date']

    def __str__(self) -> str:
        return f"Amendment {self.amendment_number} ({self.effective_date})"


class ContractTerm(models.Model):
    """
    Phase B: Reference table for contract/version-scoped multipliers.
    When a PricingRule has contract_term_id set, the loader uses this term's multiplier
    (subject to effective dates) instead of rule.multiplier. rule.multiplier is not removed.
    """
    id = models.BigAutoField(primary_key=True)
    contract = models.ForeignKey(
        ProviderContract,
        on_delete=models.CASCADE,
        db_column='contract_id',
        related_name='contract_terms',
    )
    version = models.ForeignKey(
        ContractVersion,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        db_column='version_id',
        related_name='contract_terms',
    )
    name = models.CharField(max_length=150)
    multiplier = models.DecimalField(max_digits=10, decimal_places=4, default=1.0000)
    effective_start_date = models.DateField()
    effective_end_date = models.DateField(null=True, blank=True)

    class Meta:
        managed = True
        db_table = 'contract_terms'
        indexes = [
            models.Index(
                fields=['contract', 'version', 'effective_start_date', 'effective_end_date'],
                name='contract_terms_cv_dates_idx',
            ),
        ]

    def __str__(self):
        return f"{self.name} (contract={self.contract_id})"


class TierMultiplier(models.Model):
    """
    Step 14a: Contract/version-scoped conversion multiplier by product and/or network tier,
    effective-dated. Used as default conversion factor in the loader when FEATURE_TIERED_RESOLUTION is on.
    """
    id = models.BigAutoField(primary_key=True)
    contract = models.ForeignKey(
        ProviderContract,
        on_delete=models.CASCADE,
        db_column='contract_id',
        related_name='tier_multipliers',
    )
    version = models.ForeignKey(
        ContractVersion,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        db_column='version_id',
        related_name='tier_multipliers',
    )
    product_id = models.CharField(max_length=100, null=True, blank=True, db_column='product_id')
    network_id = models.CharField(max_length=100, null=True, blank=True, db_column='network_id')
    multiplier = models.DecimalField(max_digits=10, decimal_places=4)
    effective_start_date = models.DateField()
    effective_end_date = models.DateField(null=True, blank=True)

    class Meta:
        managed = True
        db_table = 'tier_multipliers'
        indexes = [
            models.Index(
                fields=['contract', 'product_id', 'network_id', 'effective_start_date', 'effective_end_date'],
                name='tier_mult_ctr_prod_net_dt_idx',
            ),
        ]

    def __str__(self):
        return f"TierMultiplier(contract={self.contract_id}, pk={self.pk})"


class CodeGroup(models.Model):
    """
    Phase C: Group of procedure codes for resolver condition 'code_group'.
    When a rule condition has attribute_name='code_group' and attribute_value=code_group_id,
    the resolver checks request.procedure_code IN code group members (effective for service_date).
    """
    id = models.BigAutoField(primary_key=True)
    contract = models.ForeignKey(
        ProviderContract,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        db_column='contract_id',
        related_name='code_groups',
    )
    version = models.ForeignKey(
        ContractVersion,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        db_column='version_id',
        related_name='code_groups',
    )
    code_group_code = models.CharField(max_length=50)
    name = models.CharField(max_length=150)
    effective_start_date = models.DateField()
    effective_end_date = models.DateField(null=True, blank=True)

    class Meta:
        managed = True
        db_table = 'code_groups'
        indexes = [
            models.Index(
                fields=['contract', 'version', 'effective_start_date', 'effective_end_date'],
                name='code_groups_cv_dates_idx',
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.code_group_code})"


class CodeGroupMember(models.Model):
    """Phase C: One procedure code in a CodeGroup. Effective-dated for service_date filtering."""
    id = models.BigAutoField(primary_key=True)
    code_group = models.ForeignKey(
        CodeGroup,
        on_delete=models.CASCADE,
        db_column='code_group_id',
        related_name='members',
    )
    code_id = models.CharField(max_length=20)
    effective_start_date = models.DateField()
    effective_end_date = models.DateField(null=True, blank=True)

    class Meta:
        managed = True
        db_table = 'code_group_members'
        indexes = [
            models.Index(fields=['code_group', 'code_id'], name='code_group_members_cg_code_idx'),
        ]

    def __str__(self):
        return f"{self.code_group_id}:{self.code_id}"


# --- Phase D: Reference-only pricing (multiplier/flat_rate from reference tables) ---

class PerDiemRate(models.Model):
    """
    Phase D: Contract/version-scoped per diem rate. When a rule has per_diem_rate_id set,
    the loader uses this rate (effective-dated) instead of rule.flat_rate for PER_DIEM.
    """
    id = models.BigAutoField(primary_key=True)
    contract = models.ForeignKey(
        ProviderContract,
        on_delete=models.CASCADE,
        db_column='contract_id',
        related_name='per_diem_rates',
    )
    version = models.ForeignKey(
        ContractVersion,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        db_column='version_id',
        related_name='per_diem_rates',
    )
    rate_amount = models.DecimalField(max_digits=12, decimal_places=2)
    effective_start_date = models.DateField()
    effective_end_date = models.DateField(null=True, blank=True)

    class Meta:
        managed = True
        db_table = 'per_diem_rates'
        indexes = [
            models.Index(
                fields=['contract', 'version', 'effective_start_date', 'effective_end_date'],
                name='per_diem_rates_cv_dates_idx',
            ),
        ]

    def __str__(self):
        return f"PerDiemRate(contract={self.contract_id}, rate={self.rate_amount})"


class ModifierAdjustment(models.Model):
    """
    Phase D: Contract/version override for modifier percentage. When present for a modifier_code
    and effective for service_date, loader uses this value instead of RefModifier.percentage_adjustment.
    """
    ADJUSTMENT_TYPE_PERCENT = 'PERCENT'
    ADJUSTMENT_TYPE_CHOICES = [(ADJUSTMENT_TYPE_PERCENT, 'Percentage')]

    id = models.BigAutoField(primary_key=True)
    contract = models.ForeignKey(
        ProviderContract,
        on_delete=models.CASCADE,
        db_column='contract_id',
        related_name='modifier_adjustments',
    )
    version = models.ForeignKey(
        ContractVersion,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        db_column='version_id',
        related_name='modifier_adjustments',
    )
    modifier_code = models.CharField(max_length=5)
    adjustment_type = models.CharField(max_length=20, choices=ADJUSTMENT_TYPE_CHOICES, default=ADJUSTMENT_TYPE_PERCENT)
    adjustment_value = models.DecimalField(max_digits=8, decimal_places=2)  # e.g. 100.00 = 100%
    effective_start_date = models.DateField()
    effective_end_date = models.DateField(null=True, blank=True)

    class Meta:
        managed = True
        db_table = 'modifier_adjustments'
        indexes = [
            models.Index(
                fields=['contract', 'version', 'modifier_code', 'effective_start_date', 'effective_end_date'],
                name='mod_adj_cv_code_dates_idx',
            ),
        ]

    def __str__(self):
        return f"ModifierAdjustment({self.modifier_code}={self.adjustment_value}%)"


class ContractFlatRateOverride(models.Model):
    """
    Phase D: Contract/version flat rate for rules that have no fee schedule. When a rule has
    flat_rate_override_id set, the loader uses this rate (effective-dated) instead of rule.flat_rate.
    procedure_code null = applies to all procedures for that rule context.
    """
    id = models.BigAutoField(primary_key=True)
    contract = models.ForeignKey(
        ProviderContract,
        on_delete=models.CASCADE,
        db_column='contract_id',
        related_name='flat_rate_overrides',
    )
    version = models.ForeignKey(
        ContractVersion,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        db_column='version_id',
        related_name='flat_rate_overrides',
    )
    procedure_code = models.CharField(max_length=20, null=True, blank=True)
    rate_amount = models.DecimalField(max_digits=12, decimal_places=2)
    effective_start_date = models.DateField()
    effective_end_date = models.DateField(null=True, blank=True)

    class Meta:
        managed = True
        db_table = 'contract_flat_rate_overrides'
        indexes = [
            models.Index(
                fields=['contract', 'version', 'effective_start_date', 'effective_end_date'],
                name='flat_rate_ov_cv_dates_idx',
            ),
        ]

    def __str__(self):
        return f"FlatRateOverride(contract={self.contract_id}, rate={self.rate_amount})"


class ContractVersionAudit(models.Model):
    """
    Step 12b: Immutable audit record written on every ContractVersion lifecycle transition.
    Never modified after creation; delete is disallowed at the service level.
    """

    class ChangeType(models.TextChoices):
        ACTIVATED = 'ACTIVATED', 'Activated'
        SUPERSEDED = 'SUPERSEDED', 'Superseded'
        ARCHIVED = 'ARCHIVED', 'Archived'
        DRAFTED = 'DRAFTED', 'Drafted'

    version = models.ForeignKey(
        'ContractVersion',
        on_delete=models.CASCADE,
        db_column='version_id',
        related_name='audit_records',
    )
    changed_by = models.ForeignKey(
        'auth.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column='changed_by_id',
    )
    change_type = models.CharField(max_length=20, choices=ChangeType.choices)
    previous_status = models.CharField(max_length=20)
    new_status = models.CharField(max_length=20)
    timestamp = models.DateTimeField(auto_now_add=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        managed = True
        db_table = 'contract_version_audit'
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['version', '-timestamp'], name='ver_audit_version_ts_idx'),
        ]

    def __str__(self):
        return f"Version {self.version_id} {self.change_type} at {self.timestamp}"


class ContractMethodology(models.Model):
    """Phase 2B: Contract-level methodology. Rules inherit when methodology_code is blank. Phase 7: optional version scoping."""
    id = models.BigAutoField(primary_key=True)
    contract = models.ForeignKey(
        ProviderContract,
        on_delete=models.CASCADE,
        db_column='contract_id',
        related_name='methodologies',
    )
    version = models.ForeignKey(
        ContractVersion,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        db_column='version_id',
        related_name='methodologies',
    )
    methodology_type = models.CharField(max_length=50)  # RBRVS, DRG, PCT_BILLED, PER_DIEM, CASE_RATE
    # Phase D deprecated: use contract_term_id for multiplier; keep for backward compatibility until backfill
    base_percentage = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    conversion_factor = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    # Phase D: when set, loader uses ContractTerm.multiplier (effective-dated) for conversion_factor
    contract_term = models.ForeignKey(
        ContractTerm,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column='contract_term_id',
        related_name='contract_methodologies',
    )
    fee_schedule = models.ForeignKey(
        'FeeSchedule',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column='fee_schedule_id',
        related_name='contract_methodologies',
    )
    effective_date = models.DateField()
    termination_date = models.DateField(null=True, blank=True)
    priority = models.IntegerField(default=0)
    # Phase 2B: claim_type and site_of_service for filtering
    claim_type = models.CharField(max_length=20, null=True, blank=True)  # INPATIENT, OUTPATIENT, PROFESSIONAL
    site_of_service = models.CharField(max_length=50, null=True, blank=True)
    # Step 12c: optional structured applicability conditions (evaluated at runtime; null = always applies)
    conditions = models.JSONField(
        null=True, blank=True,
        help_text='Optional. Null = always apply. Schema: {"operator": "AND"|"OR", "conditions": [{"field": "<name>", "op": "eq"|"neq"|"gt"|"gte"|"lt"|"lte"|"in"|"not_in", "value": <scalar or list>}]}. '
                  'Allowed fields: procedure_code, billed_amount, units, claim_type, modifiers_count. No nested groups.',
    )

    class Meta:
        managed = True
        db_table = 'contract_methodologies'
        # MySQL does not support partial unique indexes; uniqueness is enforced in clean() below.
        constraints = []

    def clean(self):
        from django.core.exceptions import ValidationError
        from core.services.validation_service import ValidationService
        from core.services.condition_validation_service import validate_condition_schema
        errors = ValidationService.check_methodology_collision(self)
        if errors:
            raise ValidationError(errors[0].message)
        validate_condition_schema(self.conditions)


class ContractOutlierRule(models.Model):
    """Phase 6: Outlier/stop-loss with explicit evaluation order (after base and adjustment rules)."""
    THRESHOLD_SCOPE_CHOICES = [
        ("PER_CLAIM", "Per Claim"),
        ("PER_LINE", "Per Line"),
    ]
    id = models.BigAutoField(primary_key=True)
    contract = models.ForeignKey(
        ProviderContract,
        on_delete=models.CASCADE,
        db_column='contract_id',
        related_name='outlier_rules',
    )
    version = models.ForeignKey(
        ContractVersion,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        db_column='version_id',
        related_name='outlier_rules',
    )
    threshold_amount = models.DecimalField(max_digits=12, decimal_places=2)
    threshold_scope = models.CharField(
        max_length=20, choices=THRESHOLD_SCOPE_CHOICES, default="PER_CLAIM"
    )
    reimbursement_percentage = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    cost_to_charge_ratio = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)
    priority = models.IntegerField(default=0)  # Tiers; higher = evaluated first (order_by -priority)
    effective_start_date = models.DateField(default='1900-01-01')
    effective_end_date = models.DateField(null=True, blank=True)

    class Meta:
        managed = True
        db_table = 'contract_outlier_rules'
        ordering = ['contract', '-priority', 'effective_start_date']
        constraints = [
            models.CheckConstraint(
                condition=Q(reimbursement_percentage__isnull=False)
                | Q(cost_to_charge_ratio__isnull=False),
                name="outlier_requires_payment_method",
            )
        ]
        indexes = [
            models.Index(fields=["contract", "-priority"], name="outlier_contract_priority_idx"),
        ]

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.reimbursement_percentage is None and self.cost_to_charge_ratio is None:
            raise ValidationError(
                'At least one of reimbursement_percentage or cost_to_charge_ratio must be set.'
            )


class ContractStopLossRule(models.Model):
    """Phase 7: Stop-loss at claim level (cost-based). Evaluated BEFORE outlier rules. Phase 7: optional version scoping."""
    id = models.BigAutoField(primary_key=True)
    contract = models.ForeignKey(
        ProviderContract,
        on_delete=models.CASCADE,
        db_column='contract_id',
        related_name='stop_loss_rules',
    )
    version = models.ForeignKey(
        ContractVersion,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        db_column='version_id',
        related_name='stop_loss_rules',
    )
    cost_threshold = models.DecimalField(max_digits=12, decimal_places=2)
    reimbursement_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        help_text="Percentage of cost paid above threshold",
    )
    priority = models.IntegerField(default=0)
    effective_start_date = models.DateField()
    effective_end_date = models.DateField(null=True, blank=True)

    class Meta:
        managed = True
        db_table = 'contract_stop_loss_rules'
        ordering = ['contract', '-priority', 'effective_start_date']
        constraints = [
            models.CheckConstraint(
                condition=Q(reimbursement_percentage__gt=0) & Q(reimbursement_percentage__lte=100),
                name='stoploss_reimbursement_pct_range',
            )
        ]
        indexes = [
            models.Index(fields=['contract', '-priority'], name='stoploss_contract_priority_idx'),
        ]


class ContractCarveout(models.Model):
    """
    Step 7: Line-level carve-outs per contract version.
    Execution order: after base methodology (step 4), before rule adjustments (step 6).
    carveout_methodology:
      EXCLUDE    → zero the line allowed amount
      PCT_BILLED → allowed = billed_amount * carveout_percentage / 100
      FIXED_RATE → allowed = carveout_rate (fixed dollar amount)
    """
    carveout_id = models.BigAutoField(primary_key=True)
    version = models.ForeignKey(
        ContractVersion,
        on_delete=models.CASCADE,
        db_column='version_id',
        related_name='carveouts',
    )
    code_type = models.CharField(max_length=20)  # CPT, HCPCS, DRG, APC, REV_CODE
    code_value = models.CharField(max_length=20)
    carveout_methodology = models.CharField(max_length=50)  # EXCLUDE, PCT_BILLED, FIXED_RATE
    carveout_percentage = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True,
        help_text="Percent of billed amount; used when carveout_methodology=PCT_BILLED",
    )
    carveout_rate = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        help_text="Fixed dollar rate; used when carveout_methodology=FIXED_RATE",
    )

    status = models.CharField(
        max_length=20,
        choices=ContractVersion.VersionStatus.choices,
        default=ContractVersion.VersionStatus.DRAFT,
        db_index=True,
    )
    # Step 12c: optional structured applicability conditions
    conditions = models.JSONField(
        null=True, blank=True,
        help_text='Optional. Null = always apply. Schema: {"operator": "AND"|"OR", "conditions": [{"field": "procedure_code"|"billed_amount"|"units"|"claim_type"|"modifiers_count", "op": "eq"|"neq"|"gt"|"gte"|"lt"|"lte"|"in"|"not_in", "value": <scalar or list>}]}. No nested groups.',
    )

    class Meta:
        managed = True
        db_table = 'contract_carveouts'
        ordering = ['version', 'code_type', 'code_value']

    def clean(self):
        from django.core.exceptions import ValidationError
        from core.services.validation_service import ValidationService
        from core.services.condition_validation_service import validate_condition_schema
        errors = ValidationService.check_carveout_duplicate(self)
        if errors:
            raise ValidationError(errors[0].message)
        validate_condition_schema(self.conditions)


class ContractCapFloor(models.Model):
    """
    Step 8: Claim-level or line-level caps and floors (Phase G).
    scope:
      CLAIM        → applied after CROSS_LINE and blending (claim total clamp).
      LINE         → applied per line after ADJUSTMENT/carve-out (LINE_CAP_FLOOR stage).
      DRG / APC    → claim-level, only when a line used that methodology.
    cap_type:
      CAP          → clamp to max value (claim total or line allowed_amount)
      FLOOR        → clamp to min value
      PCT_BILLED_CAP → cap = (total_billed or line_billed) * percentage / 100
    code_value: for CLAIM/DRG/APC optional code restriction; for LINE = procedure_code filter.
    """
    cap_floor_id = models.BigAutoField(primary_key=True)
    version = models.ForeignKey(
        ContractVersion,
        on_delete=models.CASCADE,
        db_column='version_id',
        related_name='cap_floors',
    )
    scope = models.CharField(max_length=20, default='CLAIM')  # CLAIM, DRG, APC
    cap_type = models.CharField(max_length=20)  # CAP, FLOOR, PCT_BILLED_CAP
    value = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True,
        help_text="Absolute dollar cap or floor value",
    )
    percentage = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True,
        help_text="Percentage of billed; used when cap_type=PCT_BILLED_CAP",
    )
    code_value = models.CharField(
        max_length=20, null=True, blank=True,
        help_text="Restrict to this DRG or APC code; null = apply to all codes of the scope type",
    )
    priority = models.IntegerField(default=0)
    effective_start_date = models.DateField()
    effective_end_date = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=ContractVersion.VersionStatus.choices,
        default=ContractVersion.VersionStatus.DRAFT,
        db_index=True,
    )
    # Step 12c: optional structured applicability conditions
    conditions = models.JSONField(
        null=True, blank=True,
        help_text='Optional. Null = always apply. Schema: {"operator": "AND"|"OR", "conditions": [{"field": "procedure_code"|"billed_amount"|"units"|"claim_type"|"modifiers_count", "op": "eq"|"neq"|"gt"|"gte"|"lt"|"lte"|"in"|"not_in", "value": <scalar or list>}]}. No nested groups.',
    )

    class Meta:
        managed = True
        db_table = 'contract_cap_floors'
        ordering = ['-priority', 'effective_start_date']

    def clean(self):
        from core.services.condition_validation_service import validate_condition_schema
        validate_condition_schema(self.conditions)


class ContractBlendingRule(models.Model):
    """
    Step 9: Multi-methodology blending rule per contract version.
    Executed after stop-loss/outlier and before caps/floors (canonical step 9).

    blend_type:
      ADD      → blended = current_total + total_billed * blend_percentage / 100
                 (LINE scope: blended_line = line_allowed + line_billed * blend_percentage / 100)
      OVERRIDE → blended = total_billed * blend_percentage / 100
                 (LINE scope: blended_line = line_billed * blend_percentage / 100)
    scope:
      CLAIM    → applies blending to the claim-level post-outlier total
      LINE     → applies blending per matching line; sum becomes new claim total
    primary_methodology: '' (empty) = applies to all lines; e.g. 'DRG' restricts to DRG lines.
    secondary_methodology: informational label for the secondary pricing basis (e.g. 'PERCENT_BILLED').
    """
    blending_rule_id = models.BigAutoField(primary_key=True)
    version = models.ForeignKey(
        ContractVersion,
        on_delete=models.CASCADE,
        db_column='version_id',
        related_name='blending_rules',
    )
    blend_type = models.CharField(max_length=20)              # ADD, OVERRIDE
    scope = models.CharField(max_length=20, default='CLAIM')  # CLAIM, LINE
    primary_methodology = models.CharField(
        max_length=50, default='',
        help_text="Methodology code this rule targets; empty = apply to all.",
    )
    secondary_methodology = models.CharField(
        max_length=50, default='',
        help_text="Label for the secondary pricing basis (informational).",
    )
    blend_percentage = models.DecimalField(
        max_digits=6, decimal_places=2,
        help_text="Percentage applied to total_billed for ADD/OVERRIDE computation.",
    )
    priority = models.IntegerField(default=0)
    effective_start_date = models.DateField()
    effective_end_date = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=ContractVersion.VersionStatus.choices,
        default=ContractVersion.VersionStatus.DRAFT,
        db_index=True,
    )
    # Step 12c: optional structured applicability conditions
    conditions = models.JSONField(
        null=True, blank=True,
        help_text='Optional. Null = always apply. Schema: {"operator": "AND"|"OR", "conditions": [{"field": "procedure_code"|"billed_amount"|"units"|"claim_type"|"modifiers_count", "op": "eq"|"neq"|"gt"|"gte"|"lt"|"lte"|"in"|"not_in", "value": <scalar or list>}]}. No nested groups.',
    )

    class Meta:
        managed = True
        db_table = 'contract_blending_rules'
        ordering = ['-priority', 'effective_start_date']
        indexes = [
            models.Index(fields=['version', '-priority'], name='blend_version_priority_idx'),
        ]

    def clean(self):
        from django.core.exceptions import ValidationError
        from core.services.validation_service import ValidationService
        from core.services.condition_validation_service import validate_condition_schema
        errors = ValidationService.check_blending_cycle_for_rule(self)
        if errors:
            raise ValidationError(errors[0].message)
        validate_condition_schema(self.conditions)


class ContractBaseRate(models.Model):
    """Phase 7: DRG/APC base rate per contract version."""
    base_rate_id = models.BigAutoField(primary_key=True)
    version = models.ForeignKey(
        ContractVersion,
        on_delete=models.CASCADE,
        db_column='version_id',
        related_name='base_rates',
    )
    rate_type = models.CharField(max_length=20)  # DRG, APC
    base_rate = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        managed = True
        db_table = 'contract_base_rates'
        ordering = ['version', 'rate_type']


# --- Phase E: Claim-level methodology (DRG, case rate) ---

class FacilityBaseRate(models.Model):
    """
    Phase E: Claim-level DRG/APC base rate per contract/version (optional facility).
    When claim_level_drg_enabled, orchestrator uses this × RefDrg.relative_weight for claim payment.
    """
    id = models.BigAutoField(primary_key=True)
    contract = models.ForeignKey(
        ProviderContract,
        on_delete=models.CASCADE,
        db_column='contract_id',
        related_name='facility_base_rates',
    )
    version = models.ForeignKey(
        ContractVersion,
        on_delete=models.CASCADE,
        db_column='version_id',
        related_name='facility_base_rates',
    )
    facility_id = models.IntegerField(null=True, blank=True)  # nullable; null = default for version
    rate_type = models.CharField(max_length=20)  # DRG, APC
    base_rate = models.DecimalField(max_digits=12, decimal_places=2)
    effective_start_date = models.DateField()
    effective_end_date = models.DateField(null=True, blank=True)

    class Meta:
        managed = True
        db_table = 'facility_base_rates'
        indexes = [
            models.Index(
                fields=['contract', 'version', 'facility_id', 'rate_type', 'effective_start_date', 'effective_end_date'],
                name='fbr_cv_fac_type_dates_idx',
            ),
        ]

    def __str__(self):
        return f"FacilityBaseRate(version={self.version_id} rate_type={self.rate_type} base={self.base_rate})"


class CaseRateDefinition(models.Model):
    """Phase E: Claim-level case rate (lump sum per case_rate_code)."""
    id = models.BigAutoField(primary_key=True)
    contract = models.ForeignKey(
        ProviderContract,
        on_delete=models.CASCADE,
        db_column='contract_id',
        related_name='case_rate_definitions',
    )
    version = models.ForeignKey(
        ContractVersion,
        on_delete=models.CASCADE,
        db_column='version_id',
        related_name='case_rate_definitions',
    )
    case_rate_code = models.CharField(max_length=50)
    lump_sum_amount = models.DecimalField(max_digits=12, decimal_places=2)
    effective_start_date = models.DateField()
    effective_end_date = models.DateField(null=True, blank=True)

    class Meta:
        managed = True
        db_table = 'case_rate_definitions'
        indexes = [
            models.Index(
                fields=['contract', 'version', 'effective_start_date', 'effective_end_date'],
                name='case_rate_cv_dates_idx',
            ),
        ]

    def __str__(self):
        return f"CaseRate({self.case_rate_code}={self.lump_sum_amount})"


# --- Phase F: Cross-line MPPR (Multiple Procedure Payment Reduction) ---

class MPPRDefinition(models.Model):
    """
    Phase F: MPPR rule per contract/version. Lines in scope (via MPPRScope) are ranked by rank_by;
    primary_pct applied to first, secondary_pct to second, tertiary_pct to rest.
    """
    RANK_BY_ALLOWED = 'ALLOWED_AMOUNT'
    RANK_BY_RVU = 'RVU'
    RANK_BY_FEE_SCHEDULE = 'FEE_SCHEDULE'
    RANK_BY_CHOICES = [
        (RANK_BY_ALLOWED, 'Allowed amount'),
        (RANK_BY_RVU, 'RVU'),
        (RANK_BY_FEE_SCHEDULE, 'Fee schedule'),
    ]

    id = models.BigAutoField(primary_key=True)
    contract = models.ForeignKey(
        ProviderContract,
        on_delete=models.CASCADE,
        db_column='contract_id',
        related_name='mppr_definitions',
    )
    version = models.ForeignKey(
        ContractVersion,
        on_delete=models.CASCADE,
        db_column='version_id',
        related_name='mppr_definitions',
    )
    name = models.CharField(max_length=150)
    rank_by = models.CharField(max_length=30, choices=RANK_BY_CHOICES, default=RANK_BY_ALLOWED)
    primary_pct = models.DecimalField(max_digits=6, decimal_places=2)    # e.g. 100.00
    secondary_pct = models.DecimalField(max_digits=6, decimal_places=2)  # e.g. 50.00
    tertiary_pct = models.DecimalField(max_digits=6, decimal_places=2)   # e.g. 25.00
    effective_start_date = models.DateField()
    effective_end_date = models.DateField(null=True, blank=True)

    class Meta:
        managed = True
        db_table = 'mppr_definitions'
        indexes = [
            models.Index(
                fields=['contract', 'version', 'effective_start_date', 'effective_end_date'],
                name='mppr_def_cv_dates_idx',
            ),
        ]

    def __str__(self):
        return f"MPPR({self.name})"


class MPPRScope(models.Model):
    """Phase F: Scope for an MPPR definition. Line in scope if procedure in code_group or matches procedure_code."""
    id = models.BigAutoField(primary_key=True)
    mppr_definition = models.ForeignKey(
        MPPRDefinition,
        on_delete=models.CASCADE,
        db_column='mppr_definition_id',
        related_name='scopes',
    )
    code_group = models.ForeignKey(
        CodeGroup,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        db_column='code_group_id',
        related_name='mppr_scopes',
    )
    procedure_code = models.CharField(max_length=20, null=True, blank=True)

    class Meta:
        managed = True
        db_table = 'mppr_scopes'

    def __str__(self):
        return f"MPPRScope(mppr={self.mppr_definition_id} code_group={self.code_group_id} procedure={self.procedure_code})"


# ==========================================
# 3. PRICING RULES (The Engine Logic)
# ==========================================

class FeeSchedule(models.Model):
    # Physical Table: fee_schedules
    fee_schedule_id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=100, null=True, blank=True)
    effective_date = models.DateField(null=True, blank=True)
    version = models.IntegerField(default=1)
    # Phase 1: versioning and source metadata
    effective_year = models.IntegerField(null=True, blank=True)
    effective_start_date = models.DateField(null=True, blank=True)
    effective_end_date = models.DateField(null=True, blank=True)
    schedule_type = models.CharField(max_length=50, null=True, blank=True)  # e.g. PROFESSIONAL, FACILITY
    source = models.CharField(max_length=100, null=True, blank=True)
    # Locality linked to geo for GPCI (ref_geo_indices)
    geo = models.ForeignKey(
        RefGeoIndex,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column='geo_id',
        related_name='fee_schedules',
    )

    class Meta:
        managed = True
        db_table = 'fee_schedules'

class FeeScheduleRate(models.Model):
    # Physical Table: fee_schedule_rates
    rate_id = models.BigAutoField(primary_key=True)
    fee_schedule = models.ForeignKey(FeeSchedule, on_delete=models.CASCADE, db_column='fee_schedule_id')
    code_id = models.CharField(max_length=20)
    rate_amount = models.DecimalField(max_digits=12, decimal_places=2)
    # Phase 1: effective dating and year
    effective_start_date = models.DateField(null=True, blank=True)
    effective_end_date = models.DateField(null=True, blank=True)
    year = models.IntegerField(null=True, blank=True)

    class Meta:
        managed = True
        db_table = 'fee_schedule_rates'
        # Phase 7: indexes for loader lookups
        indexes = [
            models.Index(fields=['fee_schedule', 'code_id'], name='fs_rates_fs_code_idx'),
            models.Index(
                fields=['code_id', 'effective_start_date', 'effective_end_date'],
                name='fs_rates_code_dates_idx',
            ),
        ]


class PricingRule(models.Model):
    class RuleStatus(models.TextChoices):
        DRAFT = 'DRAFT', 'Draft'
        ACTIVE = 'ACTIVE', 'Active'
        RETIRED = 'RETIRED', 'Retired'

    # Physical Table: pricing_rules
    rule_id = models.BigAutoField(primary_key=True)
    contract = models.ForeignKey(ProviderContract, on_delete=models.CASCADE, db_column='contract_id')
    version = models.ForeignKey(
        ContractVersion,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        db_column='version_id',
        related_name='pricing_rules',
    )
    rule_name = models.CharField(max_length=150, null=True, blank=True)
    arrangement = models.ForeignKey(
        ContractArrangement,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column='arrangement_id',
        related_name='pricing_rules',
    )

    # Logic Columns
    rule_type = models.CharField(max_length=10)  # 'BASE', 'ADJUSTMENT'
    # Phase 2B: null/blank = inherit from ContractMethodology; set = override contract methodology
    methodology_code = models.CharField(max_length=50, null=True, blank=True)  # RBRVS, FLAT_RATE, DRG, etc.
    multiplier = models.DecimalField(max_digits=6, decimal_places=4, default=1.0000)
    flat_rate = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    # Phase B: when set, loader uses ContractTerm.multiplier (effective-dated) instead of rule.multiplier
    contract_term = models.ForeignKey(
        ContractTerm,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column='contract_term_id',
        related_name='pricing_rules',
    )
    # Phase D: when set, loader uses PerDiemRate.rate_amount (effective-dated) for PER_DIEM instead of rule.flat_rate
    per_diem_rate = models.ForeignKey(
        PerDiemRate,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column='per_diem_rate_id',
        related_name='pricing_rules',
    )
    # Phase D: when set, loader uses ContractFlatRateOverride.rate_amount (effective-dated) instead of rule.flat_rate
    flat_rate_override = models.ForeignKey(
        ContractFlatRateOverride,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column='flat_rate_override_id',
        related_name='pricing_rules',
    )

    base_fee_schedule = models.ForeignKey(FeeSchedule, on_delete=models.SET_NULL, null=True, db_column='base_fee_schedule_id')
    # Phase 2B: inherit methodology from contract when null/blank; filter by claim_type
    claim_type = models.CharField(max_length=20, null=True, blank=True)  # INPATIENT, OUTPATIENT, PROFESSIONAL
    site_of_service = models.CharField(max_length=50, null=True, blank=True)

    # The Critical "V2" Column
    specificity_score = models.IntegerField(default=0)

    status = models.CharField(
        max_length=20,
        choices=RuleStatus.choices,
        default=RuleStatus.DRAFT,
        db_column='status',
    )
    effective_start_date = models.DateField(default='1900-01-01')
    effective_end_date = models.DateField(null=True, blank=True)

    # Helper Logic (Used by Django, ignored by SQL)
    def calculate_score(self):
        score = 0
        # Check associated conditions (Reverse Relationship)
        if self.pk: 
            for condition in self.conditions.all():
                score += 10
                # Boost score for Specific Overrides
                if condition.attribute_name in ['plan_id', 'group_id', 'provider_id']:
                    score += 50
        self.specificity_score = score
        self.save()

    class Meta:
        managed = True
        db_table = 'pricing_rules'
        # Phase 7: indexes for resolver and bulk simulation
        indexes = [
            models.Index(
                fields=['contract', 'effective_start_date', 'effective_end_date'],
                name='rule_cntr_dates_idx',
            ),
            models.Index(
                fields=['contract', 'claim_type', 'specificity_score'],
                name='rule_claim_spec_idx',
            ),
        ]


class PricingRuleCondition(models.Model):
    """
    Phase 5: Conditions do NOT have independent effective dates.
    They inherit the parent rule's effective_start_date and effective_end_date.
    The resolver applies rule effective dating before condition matching.
    """
    # Physical Table: pricing_rule_conditions
    condition_id = models.BigAutoField(primary_key=True)
    # Note: related_name='conditions' is crucial for the calculate_score method above
    pricing_rule = models.ForeignKey(PricingRule, on_delete=models.CASCADE, db_column='rule_id', related_name='conditions')

    attribute_name = models.CharField(max_length=50)  # e.g. 'code'
    operator = models.CharField(max_length=10, default='EQ')
    attribute_value = models.CharField(max_length=255)

    class Meta:
        managed = True
        db_table = 'pricing_rule_conditions'
        indexes = [
            models.Index(fields=['pricing_rule'], name='cond_rule_id_idx'),
        ]


class RuleHistory(models.Model):
    """Audit log for PricingRule status changes (Phase 3 Segment 4)."""
    pricing_rule = models.ForeignKey(
        PricingRule, on_delete=models.CASCADE, db_column='rule_id', related_name='history'
    )
    change_date = models.DateTimeField(auto_now_add=True)
    previous_status = models.CharField(max_length=20, blank=True)
    new_status = models.CharField(max_length=20)
    change_reason = models.TextField(blank=True)

    class Meta:
        managed = True
        db_table = 'rule_history'
        ordering = ['-change_date']


# ==========================================
# Phase 5B: Claim Header and Claim Line (persistent claim for bulk simulation)
# ==========================================

class ClaimHeader(models.Model):
    """Persistent claim header; DRG and claim_type at header for resolver/outlier. Phase 8: contract nullable for resolution."""
    claim_id = models.BigAutoField(primary_key=True)
    contract = models.ForeignKey(
        ProviderContract,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        db_column='contract_id',
        related_name='claims',
    )
    provider_org = models.ForeignKey(
        ProviderOrganization,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column='provider_org_id',
        related_name='claim_headers',
    )
    npi = models.CharField(max_length=15, null=True, blank=True)
    site_of_service = models.CharField(max_length=20, null=True, blank=True)
    geo = models.ForeignKey(
        RefGeoIndex,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column='geo_id',
        related_name='claim_headers',
    )
    member_id = models.CharField(max_length=64, null=True, blank=True)
    service_date = models.DateField()
    claim_type = models.CharField(max_length=20, null=True, blank=True)  # INPATIENT, OUTPATIENT, PROFESSIONAL
    drg_code = models.CharField(max_length=20, null=True, blank=True)
    line_of_business = models.CharField(max_length=50, null=True, blank=True)
    pricing_date = models.DateField(null=True, blank=True)
    rendering_provider = models.ForeignKey(
        'providers.Provider',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column='rendering_provider_id',
        related_name='claim_headers',
    )
    facility = models.ForeignKey(
        'providers.Facility',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column='facility_id',
        related_name='claim_headers',
    )
    member_fk = models.ForeignKey(
        'members.Member',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column='member_fk_id',
        related_name='claim_headers',
    )
    billing_npi = models.CharField(max_length=15, null=True, blank=True)

    class Meta:
        managed = True
        db_table = 'claim_headers'
        ordering = ['-service_date']


class ClaimLine(models.Model):
    """Single line on a claim; child of ClaimHeader."""
    line_id = models.BigAutoField(primary_key=True)
    claim = models.ForeignKey(
        ClaimHeader,
        on_delete=models.CASCADE,
        db_column='claim_id',
        related_name='lines',
    )
    procedure_code = models.CharField(max_length=20)
    modifiers = models.JSONField(default=list, blank=True)  # list of modifier codes
    billed_amount = models.DecimalField(max_digits=12, decimal_places=2)
    cost_amount = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True, default=0,
        help_text="Cost for this line; used for stop-loss (Phase 7).",
    )
    units = models.IntegerField(default=1)
    sequence = models.IntegerField(default=0)

    class Meta:
        managed = True
        db_table = 'claim_lines'
        ordering = ['claim', 'sequence', 'line_id']


class ClaimResolutionLog(models.Model):
    """Append-only audit of contract resolution for a claim (Phase R1 schema; writes in R4)."""

    class ResolutionPath(models.TextChoices):
        CALLER_SUPPLIED = 'CALLER_SUPPLIED', 'Caller Supplied'
        LEGACY_PARTICIPATION = 'LEGACY_PARTICIPATION', 'Legacy Participation'
        CONTEXT_RESOLVER = 'CONTEXT_RESOLVER', 'Context Resolver'

    claim_header = models.ForeignKey(
        'ClaimHeader',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='resolution_logs',
    )
    trace_id = models.UUIDField(db_index=True, null=True, blank=True)
    resolved_contract = models.ForeignKey(
        'ProviderContract',
        on_delete=models.PROTECT,
        related_name='resolution_logs',
    )
    resolved_version = models.ForeignKey(
        'ContractVersion',
        on_delete=models.PROTECT,
        related_name='resolution_logs',
    )
    resolution_path = models.CharField(max_length=30, choices=ResolutionPath.choices)
    service_date = models.DateField()
    resolver_inputs = models.JSONField(default=dict)
    is_repricing = models.BooleanField(default=False)
    resolved_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'claim_resolution_logs'
        indexes = [
            models.Index(fields=['resolved_contract', 'service_date']),
            models.Index(fields=['claim_header']),
        ]


class ContractResolutionException(models.Model):
    """Analyst review queue for failed or ambiguous contract resolution (Phase D3)."""

    id = models.BigAutoField(primary_key=True)
    trace_id = models.UUIDField(db_index=True, null=True, blank=True)
    status = models.CharField(max_length=30)
    reason = models.TextField()
    candidates = models.JSONField(default=list)
    gathered_inputs = models.JSONField(default=dict)
    service_date = models.DateField(null=True, blank=True)
    is_reviewed = models.BooleanField(default=False)
    review_notes = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'contract_resolution_exceptions'
        indexes = [
            models.Index(fields=['status', 'is_reviewed'], name='cre_status_reviewed_idx'),
            models.Index(fields=['trace_id'], name='cre_trace_id_idx'),
        ]

    def __str__(self) -> str:
        return f'{self.status} @ {self.created_at:%Y-%m-%d}'


# ==========================================
# Step 10: Validation Result (audit table)
# ==========================================

class ValidationResult(models.Model):
    """
    Step 10: Persistent audit record of a contract validation run.
    Populated by ValidationService.save_validation_results().
    Never read or written during claim pricing execution.
    """
    SEVERITY_ERROR = "ERROR"
    SEVERITY_WARNING = "WARNING"

    contract = models.ForeignKey(
        ProviderContract,
        on_delete=models.CASCADE,
        db_column='contract_id',
        related_name='validation_results',
    )
    validated_at = models.DateTimeField(auto_now_add=True)
    conflict_type = models.CharField(max_length=50)
    severity = models.CharField(max_length=10)  # ERROR, WARNING
    message = models.TextField()
    affected_objects = models.JSONField(default=list)
    suggested_action = models.TextField(blank=True)
    resolved = models.BooleanField(default=False)

    class Meta:
        managed = True
        db_table = 'contract_validation_results'
        ordering = ['-validated_at', 'severity', 'conflict_type']
        indexes = [
            models.Index(fields=['contract', 'resolved'], name='val_contract_resolved_idx'),
        ]

    def __str__(self):
        return f"[{self.severity}] {self.conflict_type} – contract {self.contract_id}"


# ==========================================
# Gap A (§16): Published schedule rate linkage
# ==========================================

class PublishedFeeSchedule(models.Model):
    """Named external fee schedule (MPFS, MSDRG, APC, or CUSTOM). Source for ContractRateBasis."""

    class BasisType(models.TextChoices):
        MPFS = 'MPFS', 'MPFS'
        MSDRG = 'MSDRG', 'MSDRG'
        APC = 'APC', 'APC'
        CUSTOM = 'CUSTOM', 'Custom'

    id = models.BigAutoField(primary_key=True)
    name = models.CharField(max_length=150)
    basis_type = models.CharField(max_length=20, choices=BasisType.choices)
    year = models.IntegerField()
    source = models.CharField(max_length=100, blank=True, default='')
    effective_start_date = models.DateField()
    effective_end_date = models.DateField(null=True, blank=True)
    # Optional national base / conversion factor for MPFS CF, DRG base, or APC CF when resolving.
    base_rate = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)

    class Meta:
        managed = True
        db_table = 'published_fee_schedules'
        ordering = ['-year', 'name']
        indexes = [
            models.Index(fields=['basis_type', 'year'], name='pub_sched_type_year_idx'),
        ]

    def __str__(self):
        return f'{self.name} ({self.basis_type} {self.year})'


class PublishedFeeScheduleRate(models.Model):
    """Code-level rate for CUSTOM published schedules only."""

    id = models.BigAutoField(primary_key=True)
    schedule = models.ForeignKey(
        PublishedFeeSchedule,
        on_delete=models.CASCADE,
        db_column='schedule_id',
        related_name='rates',
    )
    code = models.CharField(max_length=20)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    unit = models.CharField(max_length=20, null=True, blank=True)

    class Meta:
        managed = True
        db_table = 'published_fee_schedule_rates'
        indexes = [
            models.Index(fields=['schedule', 'code'], name='pub_sched_rate_sched_code_idx'),
        ]

    def __str__(self):
        return f'{self.schedule_id}:{self.code}={self.amount}'


class ContractRateBasis(models.Model):
    """Authoring source: rule rate = percentage × published schedule lookup (materialized to concrete fields)."""

    id = models.BigAutoField(primary_key=True)
    pricing_rule = models.OneToOneField(
        PricingRule,
        on_delete=models.CASCADE,
        db_column='rule_id',
        related_name='rate_basis',
    )
    schedule = models.ForeignKey(
        PublishedFeeSchedule,
        on_delete=models.PROTECT,
        db_column='schedule_id',
        related_name='contract_bases',
    )
    percentage = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        help_text='Percent of schedule amount, e.g. 120.00 = 120%',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        managed = True
        db_table = 'contract_rate_bases'
        verbose_name_plural = 'contract rate bases'

    def __str__(self):
        return f'Rule {self.pricing_rule_id}: {self.percentage}% of {self.schedule}'

    def readable_basis(self) -> str:
        """Plain-language basis for summary panel, e.g. '120% of MPFS 2025'."""
        pct = self.percentage
        if pct == pct.to_integral():
            pct_str = str(int(pct))
        else:
            pct_str = format(pct, 'f').rstrip('0').rstrip('.')
        return f'{pct_str}% of {self.schedule.name}'


class ContractEscalator(models.Model):
    """Contract-level annual escalator applied during rate materialization (Gap B §16)."""

    id = models.BigAutoField(primary_key=True)
    contract = models.ForeignKey(
        ProviderContract,
        on_delete=models.CASCADE,
        db_column='contract_id',
        related_name='escalators',
    )
    version = models.ForeignKey(
        'ContractVersion',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        db_column='version_id',
        related_name='escalators',
        help_text='Null = applies to all rate-basis rules on the contract.',
    )
    annual_percentage = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        help_text='Annual compounding increase, e.g. 3.00 = 3%/yr',
    )
    cap_percentage = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        help_text='Optional max cumulative increase from base_year, e.g. 10.00 = 10% total cap',
    )
    base_year = models.IntegerField(help_text='Anchor year for the base rate before escalation')
    effective_start_date = models.DateField()
    effective_end_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        managed = True
        db_table = 'contract_escalators'
        ordering = ['contract', '-effective_start_date']
        indexes = [
            models.Index(fields=['contract', 'effective_start_date'], name='contract_esc_cntr_start_idx'),
        ]

    def __str__(self):
        scope = f'v{self.version_id}' if self.version_id else 'contract-wide'
        return f'{self.contract_id} {scope}: +{self.annual_percentage}%/yr from {self.base_year}'

    def readable_suffix(self) -> str:
        """Summary suffix, e.g. '+3%/yr'."""
        pct = self.annual_percentage
        if pct == pct.to_integral():
            pct_str = str(int(pct))
        else:
            pct_str = format(pct, 'f').rstrip('0').rstrip('.')
        return f'+{pct_str}%/yr'

