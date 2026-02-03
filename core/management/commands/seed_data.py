from django.core.management.base import BaseCommand
from core.models import ProviderOrganization, ProviderContract, PricingMethodology, CodeSet, Code, FeeSchedule, FeeScheduleRate, PricingRule, PricingRuleCondition
from datetime import date
from decimal import Decimal

class Command(BaseCommand):
    help = 'Seeds the database with Enterprise Pricing Data'

    def handle(self, *args, **kwargs):
        self.stdout.write("--- STARTING ENTERPRISE SEED ---")
        
        # 0. CLEANUP (Wipe old rules to prevent collisions)
        self.stdout.write("🧹 Wiping old rules...")
        PricingRuleCondition.objects.all().delete()
        PricingRule.objects.all().delete()
        ProviderContract.objects.all().delete()
        # (We keep Fee Schedules and Codes as they are reference data)

        # 1. PRICING METHODOLOGIES (The Strategies)
        methods = [
            ('RBRVS', 'Resource-Based Relative Value Scale'),
            ('DRG', 'Diagnosis Related Group (Inpatient)'),
            ('PER_DIEM', 'Daily Rate (Psych/Rehab)'),
            ('PERCENT_BILLED', 'Percentage of Billed Charges'),
            ('FLAT_RATE', 'Fixed Flat Rate Case Rate')
        ]
        
        for code, desc in methods:
            PricingMethodology.objects.get_or_create(methodology_code=code, defaults={'description': desc})
        self.stdout.write("✅ Methodologies Created")

        # 2. CODE SETS (The Language of Claims)
        cpt_set, _ = CodeSet.objects.get_or_create(code_set_name='CPT', code_system_uri='http://www.ama-assn.org/go/cpt')
        drg_set, _ = CodeSet.objects.get_or_create(code_set_name='MS-DRG', code_system_uri='https://www.cms.gov/icd10m/drg')
        rev_set, _ = CodeSet.objects.get_or_create(code_set_name='REV_CODE', code_system_uri='https://www.cms.gov/revenue-codes')

        # 3. STANDARD CODES
        codes_data = [
            (cpt_set, '99213', 'Office/outpatient visit, established'),
            (cpt_set, '99214', 'Office/outpatient visit, established, mod complexity'),
            (cpt_set, '90837', 'Psychotherapy, 60 min'), 
            (cpt_set, '27447', 'Total Knee Arthroplasty'), 
            (drg_set, '470', 'Major Joint Replacement or Reattachment of Lower Extremity w/o MCC'),
            (rev_set, '0124', 'Psychiatric - General Classification'),
            (rev_set, '0278', 'Medical/Surgical Supplies: Implants') 
        ]
        
        for c_set, code, desc in codes_data:
            Code.objects.get_or_create(code_set=c_set, code=code, defaults={'description': desc})
        self.stdout.write("✅ Standard Codes Loaded")

        # 4. FEE SCHEDULE (Use Case 2)
        fs, _ = FeeSchedule.objects.get_or_create(
            name='Medicare Physician Fee Schedule CY2026',
            defaults={
                'source': 'CMS',
                'effective_start_date': date(2026, 1, 1),
                'version': 1
            }
        )
        
        # Link Rates
        code_99213 = Code.objects.get(code='99213')
        FeeScheduleRate.objects.get_or_create(fee_schedule=fs, code=code_99213, defaults={'rate_amount': Decimal('85.00')})
        
        code_27447 = Code.objects.get(code='27447')
        FeeScheduleRate.objects.get_or_create(fee_schedule=fs, code=code_27447, defaults={'rate_amount': Decimal('1250.00')}) 
        self.stdout.write("✅ Fee Schedule 'Medicare 2026' Created")

        # 5. PROVIDER CONTRACT (Use Case 1)
        org, _ = ProviderOrganization.objects.get_or_create(
            name='Allegheny Health Network',
            defaults={'tax_id': '25-0000000', 'network_code': 'HIGHMARK_COMMERCIAL'}
        )

        contract, _ = ProviderContract.objects.get_or_create(
            contract_name='AHN Commercial Master 2026',
            provider_org=org,
            defaults={
                'product_line': 'Commercial',
                'status': 'ACTIVE',
                'effective_start_date': date(2026, 1, 1)
            }
        )
        self.stdout.write(f"✅ Contract Created: {contract}")

        # --- PREPARE METHODOLOGIES ---
        rbrvs_method = PricingMethodology.objects.get(methodology_code='RBRVS')
        flat_method = PricingMethodology.objects.get(methodology_code='FLAT_RATE')
        per_diem_method = PricingMethodology.objects.get(methodology_code='PER_DIEM')

        # 6. PRICING RULES (Auto-Scored)
        
        # --- A. KNEE SURGERY (Specific) ---
        rule_knee = PricingRule.objects.create(
            contract=contract,
            rule_type='BASE',
            methodology=rbrvs_method,
            base_fee_schedule=fs,
            multiplier=Decimal('1.50'),
            status='ACTIVE',
            effective_start_date=date(2026, 1, 1),
            version=1
        )
        # Condition: Exact Code 27447 (+1000 Points)
        PricingRuleCondition.objects.create(
            pricing_rule=rule_knee,
            attribute_name='code',
            operator='EQ',
            attribute_value='27447'
        )
        rule_knee.calculate_score() 
        self.stdout.write(f"✅ Created Knee Rule (Score: {rule_knee.specificity_score})")

        # --- B. OFFICE VISIT (Group/Range) ---
        rule_office = PricingRule.objects.create(
            contract=contract,
            rule_type='BASE',
            methodology=rbrvs_method,
            base_fee_schedule=fs,
            multiplier=Decimal('1.10'),
            status='ACTIVE',
            effective_start_date=date(2026, 1, 1),
            version=1
        )
        # Condition: Range > 99000 (+100 Points)
        PricingRuleCondition.objects.create(
            pricing_rule=rule_office,
            attribute_name='code',
            operator='GT',
            attribute_value='99000'
        )
        rule_office.calculate_score()
        self.stdout.write(f"✅ Created Office Rule (Score: {rule_office.specificity_score})")

        # --- C. IMPLANTS (Category) ---
        rule_implant = PricingRule.objects.create(
            contract=contract,
            rule_type='ADD_ON',
            methodology=flat_method,
            flat_rate=Decimal('500.00'),
            status='ACTIVE',
            effective_start_date=date(2026, 1, 1),
            version=1
        )
        # Condition: Rev Code 0278 (+10 Points)
        PricingRuleCondition.objects.create(
            pricing_rule=rule_implant,
            attribute_name='rev_code',
            operator='EQ',
            attribute_value='0278'
        )
        rule_implant.calculate_score()
        self.stdout.write(f"✅ Created Implant Rule (Score: {rule_implant.specificity_score})")
        
        # --- D. PSYCH (Rev Code) ---
        rule_psych = PricingRule.objects.create(
            contract=contract,
            rule_type='BASE',
            methodology=per_diem_method,
            flat_rate=Decimal('1250.00'),
            status='ACTIVE',
            effective_start_date=date(2026, 1, 1),
            version=1
        )
        PricingRuleCondition.objects.create(
            pricing_rule=rule_psych,
            attribute_name='rev_code',
            operator='EQ',
            attribute_value='0124'
        )
        rule_psych.calculate_score()
        self.stdout.write(f"✅ Created Psych Rule (Score: {rule_psych.specificity_score})")

        self.stdout.write("--- SEED COMPLETE ---")

        # --- E. MODIFIER 50 (Bilateral Adjustment) ---
        # Rule: If Modifier '50' is present, multiply price by 1.50
        rule_bilateral = PricingRule.objects.create(
            contract=contract,
            rule_type='ADJUSTMENT',
            methodology=rbrvs_method, # Methodology doesn't strictly matter for Adjustment, but field is required
            multiplier=Decimal('1.50'),
            status='ACTIVE',
            effective_start_date=date(2026, 1, 1),
            version=1
        )
        PricingRuleCondition.objects.create(
            pricing_rule=rule_bilateral,
            attribute_name='modifier',
            operator='EQ',
            attribute_value='50'
        )
        rule_bilateral.calculate_score()
        self.stdout.write(f"✅ Created Bilateral Rule (Score: {rule_bilateral.specificity_score})")

        # --- F. STOP LOSS (High Cost Outlier) ---
        # Rule: If Billed > $10,000, pay 50% of the excess
        rule_stoploss = PricingRule.objects.create(
            contract=contract,
            rule_type='STOP_LOSS',
            methodology=flat_method,
            threshold_amount=Decimal('10000.00'),
            multiplier=Decimal('0.50'), # 50% of excess
            status='ACTIVE',
            effective_start_date=date(2026, 1, 1),
            version=1
        )
        # Apply to specific Rev Code (e.g., Implants) or Global
        # Let's apply it globally to Implants (0278)
        PricingRuleCondition.objects.create(
            pricing_rule=rule_stoploss,
            attribute_name='rev_code',
            operator='EQ',
            attribute_value='0278'
        )
        rule_stoploss.calculate_score()
        self.stdout.write(f"✅ Created Stop Loss Rule (Score: {rule_stoploss.specificity_score})")

        # --- G. INPATIENT DRG (Hospital Logic) ---
        # 1. Define the Weight in the Fee Schedule
        # Code 470 (Knee Replacement) has a relative weight of 2.05
        drg_method = PricingMethodology.objects.get(methodology_code='DRG')
        code_470 = Code.objects.get(code='470')
        
        # Note: We are using 'rate_amount' to store the Weight (2.05)
        FeeScheduleRate.objects.get_or_create(
            fee_schedule=fs, 
            code=code_470, 
            defaults={'rate_amount': Decimal('2.05')} 
        )

        # 2. Create the Pricing Rule
        # "All DRG Claims get paid: Base Rate ($10,000) * DRG Weight"
        rule_drg = PricingRule.objects.create(
            contract=contract,
            rule_type='BASE',
            methodology=drg_method,
            base_fee_schedule=fs,      # <--- Look up weights here
            flat_rate=Decimal('10000.00'), # <--- The Hospital Base Rate
            status='ACTIVE',
            effective_start_date=date(2026, 1, 1),
            version=1
        )
        
        # Condition: Trigger for any code in the DRG range (e.g., 001-999)
        # For simplicity, we will just target our specific test code '470'
        PricingRuleCondition.objects.create(
            pricing_rule=rule_drg,
            attribute_name='code',
            operator='EQ',
            attribute_value='470'
        )
        rule_drg.calculate_score()
        self.stdout.write(f"✅ Created DRG Hospital Rule (Score: {rule_drg.specificity_score})")