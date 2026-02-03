from django.db import models
from django.contrib.auth.models import User
import uuid

# -----------------------------
# Base / Shared Mixins
# -----------------------------

class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

class EffectiveDatedModel(models.Model):
    effective_start_date = models.DateField()
    effective_end_date = models.DateField(null=True, blank=True)

    class Meta:
        abstract = True

class VersionedModel(models.Model):
    version = models.IntegerField(default=1)
    is_active = models.BooleanField(default=False)
    previous_version = models.ForeignKey(
        'self',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='next_versions'
    )

    class Meta:
        abstract = True

class AuditableModel(models.Model):
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='+'
    )
    approved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='+'
    )
    approved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        abstract = True

# -----------------------------
# Provider & Contract Entities
# -----------------------------

class ProviderOrganization(TimeStampedModel):
    organization_id = models.UUIDField(default=uuid.uuid4, unique=True)
    name = models.CharField(max_length=255)
    tax_id = models.CharField(max_length=15)
    network_code = models.CharField(max_length=50)

    def __str__(self):
        return self.name

class Provider(TimeStampedModel):
    provider_id = models.UUIDField(default=uuid.uuid4, unique=True)
    npi = models.CharField(max_length=10)
    organization = models.ForeignKey(
        ProviderOrganization,
        on_delete=models.CASCADE,
        related_name='providers'
    )
    specialty_code = models.CharField(max_length=50)

    def __str__(self):
        return self.npi

class ProviderContract(TimeStampedModel, EffectiveDatedModel):
    contract_id = models.UUIDField(default=uuid.uuid4, unique=True)
    provider_org = models.ForeignKey(
        ProviderOrganization,
        on_delete=models.CASCADE,
        related_name='contracts'
    )
    contract_name = models.CharField(max_length=255)
    product_line = models.CharField(max_length=50)
    status = models.CharField(
        max_length=30,
        choices=[
            ('DRAFT', 'Draft'),
            ('ACTIVE', 'Active'),
            ('TERMINATED', 'Terminated')
        ]
    )

    def __str__(self):
        return self.contract_name

# -----------------------------
# Code Systems
# -----------------------------

class CodeSet(TimeStampedModel):
    code_set_name = models.CharField(max_length=50)
    code_system_uri = models.CharField(max_length=255)

    def __str__(self):
        return self.code_set_name

class Code(TimeStampedModel):
    code_set = models.ForeignKey(
        CodeSet,
        on_delete=models.CASCADE,
        related_name='codes'
    )
    code = models.CharField(max_length=20)
    description = models.TextField()

    def __str__(self):
        return self.code

# -----------------------------
# Fee Schedules
# -----------------------------

class FeeSchedule(TimeStampedModel, VersionedModel, EffectiveDatedModel, AuditableModel):
    fee_schedule_id = models.UUIDField(default=uuid.uuid4, unique=True)
    name = models.CharField(max_length=255)
    source = models.CharField(max_length=100)

    def __str__(self):
        return f"{self.name} v{self.version}"

class FeeScheduleRate(TimeStampedModel):
    fee_schedule = models.ForeignKey(
        FeeSchedule,
        on_delete=models.CASCADE,
        related_name='rates'
    )
    code = models.ForeignKey(
        Code,
        on_delete=models.CASCADE
    )
    rate_amount = models.DecimalField(max_digits=12, decimal_places=4)

    class Meta:
        unique_together = ('fee_schedule', 'code')

# -----------------------------
# Pricing Methodologies & Rules
# -----------------------------

class PricingMethodology(models.Model):
    methodology_code = models.CharField(max_length=50)
    description = models.TextField()

    def __str__(self):
        return self.methodology_code

class PricingRule(TimeStampedModel, VersionedModel, EffectiveDatedModel, AuditableModel):
    pricing_rule_id = models.UUIDField(default=uuid.uuid4, unique=True)
    contract = models.ForeignKey(
        ProviderContract,
        on_delete=models.CASCADE,
        related_name='pricing_rules'
    )
    methodology = models.ForeignKey(
        PricingMethodology,
        on_delete=models.PROTECT
    )
    
    rule_type = models.CharField(
        max_length=20,
        choices=[
            ('BASE', 'Base Rate (Standard)'),
            ('ADD_ON', 'Add-on (Cumulative)'),
            ('ADJUSTMENT', 'Adjustment (Multiplier)'), # <--- NEW
            ('CAP', 'Cap / Limit (Restrictive)'),
            ('STOP_LOSS', 'Stop Loss (Outlier)')
        ],
        default='BASE',
        help_text="BASE=Exclusive. ADD_ON=Sum. ADJUSTMENT=Multiply. STOP_LOSS=Outlier."
    )
    # NEW FIELD for Stop Loss
    threshold_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, help_text="Trigger for Stop Loss")
    
    # --- NEW FIELD: AUTOMATIC SCORING ---
    specificity_score = models.IntegerField(default=0, editable=False)
    # ------------------------------------

    base_fee_schedule = models.ForeignKey(
        FeeSchedule,
        on_delete=models.PROTECT,
        null=True,
        blank=True
    )
    multiplier = models.DecimalField(max_digits=6, decimal_places=4, null=True, blank=True)
    flat_rate = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    
    # We removed 'rule_priority'
    
    status = models.CharField(
        max_length=30,
        choices=[('DRAFT', 'Draft'), ('ACTIVE', 'Active'), ('RETIRED', 'Retired')]
    )

    def calculate_score(self):
        """
        The Algorithm: Sums points based on attached conditions.
        Must be called AFTER conditions are saved.
        """
        score = 0
        for cond in self.conditions.all():
            attr = cond.attribute_name
            op = cond.operator
            
            if attr == 'code':
                if op == 'EQ':
                    score += 1000  # Exact Code (Highest)
                else:
                    score += 100   # Range/Group (Medium)
            elif attr == 'modifier':
                score += 500       # Modifier (High)
            elif attr == 'rev_code':
                score += 10        # Revenue Code (Low)
            elif attr == 'provider_id':
                score += 5         # Network Context (Lowest)
        
        self.specificity_score = score
        self.save()

    def __str__(self):
        return f"Rule {self.pricing_rule_id} (Score: {self.specificity_score})"

# (PricingRuleCondition stays exactly the same)
class PricingRuleCondition(TimeStampedModel):
    pricing_rule = models.ForeignKey(
        PricingRule,
        on_delete=models.CASCADE,
        related_name='conditions'
    )
    attribute_name = models.CharField(
        max_length=50,
        choices=[
            ('code', 'Procedure Code (CPT/HCPCS/DRG)'),
            ('rev_code', 'Revenue Code'),
            ('modifier', 'Modifier'),
            ('network_status', 'Network Status (INN/OON)'),
            ('EQ', 'Equals'), ('IN', 'In'), ('GT', 'Greater Than'), ('LT', 'Less Than')]
    )
    attribute_value = models.CharField(max_length=255)

    def __str__(self):
        return f"{self.attribute_name} {self.operator} {self.attribute_value}"

class PricingRuleCondition(TimeStampedModel):
    pricing_rule = models.ForeignKey(
        PricingRule,
        on_delete=models.CASCADE,
        related_name='conditions'
    )
    attribute_name = models.CharField(max_length=100)
    operator = models.CharField(
        max_length=20,
        choices=[('EQ', 'Equals'), ('IN', 'In'), ('GT', 'Greater Than'), ('LT', 'Less Than')]
    )
    attribute_value = models.CharField(max_length=255)

    def __str__(self):
        return f"{self.attribute_name} {self.operator} {self.attribute_value}"