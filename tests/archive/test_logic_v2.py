import os
import django
from decimal import Decimal

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from core.models import ProviderContract, PricingRule, FeeScheduleRate

def calculate_price(contract, code, billed_amount):
    print(f"\n🔎 PRICING CLAIM LINE: Code {code} | Billed ${billed_amount}")

    # 1. Find Matching Rule (Logic Engine)
    # Fetch all active rules for this contract, sorted by Score (High -> Low)
    rules = PricingRule.objects.filter(contract=contract, is_active=1).order_by('-specificity_score')
    
    selected_rule = None
    
    for rule in rules:
        # Check Conditions
        is_match = True
        for cond in rule.conditions.all():
            if cond.attribute_name == 'code' and cond.attribute_value != code:
                is_match = False
                break
        
        if is_match:
            selected_rule = rule
            break # Stop at the first (highest score) match
            
    if not selected_rule:
        print("❌ DENIED: No matching rule found.")
        return None

    print(f"   ✅ Matched Rule: '{selected_rule.rule_name}' (Method: {selected_rule.methodology_code})")

    # 2. Execute Math based on Methodology
    final_price = Decimal('0.00')

    if selected_rule.methodology_code == 'RBRVS':
        # Logic: Fee Schedule Rate * Multiplier
        try:
            rate_entry = FeeScheduleRate.objects.get(
                fee_schedule=selected_rule.base_fee_schedule,
                code_id=code
            )
            final_price = rate_entry.rate_amount * selected_rule.multiplier
            print(f"   🧮 Calc: FS Rate ${rate_entry.rate_amount} * {selected_rule.multiplier}")

        except FeeScheduleRate.DoesNotExist:
            print("   ❌ Error: Fee Schedule Rate missing.")
            return None

    elif selected_rule.methodology_code == 'FLAT_RATE':
        # Logic: Fixed Price
        final_price = selected_rule.flat_rate
        print(f"   🧮 Calc: Flat Rate Applied")

    elif selected_rule.methodology_code == 'PERCENT_BILLED':
        # Logic: Billed Amount * Multiplier
        final_price = billed_amount * selected_rule.multiplier
        print(f"   🧮 Calc: Billed ${billed_amount} * {selected_rule.multiplier}")

    print(f"   🚀 FINAL ALLOWED: ${final_price:.2f}")
    return final_price

def run_tests():
    # Load Contract
    contract = ProviderContract.objects.get(legacy_contract_number='CONT-2026-A')

    # TEST CASE 1: Standard RBRVS
    # Code 99213 (Office Visit) -> Should match "Standard RBRVS"
    calculate_price(contract, '99213', Decimal('250.00'))

    # TEST CASE 2: Flat Rate
    # Code 73030 (X-Ray) -> Should match "X-Ray Flat Rate" ($75.00)
    calculate_price(contract, '73030', Decimal('150.00'))

    # TEST CASE 3: Percent of Billed
    # Code 29806 (Implant) -> Should match "Implant Carve Out" (50% of Billed)
    calculate_price(contract, '29806', Decimal('5000.00'))

if __name__ == "__main__":
    run_tests()