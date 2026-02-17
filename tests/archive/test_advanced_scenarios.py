from django.core.management.base import BaseCommand
from core.services.pricing_engine import PricingEngine
from core.models import ProviderOrganization, PricingRule, PricingRuleCondition, Code, FeeScheduleRate, FeeSchedule, CodeSet
from decimal import Decimal

class Command(BaseCommand):
    help = 'Tests Section B (Hierarchy) and Section C (Integrity) - SELF CLEANING'

    def handle(self, *args, **kwargs):
        self.stdout.write("--- 🛡️ TESTING ADVANCED SCENARIOS 🛡️ ---")
        
        try:
            org = ProviderOrganization.objects.get(name='Allegheny Health Network')
        except:
            self.stdout.write("❌ Seed data missing. Run 'python manage.py seed_data' first.")
            return

        contract = PricingRule.objects.first().contract
        engine = PricingEngine()

        # =========================================================
        # 0. CLEANUP (Fixes the "Returned 3" and "Stale Rule" bugs)
        # =========================================================
        self.stdout.write("🧹 Cleaning up old test data...")
        
        # Delete any existing rules with Multiplier 2.0 (The Gold Rules)
        PricingRule.objects.filter(contract=contract, multiplier=Decimal('2.00')).delete()
        
        # Delete any rules targeting the Ghost Code 'XXXXX'
        # We find them by looking for conditions that point to 'XXXXX'
        ghost_rules = PricingRule.objects.filter(conditions__attribute_value='XXXXX')
        ghost_rules.delete()
        
        self.stdout.write("✅ Cleanup complete. Database ready.")

        # =========================================================
        # SECTION B: PLAN OVERRIDES (Hierarchy)
        # =========================================================
        self.print_header("B. PLAN-LEVEL OVERRIDES")
        
        # 1. Setup: Create the Gold Rule (Fresh using .create, not get_or_create)
        rule_gold = PricingRule.objects.create(
            contract=contract,
            rule_type='BASE',
            multiplier=Decimal('2.00'), # Target: $170.00
            methodology_id=PricingRule.objects.first().methodology_id,
            base_fee_schedule=PricingRule.objects.first().base_fee_schedule,
            status='ACTIVE',
            effective_start_date="2026-01-01"
        )
        
        # 2. Add Conditions
        PricingRuleCondition.objects.create(pricing_rule=rule_gold, attribute_name='code', operator='EQ', attribute_value='99213')
        PricingRuleCondition.objects.create(pricing_rule=rule_gold, attribute_name='network_status', operator='EQ', attribute_value='INN')
        PricingRuleCondition.objects.create(pricing_rule=rule_gold, attribute_name='plan_id', operator='EQ', attribute_value='GOLD')
        
        # 3. Trigger Calculation (Score should be 10+10+50+10 = 80)
        rule_gold.calculate_score() 
        self.stdout.write(f"   > Gold Rule Score: {rule_gold.specificity_score}")

        # 4. IMPORTANT: Refresh Standard Rule Score (Ensure it's accurate)
        std_rule = PricingRule.objects.filter(
            contract=contract, 
            multiplier=Decimal('1.50'),
            conditions__attribute_value='99213'
        ).first()
        if std_rule:
            std_rule.calculate_score() # Should be ~20

        # 5. Test Gold Plan
        req_gold = {
            "provider_id": str(org.organization_id),
            "date_of_service": "2026-06-01",
            "plan_id": "GOLD", 
            "lines": [{"line_id": 1, "code": "99213", "billed": "200.00"}]
        }
        res_gold = engine.calculate_claim(req_gold)
        self.verify(res_gold, 1, "170.00", "Gold Plan (Specific Rule)")

        # 6. Test Standard (Sanity Check)
        req_std = {
            "provider_id": str(org.organization_id),
            "date_of_service": "2026-06-01",
            "lines": [{"line_id": 1, "code": "99213", "billed": "200.00"}]
        }
        res_std = engine.calculate_claim(req_std)
        self.verify(res_std, 1, "127.50", "Standard Plan (Base Rule)")

        # =========================================================
        # SECTION C: DATA INTEGRITY (Missing Data)
        # =========================================================
        self.print_header("C. DATA INTEGRITY (MISSING FEE)")
        
        # Setup Ghost Code
        cpt = CodeSet.objects.get(code_set_name='CPT')
        Code.objects.get_or_create(code_set=cpt, code='XXXXX', defaults={'description': 'Ghost Code'})
        
        # Create Ghost Rule (Fresh)
        rule_ghost = PricingRule.objects.create(
            contract=contract, rule_type='BASE', 
            methodology_id=PricingRule.objects.first().methodology_id,
            base_fee_schedule=PricingRule.objects.first().base_fee_schedule,
            multiplier=Decimal('1.0'), 
            status='ACTIVE', 
            effective_start_date="2026-01-01"
        )
        PricingRuleCondition.objects.create(pricing_rule=rule_ghost, attribute_name='code', operator='EQ', attribute_value='XXXXX')
        rule_ghost.calculate_score()

        # Run Test
        req_ghost = {
            "provider_id": str(org.organization_id),
            "date_of_service": "2026-06-01",
            "lines": [{"line_id": 1, "code": "XXXXX", "billed": "100.00"}]
        }
        res_ghost = engine.calculate_claim(req_ghost)
        
        line_res = res_ghost['lines'][0]
        status = line_res.get('status', 'UNKNOWN')
        
        if status == "SUSPEND_DATA_ERROR":
            self.stdout.write(f"✅ PASS: Missing Fee Schedule -> {status}")
        else:
            self.stdout.write(f"❌ FAIL: Expected SUSPEND_DATA_ERROR, Got {status}")

    # --- Helpers ---
    def print_header(self, title):
        self.stdout.write(f"\n{title}")
        self.stdout.write("-" * 40)

    def verify(self, result, line_id, expected_str, desc):
        line = next(l for l in result['lines'] if l['line_id'] == line_id)
        val = line['final_allowed']
        exp = Decimal(expected_str)
        if val == exp:
            self.stdout.write(f"✅ PASS: {desc} -> ${val}")
        else:
            self.stdout.write(f"❌ FAIL: {desc} -> Exp ${exp}, Got ${val}")