import os
import django
from decimal import Decimal

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from core.models import ProviderContract, PricingRule, PricingRuleCondition

def seed_advanced():
    print("🌱 Seeding Advanced Pricing Rules...")

    # 1. Get the Contract
    contract = ProviderContract.objects.get(legacy_contract_number='CONT-2026-A')

    # ==========================================
    # CASE 1: FLAT RATE (Fixed Price)
    # Scenario: "Pay $75.00 for X-Ray (73030), ignore fee schedule."
    # ==========================================
    rule_flat, _ = PricingRule.objects.get_or_create(
        contract=contract,
        rule_name='X-Ray Flat Rate',
        defaults={
            'rule_type': 'BASE',
            'methodology_code': 'FLAT_RATE',
            'flat_rate': Decimal('75.00'),
            'specificity_score': 20, # Higher score than standard RBRVS
            'is_active': 1
        }
    )
    PricingRuleCondition.objects.get_or_create(
        pricing_rule=rule_flat,
        attribute_name='code',
        operator='EQ',
        attribute_value='73030'
    )
    print("✅ Created Rule: Flat Rate ($75.00) for 73030")

    # ==========================================
    # CASE 2: PERCENT OF BILLED (Carve Out)
    # Scenario: "Pay 50% of Billed Charges for Implants (29806)."
    # ==========================================
    rule_pct, _ = PricingRule.objects.get_or_create(
        contract=contract,
        rule_name='Implant Carve Out',
        defaults={
            'rule_type': 'BASE',
            'methodology_code': 'PERCENT_BILLED',
            'multiplier': Decimal('0.5000'), # 50%
            'specificity_score': 30, # Highest Priority
            'is_active': 1
        }
    )
    PricingRuleCondition.objects.get_or_create(
        pricing_rule=rule_pct,
        attribute_name='code',
        operator='EQ',
        attribute_value='29806'
    )
    print("✅ Created Rule: Percent of Billed (50%) for 29806")

if __name__ == "__main__":
    seed_advanced()