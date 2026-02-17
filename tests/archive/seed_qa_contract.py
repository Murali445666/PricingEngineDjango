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

def seed_qa_data():
    print("🏗️  Constructing QA Battle-Testing Contract...")

    # 1. QA Organization & Contract
    org, _ = ProviderOrganization.objects.get_or_create(
        organization_id='ORG-QA', defaults={'name': 'QA Health System', 'tax_id': 'QA-9999'}
    )
    net, _ = PayerNetwork.objects.get_or_create(
        network_id='NET-QA', defaults={'network_name': 'QA Commercial', 'payer_org': org}
    )
    contract, _ = ProviderContract.objects.get_or_create(
        legacy_contract_number='CONT-QA-2026',
        defaults={
            'contract_name': 'QA Master Contract',
            'provider_org': org, 'network': net,
            'status': 'ACTIVE', 'effective_start_date': date(2026, 1, 1)
        }
    )

    # 2. Reference Data (Codes & Modifiers)
    fs, _ = FeeSchedule.objects.get_or_create(name='QA Master FS', defaults={'version': 1})
    
    # Mapping Codes to Scenarios
    # 99213: Standard RBRVS
    # 99214: Conflict Scenario (Has both Generic and Specific Rules)
    # 73030: Flat Rate Carve Out
    # 29806: Percent of Billed
    # 10000: Stop Loss Trigger
    # 00100: MPPR Code (Anesthesia)
    # 99100: Add-on Code (Requires 00100)
    qa_codes = [
        ('99213', 'CPT', '100.00'),
        ('99214', 'CPT', '150.00'),
        ('73030', 'CPT', '50.00'),
        ('29806', 'CPT', '0.00'),
        ('10000', 'CPT', '500.00'),
        ('00100', 'CPT', '200.00'),
        ('99100', 'CPT', '50.00'), # Add-on
        ('36415', 'CPT', '0.00')   # No Rule Defined (Should Deny)
    ]
    
    for code, ctype, rate in qa_codes:
        RefProcedureCode.objects.get_or_create(code_id=code, code_type=ctype)
        FeeScheduleRate.objects.update_or_create(
            fee_schedule=fs, code_id=code, defaults={'rate_amount': Decimal(rate)}
        )

    # Modifiers
    mods = [
        ('26', 40.00), ('TC', 60.00), ('50', 150.00), 
        ('59', 100.00), ('LT', 100.00), ('RT', 100.00)
    ]
    for m, rate in mods:
        RefModifier.objects.update_or_create(
            modifier_code=m, defaults={'percentage_adjustment': Decimal(rate)}
        )

    # ====================================================
    # 3. RULE LAYERING (The Complex Logic)
    # ====================================================

    # A. GLOBAL STOP LOSS (Highest Priority)
    # Rule: If Billed > $5,000, Pay 60% of Billed.
    PricingRule.objects.update_or_create(
        contract=contract, rule_name='Global Stop Loss > 5k',
        defaults={
            'rule_type': 'STOP_LOSS', 'methodology_code': 'PERCENT_BILLED',
            'multiplier': 0.6000, 'flat_rate': 5000.00, # Threshold
            'specificity_score': 100, 'is_active': 1
        }
    )

    # B. SPECIFIC CARVE OUTS (High Priority)
    # 73030 -> Flat $75
    r_flat, _ = PricingRule.objects.update_or_create(
        contract=contract, rule_name='X-Ray Flat Rate',
        defaults={
            'rule_type': 'BASE', 'methodology_code': 'FLAT_RATE',
            'flat_rate': 75.00, 'specificity_score': 50, 'is_active': 1
        }
    )
    PricingRuleCondition.objects.get_or_create(pricing_rule=r_flat, attribute_name='code', attribute_value='73030')

    # 29806 -> 50% Billed
    r_pct, _ = PricingRule.objects.update_or_create(
        contract=contract, rule_name='Implant 50%',
        defaults={
            'rule_type': 'BASE', 'methodology_code': 'PERCENT_BILLED',
            'multiplier': 0.5000, 'specificity_score': 50, 'is_active': 1
        }
    )
    PricingRuleCondition.objects.get_or_create(pricing_rule=r_pct, attribute_name='code', attribute_value='29806')

    # C. CONFLICT TEST (Medium Priority)
    # 99214 -> 200% of RBRVS (Specific Override)
    r_override, _ = PricingRule.objects.update_or_create(
        contract=contract, rule_name='99214 Special Rate',
        defaults={
            'rule_type': 'BASE', 'methodology_code': 'RBRVS',
            'multiplier': 2.0000, 'base_fee_schedule': fs,
            'specificity_score': 20, 'is_active': 1
        }
    )
    PricingRuleCondition.objects.get_or_create(pricing_rule=r_override, attribute_name='code', attribute_value='99214')

    # D. GENERIC FALLBACK (Low Priority)
    # All other codes -> 150% RBRVS
    PricingRule.objects.update_or_create(
        contract=contract, rule_name='Generic RBRVS 150%',
        defaults={
            'rule_type': 'BASE', 'methodology_code': 'RBRVS',
            'multiplier': 1.5000, 'base_fee_schedule': fs,
            'specificity_score': 10, 'is_active': 1
        }
    )

    print("✅ QA Contract Seeding Complete.")

if __name__ == "__main__":
    seed_qa_data()