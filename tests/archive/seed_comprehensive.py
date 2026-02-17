import os
import django
from decimal import Decimal
from datetime import date

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from core.models import (
    ProviderOrganization, PayerNetwork, ProviderContract, 
    PricingRule, PricingRuleCondition, RefProcedureCode, 
    FeeSchedule, FeeScheduleRate, RefModifier
)

def seed_kitchen_sink():
    print("🏗️  Building 'Kitchen Sink' Test Data...")

    # 1. Setup Organization & Contract
    org, _ = ProviderOrganization.objects.get_or_create(
        organization_id='ORG-TEST', defaults={'name': 'Universal Health', 'tax_id': '99-9999999'}
    )
    net, _ = PayerNetwork.objects.get_or_create(
        network_id='NET-TEST', defaults={'network_name': 'Test Commercial', 'payer_org': org}
    )
    contract, _ = ProviderContract.objects.get_or_create(
        legacy_contract_number='CONT-UNIVERSAL',
        defaults={
            'contract_name': 'Universal Pricing Contract 2026',
            'provider_org': org, 'network': net,
            'status': 'ACTIVE', 'effective_start_date': date(2026, 1, 1)
        }
    )

    # 2. Setup Fee Schedule (The "Base Rates")
    fs, _ = FeeSchedule.objects.get_or_create(name='Universal FS 2026', defaults={'version': 1})
    
    # Test Codes & Rates
    # 99213 (Office Visit) -> $100
    # 73030 (X-Ray)        -> $50
    # 29881 (Knee Surgery) -> $1,000
    # 70450 (CT Scan)      -> $200 (For Split Billing)
    test_codes = [
        ('99213', 'CPT', '100.00'),
        ('73030', 'CPT', '50.00'),
        ('29881', 'CPT', '1000.00'),
        ('70450', 'CPT', '200.00'), 
        ('29806', 'CPT', '0.00') # Price irrelevant for % of Billed
    ]
    for code, ctype, rate in test_codes:
        RefProcedureCode.objects.get_or_create(code_id=code, code_type=ctype)
        FeeScheduleRate.objects.get_or_create(fee_schedule=fs, code_id=code, defaults={'rate_amount': Decimal(rate)})

    # 3. Define Modifiers (Standard Splits)
    RefModifier.objects.update_or_create(modifier_code='26', defaults={'percentage_adjustment': 40.00, 'description': 'Professional'})
    RefModifier.objects.update_or_create(modifier_code='TC', defaults={'percentage_adjustment': 60.00, 'description': 'Technical'})
    RefModifier.objects.update_or_create(modifier_code='50', defaults={'percentage_adjustment': 150.00, 'description': 'Bilateral'})

    # ==========================================
    # 4. CREATE RULES (The Logic Matrix)
    # ==========================================

    # RULE A: Generic Catch-All (Standard RBRVS)
    # Logic: Pay 150% of FS for anything not specified below.
    PricingRule.objects.get_or_create(
        contract=contract, rule_name='Generic RBRVS 150%',
        defaults={
            'rule_type': 'BASE', 'methodology_code': 'RBRVS',
            'multiplier': 1.5000, 'base_fee_schedule': fs,
            'specificity_score': 1, 'is_active': 1
        }
    )

    # RULE B: Flat Rate Override (X-Ray)
    # Logic: Code 73030 gets exactly $75.00
    r_flat, _ = PricingRule.objects.get_or_create(
        contract=contract, rule_name='X-Ray Flat Rate',
        defaults={
            'rule_type': 'BASE', 'methodology_code': 'FLAT_RATE',
            'flat_rate': 75.00, 'specificity_score': 20, 'is_active': 1
        }
    )
    PricingRuleCondition.objects.get_or_create(pricing_rule=r_flat, attribute_name='code', attribute_value='73030')

    # RULE C: Percent of Billed (Implant)
    # Logic: Code 29806 gets 50% of Billed Charges
    r_pct, _ = PricingRule.objects.get_or_create(
        contract=contract, rule_name='Implant Carve Out',
        defaults={
            'rule_type': 'BASE', 'methodology_code': 'PERCENT_BILLED',
            'multiplier': 0.5000, 'specificity_score': 30, 'is_active': 1
        }
    )
    PricingRuleCondition.objects.get_or_create(pricing_rule=r_pct, attribute_name='code', attribute_value='29806')

    # RULE D: Stop Loss (Global Safety Net)
    # Logic: If Billed > $10,000, Pay 60% of Billed (Overrides everything)
    PricingRule.objects.get_or_create(
        contract=contract, rule_name='Stop Loss Protection',
        defaults={
            'rule_type': 'STOP_LOSS', 'methodology_code': 'PERCENT_BILLED',
            'multiplier': 0.6000, 'flat_rate': 10000.00, # Threshold stored here
            'specificity_score': 99, 'is_active': 1
        }
    )

    print("✅ Kitchen Sink Data Created Successfully!")

if __name__ == "__main__":
    seed_kitchen_sink()