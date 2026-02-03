from django.core.management.base import BaseCommand
from core.models import ProviderOrganization, ProviderContract, PricingMethodology, CodeSet, Code, FeeSchedule, FeeScheduleRate, PricingRule, PricingRuleCondition
from datetime import date
from decimal import Decimal

class Command(BaseCommand):
    help = 'Seeds the database with Extensive Enterprise Data (35 Test Scenarios)'

    def handle(self, *args, **kwargs):
        self.stdout.write("--- STARTING EXTENSIVE SEED ---")
        
        # 0. CLEANUP
        self.stdout.write("🧹 Wiping old data...")
        PricingRuleCondition.objects.all().delete()
        PricingRule.objects.all().delete()
        FeeScheduleRate.objects.all().delete()
        ProviderContract.objects.all().delete()
        
        # 1. SETUP CORE REFERENCES
        cpt_set, _ = CodeSet.objects.get_or_create(code_set_name='CPT')
        drg_set, _ = CodeSet.objects.get_or_create(code_set_name='MS-DRG')
        rev_set, _ = CodeSet.objects.get_or_create(code_set_name='REV_CODE')

        fs, _ = FeeSchedule.objects.get_or_create(
            name='Master Fee Schedule 2026',
            defaults={'effective_start_date': date(2026, 1, 1), 'version': 1}
        )

        # 2. DEFINE DATA SETS
        rbrvs_data = [
            ('99213', 'Office Visit Low', '85.00'),
            ('99214', 'Office Visit Mod', '110.00'),
            ('73030', 'X-Ray Shoulder', '40.00'),
            ('10060', 'Drainage of Abscess', '150.00'),
            ('93000', 'EKG Routine', '20.00')
        ]
        flat_data = [
            ('97110', 'Therapy Exercises'),
            ('97112', 'Neuromuscular Re-ed'),
            ('97140', 'Manual Therapy'),
            ('97530', 'Therapeutic Activities'),
            ('98960', 'Self-Mgmt Education')
        ]
        drg_data = [
            ('470', 'Knee Replacement', '2.05'),
            ('194', 'Simple Pneumonia', '0.85'),
            ('291', 'Heart Failure', '1.25'),
            ('392', 'Digestive Disorders', '0.95'),
            ('871', 'Septicemia', '1.80')
        ]
        per_diem_data = [
            ('0124', 'Psych General'),
            ('0114', 'Room & Board Private'),
            ('0120', 'Semi-Private 2 Bed'),
            ('0130', 'Semi-Private 3 Bed'),
            ('0140', 'Private Deluxe')
        ]
        percent_data = [
            ('99999', 'Unlisted Procedure'),
            ('T1015', 'Clinic Visit All-Inclusive'),
            ('A0999', 'Unlisted Ambulance'),
            ('J3490', 'Unlisted Drug'),
            ('E1399', 'DME Misc')
        ]

        # 3. LOAD CODES & FEES
        self.stdout.write("📥 Loading Codes and Rates...")
        for code, desc, rate in rbrvs_data:
            c, _ = Code.objects.get_or_create(code_set=cpt_set, code=code, defaults={'description': desc})
            FeeScheduleRate.objects.create(fee_schedule=fs, code=c, rate_amount=Decimal(rate))

        for code, desc in flat_data:
            Code.objects.get_or_create(code_set=cpt_set, code=code, defaults={'description': desc})

        for code, desc, weight in drg_data:
            c, _ = Code.objects.get_or_create(code_set=drg_set, code=code, defaults={'description': desc})
            FeeScheduleRate.objects.create(fee_schedule=fs, code=c, rate_amount=Decimal(weight))

        for code, desc in per_diem_data:
            Code.objects.get_or_create(code_set=rev_set, code=code, defaults={'description': desc})
        for code, desc in percent_data:
            Code.objects.get_or_create(code_set=cpt_set, code=code, defaults={'description': desc})

        # 4. CREATE CONTRACT
        org, _ = ProviderOrganization.objects.get_or_create(
            name='Allegheny Health Network',
            defaults={'tax_id': '25-0000000', 'network_code': 'HIGHMARK_COMMERCIAL'}
        )
        contract, _ = ProviderContract.objects.get_or_create(
            contract_name='AHN Enterprise Master 2026',
            provider_org=org,
            defaults={'status': 'ACTIVE', 'effective_start_date': date(2026, 1, 1)}
        )

        # 5. CREATE RULES
        
        # --- RULE 1: RBRVS BASE ---
        rbrvs_method = PricingMethodology.objects.get(methodology_code='RBRVS')
        for code, _, _ in rbrvs_data:
            rule = PricingRule.objects.create(
                contract=contract, rule_type='BASE', methodology=rbrvs_method,
                base_fee_schedule=fs, multiplier=Decimal('1.50'),
                status='ACTIVE', effective_start_date=date(2026, 1, 1)
            )
            # Condition 1: Specific Code
            PricingRuleCondition.objects.create(pricing_rule=rule, attribute_name='code', operator='EQ', attribute_value=code)
            
            # Condition 2: MUST BE IN-NETWORK (This prevents it from overriding OON claims)
            PricingRuleCondition.objects.create(pricing_rule=rule, attribute_name='network_status', operator='EQ', attribute_value='INN')
            
            rule.calculate_score()

        # --- RULE 2: FLAT RATE THERAPY ---
        flat_method = PricingMethodology.objects.get(methodology_code='FLAT_RATE')
        for code, _ in flat_data:
            rule = PricingRule.objects.create(
                contract=contract, rule_type='BASE', methodology=flat_method,
                flat_rate=Decimal('50.00'), status='ACTIVE', effective_start_date=date(2026, 1, 1)
            )
            PricingRuleCondition.objects.create(pricing_rule=rule, attribute_name='code', operator='EQ', attribute_value=code)
            rule.calculate_score()

        # --- RULE 3: DRG HOSPITAL ---
        drg_method = PricingMethodology.objects.get(methodology_code='DRG')
        for code, _, _ in drg_data:
            rule = PricingRule.objects.create(
                contract=contract, rule_type='BASE', methodology=drg_method,
                base_fee_schedule=fs, flat_rate=Decimal('10000.00'),
                status='ACTIVE', effective_start_date=date(2026, 1, 1)
            )
            PricingRuleCondition.objects.create(pricing_rule=rule, attribute_name='code', operator='EQ', attribute_value=code)
            rule.calculate_score()

        # --- RULE 4: PER DIEM PSYCH ---
        pd_method = PricingMethodology.objects.get(methodology_code='PER_DIEM')
        for code, _ in per_diem_data:
            rule = PricingRule.objects.create(
                contract=contract, rule_type='BASE', methodology=pd_method,
                flat_rate=Decimal('1250.00'), status='ACTIVE', effective_start_date=date(2026, 1, 1)
            )
            PricingRuleCondition.objects.create(pricing_rule=rule, attribute_name='rev_code', operator='EQ', attribute_value=code)
            rule.calculate_score()

        # --- RULE 5: PERCENT BILLED ---
        pct_method = PricingMethodology.objects.get(methodology_code='PERCENT_BILLED')
        for code, _ in percent_data:
            rule = PricingRule.objects.create(
                contract=contract, rule_type='BASE', methodology=pct_method,
                multiplier=Decimal('0.45'), status='ACTIVE', effective_start_date=date(2026, 1, 1)
            )
            PricingRuleCondition.objects.create(pricing_rule=rule, attribute_name='code', operator='EQ', attribute_value=code)
            rule.calculate_score()

        # --- RULE 6: MODIFIERS ---
        adj_rules = [('50', '1.50'), ('80', '0.20'), ('51', '0.50')]
        for mod, mult in adj_rules:
            rule = PricingRule.objects.create(
                contract=contract, rule_type='ADJUSTMENT', methodology=rbrvs_method,
                multiplier=Decimal(mult), status='ACTIVE', effective_start_date=date(2026, 1, 1)
            )
            PricingRuleCondition.objects.create(pricing_rule=rule, attribute_name='modifier', operator='EQ', attribute_value=mod)
            rule.calculate_score()

        # --- RULE 7: STOP LOSS (Implants) ---
        # A. Base Add-on for Implants ($500)
        rule_implant_base = PricingRule.objects.create(
            contract=contract, rule_type='ADD_ON', methodology=flat_method,
            flat_rate=Decimal('500.00'), status='ACTIVE', effective_start_date=date(2026, 1, 1)
        )
        PricingRuleCondition.objects.create(pricing_rule=rule_implant_base, attribute_name='rev_code', operator='EQ', attribute_value='0278')
        rule_implant_base.calculate_score()

        # B. Stop Loss Trigger (Threshold $10k)
        rule_sl = PricingRule.objects.create(
            contract=contract, rule_type='STOP_LOSS', methodology=flat_method,
            threshold_amount=Decimal('10000.00'), multiplier=Decimal('0.50'),
            status='ACTIVE', effective_start_date=date(2026, 1, 1)
        )
        PricingRuleCondition.objects.create(pricing_rule=rule_sl, attribute_name='rev_code', operator='EQ', attribute_value='0278')
        rule_sl.calculate_score()

        # --- RULE 8: OUT OF NETWORK (OON) ---
        # Rule: Pay 100% of Medicare if Network Status = OON
        rule_oon = PricingRule.objects.create(
            contract=contract,
            rule_type='BASE',
            methodology=rbrvs_method,
            base_fee_schedule=fs,
            multiplier=Decimal('1.00'), 
            status='ACTIVE', effective_start_date=date(2026, 1, 1)
        )
        # Condition 1: Applies to standard CPT codes (> 10000)
        PricingRuleCondition.objects.create(pricing_rule=rule_oon, attribute_name='code', operator='GT', attribute_value='10000')
        # Condition 2: Network Status = OON
        PricingRuleCondition.objects.create(pricing_rule=rule_oon, attribute_name='network_status', operator='EQ', attribute_value='OON')
        rule_oon.calculate_score()
        self.stdout.write(f"✅ Created OON Rule (Score: {rule_oon.specificity_score})")

        self.stdout.write("✅ EXTENSIVE SEED COMPLETE (35+ Scenarios Ready)")