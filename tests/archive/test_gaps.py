from django.core.management.base import BaseCommand
from core.services.pricing_engine import PricingEngine
from core.models import ProviderOrganization, Code, FeeScheduleRate, PricingRule, PricingRuleCondition, CodeSet, FeeSchedule, PricingMethodology
from decimal import Decimal

class Command(BaseCommand):
    help = 'Tests Logic Gaps: Units, Modifier Stacking, Components, MPPR Compounding, Add-On Dependency'

    def handle(self, *args, **kwargs):
        self.stdout.write("--- 🧪 TESTING LOGIC GAPS 🧪 ---")
        
        try:
            org = ProviderOrganization.objects.get(name='Allegheny Health Network')
        except:
            self.stdout.write("❌ Seed data missing. Run 'python manage.py seed_data' first.")
            return

        engine = PricingEngine()

        # ---------------------------------------------------------
        # SCENARIO 1: UNITS LOGIC
        # ---------------------------------------------------------
        self.print_header("1. UNITS MULTIPLICATION")
        req_units = {
            "provider_id": str(org.organization_id),
            "date_of_service": "2026-06-01",
            "lines": [{"line_id": 1, "code": "99213", "units": 3, "billed": "500.00"}]
        }
        res_units = engine.calculate_claim(req_units)
        self.verify(res_units, 1, "382.50", "3 Units of 99213")

        # ---------------------------------------------------------
        # SCENARIO 2: COMPONENT BILLING
        # ---------------------------------------------------------
        self.print_header("2. COMPONENT BILLING (-26)")
        req_26 = {
            "provider_id": str(org.organization_id),
            "date_of_service": "2026-06-01",
            "lines": [{"line_id": 1, "code": "73030", "modifiers": ["26"], "billed": "100.00"}]
        }
        res_26 = engine.calculate_claim(req_26)
        self.verify(res_26, 1, "24.00", "X-Ray Professional Component (26)")

        # ---------------------------------------------------------
        # SCENARIO 3: MODIFIER STACKING
        # ---------------------------------------------------------
        self.print_header("3. MODIFIER STACKING (50 + 80)")
        req_stack = {
            "provider_id": str(org.organization_id),
            "date_of_service": "2026-06-01",
            "lines": [{"line_id": 1, "code": "29806", "modifiers": ["50", "80"], "billed": "5000.00"}]
        }
        res_stack = engine.calculate_claim(req_stack)
        self.verify(res_stack, 1, "450.00", "Bilateral Assistant Surgeon")

        # ---------------------------------------------------------
        # SCENARIO 4: BILATERAL + MPPR COMPOUNDING
        # ---------------------------------------------------------
        self.print_header("4. BILATERAL + MPPR COMPOUNDING")
        
        cpt = CodeSet.objects.get(code_set_name='CPT')
        fs = FeeSchedule.objects.get(name='Master Fee Schedule 2026')
        contract_obj = PricingRule.objects.first().contract
        rbrvs_method = PricingMethodology.objects.get(methodology_code='RBRVS')

        # 1. Create Spinal Code & Rate
        c_spine, _ = Code.objects.get_or_create(code_set=cpt, code='22551', defaults={'description': 'Spinal Fusion'})
        FeeScheduleRate.objects.update_or_create(fee_schedule=fs, code=c_spine, defaults={'rate_amount': Decimal('3333.33')})
        
        # 2. Check if Rule Exists (Prevent Crash)
        spine_rule_exists = PricingRuleCondition.objects.filter(
            pricing_rule__contract=contract_obj,
            attribute_name='code',
            attribute_value='22551'
        ).exists()

        if not spine_rule_exists:
            rule_spine = PricingRule.objects.create(
                contract=contract_obj,
                rule_type='BASE',
                methodology=rbrvs_method,
                base_fee_schedule=fs,
                multiplier=Decimal('1.50'),
                status='ACTIVE',
                effective_start_date="2026-01-01"
            )
            PricingRuleCondition.objects.create(pricing_rule=rule_spine, attribute_name='code', operator='EQ', attribute_value='22551')
            PricingRuleCondition.objects.create(pricing_rule=rule_spine, attribute_name='network_status', operator='EQ', attribute_value='INN')
            rule_spine.calculate_score()
            self.stdout.write("   > Created missing rule for 22551")
        else:
            self.stdout.write("   > Rule for 22551 already exists")

        # 3. Execute Request
        req_compound = {
            "provider_id": str(org.organization_id),
            "date_of_service": "2026-06-01",
            "lines": [
                # Line 1: $3333.33 * 1.50 = ~$5000 (Primary)
                {"line_id": 1, "code": "22551", "billed": "10000.00"}, 
                # Line 2: $1000 * 1.5 (Contract) * 1.5 (Bi) = $2250 -> MPPR 50% = $1125
                {"line_id": 2, "code": "29881", "modifiers": ["50"], "billed": "5000.00"}
            ]
        }
        res_compound = engine.calculate_claim(req_compound)
        self.verify(res_compound, 2, "1125.00", "Bilateral ($2250) reduced by MPPR (50%)")

        # ---------------------------------------------------------
        # SCENARIO 5: ADD-ON CODE DEPENDENCY
        # ---------------------------------------------------------
        self.print_header("5. ADD-ON DEPENDENCY CHECK")
        
        # We bill Add-on (+99100) WITHOUT its parent (00100).
        # Should be DENIED ($0.00).
        req_addon = {
            "provider_id": str(org.organization_id),
            "date_of_service": "2026-06-01",
            "lines": [
                {"line_id": 1, "code": "+99100", "billed": "100.00"}
            ]
        }
        res_addon = engine.calculate_claim(req_addon)
        
        # Check if denied
        line = res_addon['lines'][0]
        if line['final_allowed'] == 0:
            self.stdout.write(f"✅ PASS: Orphan Code Denied ($0.00)")
            if line['trace']:
                self.stdout.write(f"   Reason: {line['trace'][0]['message']}")
        else:
            self.stdout.write(f"❌ FAIL: Orphan Code Paid ${line['final_allowed']}")


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
            for log in line['trace']:
                self.stdout.write(f"   > {log['message']}")