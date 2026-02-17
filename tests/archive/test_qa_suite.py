import os
import django
from decimal import Decimal

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from core.models import ProviderContract, PricingRule, FeeScheduleRate, RefModifier

# ==================================================
# 1. THE TEST HARNESS (Reusable Engine Class)
# ==================================================
class PricingTestEngine:
    def __init__(self, contract_id):
        self.contract = ProviderContract.objects.get(legacy_contract_number=contract_id)
        self.rules = list(PricingRule.objects.filter(contract=self.contract, is_active=1).order_by('-specificity_score'))

    def execute_claim(self, lines):
        """Processes a list of lines and applies Global Logic (Stop Loss / MPPR)"""
        results = []
        total_billed = sum(l['billed'] for l in lines)
        trace_log = []

        # STEP 1: Global Stop Loss Check
        stop_loss_rule = None
        for rule in self.rules:
            if rule.rule_type == 'STOP_LOSS':
                threshold = rule.flat_rate or Decimal('9999999.99')
                if total_billed >= threshold:
                    stop_loss_rule = rule
                    trace_log.append(f"GLOBAL STOP LOSS TRIGGERED: > ${threshold}")
                    break
        
        # STEP 2: Line Level Pricing
        priced_lines = []
        for line in lines:
            line_res = self.price_single_line(line, stop_loss_rule)
            priced_lines.append(line_res)
            trace_log.append(f"Line {line['code']}: {line_res['method']} -> ${line_res['allowed']:.2f} ({line_res['status']})")

        # STEP 3: MPPR (Orchestration)
        # Sort by Allowed Amount Descending
        # Only apply MPPR if Stop Loss didn't trigger
        if not stop_loss_rule:
            priced_lines.sort(key=lambda x: x['allowed'], reverse=True)
            for i, p_line in enumerate(priced_lines):
                if p_line['method'] == 'RBRVS':
                    if i > 0: # Secondary Procedure
                        p_line['allowed'] *= Decimal('0.5')
                        p_line['status'] += "_MPPR_SEC"
                        trace_log.append(f"MPPR Applied to {p_line['code']}: 50% Reduction")
                    else:
                        p_line['status'] += "_PRIMARY"

        return priced_lines, trace_log

    def price_single_line(self, line, force_rule=None):
        code = line['code']
        billed = line['billed']
        mods = line.get('modifiers', [])
        units = line.get('units', 1)

        # A. Force Rule (Stop Loss)
        if force_rule:
            return {
                'code': code, 
                'allowed': billed * force_rule.multiplier, 
                'method': 'STOP_LOSS', 
                'status': 'PAYABLE'
            }

        # B. Find Rule
        selected_rule = None
        for rule in self.rules:
            if rule.rule_type == 'STOP_LOSS': continue
            is_match = True
            for cond in rule.conditions.all():
                if cond.attribute_name == 'code' and cond.attribute_value != code:
                    is_match = False; break
            if is_match:
                selected_rule = rule; break
        
        if not selected_rule:
            return {'code': code, 'allowed': Decimal('0.00'), 'method': 'NONE', 'status': 'DENIED_NO_RULE'}

        # C. Calculate Base
        base = Decimal('0.00')
        if selected_rule.methodology_code == 'RBRVS':
            try:
                rate = FeeScheduleRate.objects.get(fee_schedule=selected_rule.base_fee_schedule, code_id=code).rate_amount
                base = rate * selected_rule.multiplier * units
            except:
                return {'code': code, 'allowed': Decimal('0.00'), 'method': 'ERROR', 'status': 'SUSPEND_MISSING_RATE'}
        elif selected_rule.methodology_code == 'FLAT_RATE':
            base = selected_rule.flat_rate * units
        elif selected_rule.methodology_code == 'PERCENT_BILLED':
            base = billed * selected_rule.multiplier

        # D. Modifiers
        for m in mods:
            try:
                mod_obj = RefModifier.objects.get(modifier_code=m)
                base *= (mod_obj.percentage_adjustment / 100)
            except: pass

        return {'code': code, 'allowed': base, 'method': selected_rule.methodology_code, 'status': 'PAYABLE'}

# ==================================================
# 2. THE TEST RUNNER (Layers 1-4)
# ==================================================
engine = PricingTestEngine('CONT-QA-2026')

def run_test_case(scenario_id, description, input_lines, expected_total, expected_status):
    print(f"\n🧪 {scenario_id}: {description}")
    
    results, trace = engine.execute_claim(input_lines)
    
    total_allowed = sum(r['allowed'] for r in results)
    primary_status = results[0]['status'] if results else 'NO_LINES'

    # Validations
    pass_amt = abs(total_allowed - Decimal(expected_total)) < 0.05
    pass_stat = expected_status in primary_status

    print(f"   Input: {[l['code'] for l in input_lines]}")
    print(f"   Result: ${total_allowed:.2f} | Status: {primary_status}")
    if pass_amt and pass_stat:
        print("   ✅ PASS")
    else:
        print(f"   ❌ FAIL (Exp: ${expected_total} | {expected_status})")
        print("   Trace:", trace)

# --- LAYER 1: METHODOLOGY UNIT TESTS ---
print("\n--- LAYER 1: METHODOLOGIES ---")
# RBRVS-01: Standard (99213 = $100 * 1.5 = $150)
run_test_case('RBRVS-01', 'Standard RBRVS', [{'code': '99213', 'billed': Decimal('200')}], '150.00', 'PAYABLE')

# FLAT-01: Flat Rate (73030 = $75 Fixed)
run_test_case('FLAT-01', 'Flat Rate Override', [{'code': '73030', 'billed': Decimal('500')}], '75.00', 'PAYABLE')

# PCT-01: Percent Billed (29806 = $1000 * 0.50 = $500)
run_test_case('PCT-01', 'Percent of Billed', [{'code': '29806', 'billed': Decimal('1000')}], '500.00', 'PAYABLE')

# --- LAYER 2: RULE CONFLICTS ---
print("\n--- LAYER 2: RULE CONFLICTS ---")
# CONFLICT-01: Specific (Score 20) vs Generic (Score 10)
# 99214 matches "Generic 150%" AND "Specific 200%". Specific should win.
# $150 Rate * 2.00 = $300.00
run_test_case('CNFL-01', 'Specificity Win', [{'code': '99214', 'billed': Decimal('500')}], '300.00', 'PAYABLE')

# --- LAYER 3: ORCHESTRATION (MPPR & STOP LOSS) ---
print("\n--- LAYER 3: ORCHESTRATION ---")
# MPPR-01: Two RBRVS Lines
# Line 1: 99214 ($300) -> Primary
# Line 2: 99213 ($150) -> Secondary (50% = $75)
# Total: $375.00
run_test_case('MPPR-01', 'MPPR Logic', 
              [{'code': '99214', 'billed': 500}, {'code': '99213', 'billed': 200}], 
              '375.00', 'PAYABLE')

# SL-01: Stop Loss Trigger
# Total Billed $6,000 (> $5,000 threshold). 
# Pays 60% of $6,000 = $3,600.
run_test_case('SL-01', 'Global Stop Loss', 
              [{'code': '99214', 'billed': 6000}], 
              '3600.00', 'PAYABLE')

# --- LAYER 4: FAILURE MODES ---
print("\n--- LAYER 4: FAILURE MODES ---")
# ERR-01: No Rule Logic
run_test_case('ERR-01', 'No Matching Rule', [{'code': '36415', 'billed': 50}], '0.00', 'DENIED')