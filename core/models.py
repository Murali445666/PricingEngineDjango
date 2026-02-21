from django.db import models

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

    class Meta:
        managed = True
        db_table = 'provider_organizations'

class PayerNetwork(models.Model):
    # Physical Table: payer_networks
    network_id = models.CharField(max_length=50, primary_key=True)
    network_name = models.CharField(max_length=100, null=True, blank=True)
    payer_org = models.ForeignKey(ProviderOrganization, on_delete=models.CASCADE, db_column='payer_org_id')
    line_of_business = models.CharField(max_length=50, null=True, blank=True)

    class Meta:
        managed = True
        db_table = 'payer_networks'

class ProviderContract(models.Model):
    # Physical Table: contracts
    contract_id = models.AutoField(primary_key=True)
    legacy_contract_number = models.CharField(max_length=100, null=True, blank=True)
    contract_name = models.CharField(max_length=150, null=True, blank=True)
    
    # Relationships
    provider_org = models.ForeignKey(ProviderOrganization, on_delete=models.CASCADE, db_column='provider_org_id')
    network = models.ForeignKey(PayerNetwork, on_delete=models.CASCADE, db_column='network_id')
    
    status = models.CharField(max_length=10, default='DRAFT')
    effective_start_date = models.DateField()
    effective_end_date = models.DateField(null=True, blank=True)

    class Meta:
        managed = True
        db_table = 'contracts'

# ==========================================
# 3. PRICING RULES (The Engine Logic)
# ==========================================

class FeeSchedule(models.Model):
    # Physical Table: fee_schedules
    fee_schedule_id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=100, null=True, blank=True)
    effective_date = models.DateField(null=True, blank=True)
    version = models.IntegerField(default=1)

    class Meta:
        managed = True
        db_table = 'fee_schedules'

class FeeScheduleRate(models.Model):
    # Physical Table: fee_schedule_rates
    rate_id = models.BigAutoField(primary_key=True)
    fee_schedule = models.ForeignKey(FeeSchedule, on_delete=models.CASCADE, db_column='fee_schedule_id')
    code_id = models.CharField(max_length=20) 
    rate_amount = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        managed = True
        db_table = 'fee_schedule_rates'

class PricingRule(models.Model):
    class RuleStatus(models.TextChoices):
        DRAFT = 'DRAFT', 'Draft'
        ACTIVE = 'ACTIVE', 'Active'
        RETIRED = 'RETIRED', 'Retired'

    # Physical Table: pricing_rules
    rule_id = models.BigAutoField(primary_key=True)
    contract = models.ForeignKey(ProviderContract, on_delete=models.CASCADE, db_column='contract_id')
    rule_name = models.CharField(max_length=150, null=True, blank=True)
    
    # Logic Columns
    rule_type = models.CharField(max_length=10) # 'BASE', 'ADJUSTMENT'
    methodology_code = models.CharField(max_length=50) # 'RBRVS', 'FLAT_RATE'
    multiplier = models.DecimalField(max_digits=6, decimal_places=4, default=1.0000)
    flat_rate = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    
    base_fee_schedule = models.ForeignKey(FeeSchedule, on_delete=models.SET_NULL, null=True, db_column='base_fee_schedule_id')
    
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

class PricingRuleCondition(models.Model):
    # Physical Table: pricing_rule_conditions
    condition_id = models.BigAutoField(primary_key=True)
    # Note: related_name='conditions' is crucial for the calculate_score method above
    pricing_rule = models.ForeignKey(PricingRule, on_delete=models.CASCADE, db_column='rule_id', related_name='conditions')
    
    attribute_name = models.CharField(max_length=50) # e.g. 'code'
    operator = models.CharField(max_length=10, default='EQ')
    attribute_value = models.CharField(max_length=255)

    class Meta:
        managed = True
        db_table = 'pricing_rule_conditions'


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

