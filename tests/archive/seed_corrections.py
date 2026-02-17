import os
import django
from decimal import Decimal

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from core.models import RefModifier, ProviderContract, PricingRule, PricingRuleCondition

def run_corrections():
    print("🛠️  Applying Data Corrections...")

    # 1. Fix Modifier Percentages
    # Modifier 50 (Bilateral) -> 150%
    RefModifier.objects.update_or_create(
        modifier_code='50',
        defaults={'percentage_adjustment': Decimal('150.00'), 'description': 'Bilateral Procedure'}
    )
    # Modifier 80 (Assistant) -> 16%
    RefModifier.objects.update_or_create(
        modifier_code='80',
        defaults={'percentage_adjustment': Decimal('16.00'), 'description': 'Assistant Surgeon'}
    )
    print("✅ Modifiers Updated (50=150%, 80=16%)")

    # 2. Add Stop Loss Rule
    # Scenario: If Billed Amount > $10,000, ignore RBRVS and pay 60% of Billed.
    contract = ProviderContract.objects.get(legacy_contract_number='CONT-2026-A')
    
    rule_stop, _ = PricingRule.objects.get_or_create(
        contract=contract,
        rule_name='High Dollar Stop Loss',
        defaults={
            'rule_type': 'STOP_LOSS', # Special Type
            'methodology_code': 'PERCENT_BILLED',
            'multiplier': Decimal('0.6000'), # 60%
            'specificity_score': 99, # Highest Priority checks first
            'is_active': 1,
            'flat_rate': Decimal('10000.00') # Using flat_rate column to store threshold
        }
    )
    print("✅ Stop Loss Rule Created (Threshold: $10k)")

if __name__ == "__main__":
    run_corrections()