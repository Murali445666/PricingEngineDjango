import os
import django
from decimal import Decimal

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from core.models import ProviderContract, PricingRule, FeeScheduleRate, RefModifier

# ==========================================
# THE ENGINE SERVICE (Simulation)
# ==========================================
class PricingEngine:
    def __init__(self, contract_id):
        self.contract = ProviderContract.objects.get(legacy_contract_number=contract_id)
        # Pre-fetch rules for performance
        self.rules = list(PricingRule.objects.filter(contract=self.contract, is_active=1).order_by('-specificity_score'))

    def calculate_line(self, code, billed, units=1, modifiers=[]):
        """Calculates Base Price for a single line (before MPPR)"""
        
        # A. Stop Loss Check (Highest Priority)
        for rule in self.rules:
            if rule.rule_type == 'STOP_LOSS':
                threshold = rule.flat_rate or Decimal('999999.99')
                if billed >= threshold:
                    return {
                        'rule': rule.rule_name,
                        'base': billed * rule.multiplier,
                        'method': 'STOP_LOSS'
                    }

        # B. Standard Rule Logic
        selected_rule = None
        for rule in self.rules:
            if rule.rule_type == 'STOP_LOSS': continue # Skip stop loss here
            
            # Condition Matcher
            is_match = True
            for cond in rule.conditions.all():
                if cond.attribute_name == 'code' and cond.attribute_value != code:
                    is_match = False
                    break
            if is_match:
                selected_rule = rule
                break
        
        if not selected_rule:
            return {'rule': 'None', 'base': Decimal('0.00'), 'method': 'DENIED'}

        # C. Calculate Base
        price = Decimal('0.00')
        if selected_rule.methodology_code == 'RBRVS':
            try:
                rate = FeeScheduleRate.objects.get(fee_schedule=selected_rule.base_fee_schedule, code_id=code).rate_amount
                price = rate * selected_rule.multiplier * units
            except:
                return {'rule': 'Error', 'base': Decimal('0.00'), 'method': 'ERROR'}
        elif selected_rule.methodology_code == 'FLAT_RATE':
            price = selected_rule.flat_rate * units
        elif selected_rule.methodology_code == 'PERCENT_BILLED':
            price = billed * selected_rule.multiplier

        # D. Apply Modifiers
        mod_adjustment = Decimal('1.00')
        for mod in modifiers:
            try:
                m_obj = RefModifier.objects.get(modifier_code=mod)
                mod_adj = m_obj.percentage_adjustment / 100
                mod_adjustment *= mod_adj
            except:
                pass # Unknown modifier ignored
        
        final_base = price * mod_adjustment
        return {
            'rule': selected_rule.rule_name,
            'base': final_base,
            'method': selected_rule.methodology_code
        }

    def price_claim(self, lines):
        """Orchestrates MPPR across multiple lines"""
        print(f"\n🚀 PROCESSING BATCH: {len(lines)} Lines")
        
        # 1. Calculate Base for ALL lines
        priced_lines = []
        for line in lines:
            res = self.calculate_line(line['code'], line['billed'], line.get('units', 1), line.get('modifiers', []))
            line.update(res)
            priced_lines.append(line)

        # 2. Sort by Base Price (High to Low) for MPPR
        priced_lines.sort(key=lambda x: x['base'], reverse=True)

        # 3. Apply MPPR (100% Primary, 50% Secondary)
        # Note: Flat Rates and Stop Loss usually exempt from MPPR. Logic handled here.
        final_total = Decimal('0.00')
        
        for i, line in enumerate(priced_lines):
            is_mppr_eligible = line['method'] == 'RBRVS' # Only RBRVS gets cut
            mppr_factor = Decimal('1.0')
            
            if is_mppr_eligible and i > 0: # Secondary lines
                mppr_factor = Decimal('0.5')
                status = "MPPR_SECONDARY"
            else:
                status = "PRIMARY"

            final_line_price = line['base'] * mppr_factor
            final_total += final_line_price

            print(f"   Line {i+1}: {line['code']} | Mod: {line.get('modifiers')} | Base: ${line['base']:.2f} | {status} ({mppr_factor*100}%) -> ${final_line_price:.2f} [{line['rule']}]")

        print(f"💰 TOTAL CLAIM ALLOWED: ${final_total:.2f}")
        return final_total

# ==========================================
# RUN TEST SCENARIOS
# ==========================================
engine = PricingEngine('CONT-2026-A')

# Scenario 1: MPPR Logic
# High Value Knee (29881 - $1000) + Low Value Anesthesia (00100 - $200)
# Expectation: Knee paid 100% ($1500), Anesthesia paid 50% of ($300) = $150
print("\n--- TEST 1: MPPR (Standard RBRVS) ---")
engine.price_claim([
    {'code': '00100', 'billed': Decimal('500.00'), 'modifiers': []}, # Lower Value
    {'code': '29881', 'billed': Decimal('3000.00'), 'modifiers': []} # Higher Value
])

# Scenario 2: Bilateral Modifier
# Knee Surgery (29881) with Modifier 50 (150%)
# Base: $1000 * 1.5 (Contract) = $1500. 
# Mod 50: $1500 * 1.5 = $2250.
print("\n--- TEST 2: Modifier 50 (Bilateral) ---")
engine.price_claim([
    {'code': '29881', 'billed': Decimal('5000.00'), 'modifiers': ['50']}
])

# Scenario 3: Stop Loss
# Implant (29806) billed at $15,000 (Above $10k threshold)
# Should trigger Stop Loss rule (60%) -> $9,000.
# Should IGNORE the "Percent of Billed 50%" rule.
print("\n--- TEST 3: Stop Loss (High Dollar) ---")
engine.price_claim([
    {'code': '29806', 'billed': Decimal('15000.00'), 'modifiers': []}
])

# Scenario 4: Units
# 3 Units of Office Visit (99213)
# Base $100 * 1.5 = $150. Units 3 = $450.
print("\n--- TEST 4: Units Logic ---")
engine.price_claim([
    {'code': '99213', 'billed': Decimal('600.00'), 'units': 3, 'modifiers': []}
])