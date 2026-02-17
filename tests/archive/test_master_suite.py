import os
import django
from decimal import Decimal

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from core.models import ProviderContract, PricingRule, FeeScheduleRate, RefModifier

# --- REUSABLE PRICING ENGINE CLASS ---
class PricingEngine:
    def __init__(self, contract_id):
        self.contract = ProviderContract.objects.get(legacy_contract_number=contract_id)
        self.rules = list(PricingRule.objects.filter(contract=self.contract, is_active=1).order_by('-specificity_score'))

    def calculate_price(self, code, billed, modifiers=[]):
        # 1. Stop Loss Check
        for rule in self.rules:
            if rule.rule_type == 'STOP_LOSS':
                threshold = rule.flat_rate or Decimal('999999.99')
                if billed >= threshold:
                    return billed * rule.multiplier, "STOP_LOSS"

        # 2. Find Base Rule
        selected_rule = None
        for rule in self.rules:
            if rule.rule_type == 'STOP_LOSS': continue
            # Condition Check
            is_match = True
            for cond in rule.conditions.all():
                if cond.attribute_name == 'code' and cond.attribute_value != code:
                    is_match = False; break
            if is_match:
                selected_rule = rule; break
        
        if not selected_rule: return Decimal('0.00'), "DENIED"

        # 3. Apply Methodology
        price = Decimal('0.00')
        if selected_rule.methodology_code == 'RBRVS':
            rate = FeeScheduleRate.objects.get(fee_schedule=selected_rule.base_fee_schedule, code_id=code).rate_amount
            price = rate * selected_rule.multiplier
        elif selected_rule.methodology_code == 'FLAT_RATE':
            price = selected_rule.flat_rate
        elif selected_rule.methodology_code == 'PERCENT_BILLED':
            price = billed * selected_rule.multiplier

        # 4. Apply Modifiers
        for mod in modifiers:
            try:
                m_obj = RefModifier.objects.get(modifier_code=mod)
                price = price * (m_obj.percentage_adjustment / 100)
            except: pass
            
        return price, selected_rule.methodology_code

# --- RUNNING THE SCENARIOS ---
engine = PricingEngine('CONT-UNIVERSAL')

def assert_price(scenario, code, billed, modifiers, expected, expected_method):
    price, method = engine.calculate_price(code, Decimal(billed), modifiers)
    print(f"\n🧪 {scenario}")
    print(f"   Input: Code {code} | Billed ${billed} | Mods {modifiers}")
    print(f"   Result: ${price:.2f} ({method})")
    
    if abs(price - Decimal(expected)) < 0.01:
        print("   ✅ PASS")
    else:
        print(f"   ❌ FAIL (Expected ${expected})")

# 1. Standard RBRVS (Generic Rule)
# Rate $100 * 1.5 Multiplier = $150.00
assert_price("Scenario 1: Standard RBRVS", '99213', '250.00', [], '150.00', 'RBRVS')

# 2. Flat Rate Override
# Code 73030 -> Fixed $75.00 (Ignores FS $50 * 1.5)
assert_price("Scenario 2: Flat Rate Override", '73030', '200.00', [], '75.00', 'FLAT_RATE')

# 3. Percent of Billed
# Code 29806 -> 50% of $5,000 = $2,500.00
assert_price("Scenario 3: Carve Out (Percent Billed)", '29806', '5000.00', [], '2500.00', 'PERCENT_BILLED')

# 4. Stop Loss (High Dollar)
# Code 29806 Billed $15,000 -> Threshold $10k met -> 60% of $15k = $9,000.00
# (Notice: This overrides the 50% rule from Scenario 3)
assert_price("Scenario 4: Stop Loss Trigger", '29806', '15000.00', [], '9000.00', 'STOP_LOSS')

# 5. Modifier Logic (Professional Component)
# Code 70450 (CT) Base $200 * 1.5 = $300.
# Modifier 26 (Prof) = 40%. -> $300 * 0.40 = $120.00
assert_price("Scenario 5: Modifier 26 (Split Billing)", '70450', '800.00', ['26'], '120.00', 'RBRVS')