from decimal import Decimal
from django.test import TestCase
from core.models import (
    ProviderContract, 
    ProviderOrganization,
    PayerNetwork,
    FeeSchedule, 
    FeeScheduleRate, 
    PricingRule, 
    PricingRuleCondition, 
    RefProcedureCode, 
    RefModifier
)
from core.engine.orchestrator import PricingEngine
from core.engine.types import PricingInput

class MatrixPricingEngine(TestCase):
    def setUp(self):
        self.real_engine = PricingEngine()
        self.engine = self 
        self.setup_matrix_data()

    def calculate_line(self, code, billed, modifiers=None, units=1):
        inp = PricingInput(
            procedure_code=code,
            billed_amount=billed,
            modifiers=modifiers or [],
            units=units
        )
        result = self.real_engine.calculate_line(self.contract, inp)
        return result.allowed_amount, result.methodology

    def setup_matrix_data(self):
        print("🏗️  Building Full Matrix Test Data...")

        # 1. Parents
        payer_org = ProviderOrganization.objects.create(
            organization_id="PAYER-MATRIX", name="Matrix Health", tax_id="99-9999999"
        )
        provider_org = ProviderOrganization.objects.create(
            organization_id="PROV-GEN-HOSP", name="General Hospital", tax_id="11-1111111"
        )
        network = PayerNetwork.objects.create(
            network_id="NET-COMMERCIAL", network_name="Matrix Commercial", payer_org=payer_org
        )

        # 2. Contract
        self.contract = ProviderContract.objects.create(
            contract_name="Matrix 2025", legacy_contract_number="CONT-MATRIX-2026",
            status="ACTIVE", effective_start_date="2025-01-01",
            provider_org=provider_org, network=network
        )

        # 3. Fee Schedule
        fs = FeeSchedule.objects.create(name="Matrix 2025 Standard", effective_date="2025-01-01")

        # 4. Codes & Rates
        data_map = {
            '99213': ('100.00', 'Office Visit', '0.97'),
            '73030': ('75.00', 'X-Ray', '0.50'),
            '29806': ('1000.00', 'Shoulder Arthroscopy', '10.50'),
            '99100': ('100.00', 'Anesthesia Add-on', '0.00'),
            '00100': ('150.00', 'Anesthesia Head', '0.00'),
            '0120':  ('1200.00', 'Per Diem Bed', '0.00'), 
            'DRG-470': ('15000.00', 'Hip Replacement', '2.5'),
            'DRG-194': ('6000.00', 'Pneumonia', '0.8'),
        }
        for code, (rate, desc, rvu) in data_map.items():
            RefProcedureCode.objects.create(code_id=code, description=desc, work_rvu=Decimal(rvu))
            FeeScheduleRate.objects.create(fee_schedule=fs, code_id=code, rate_amount=Decimal(rate))
            
        # FIX: Use whole numbers (40.00 = 40%), not decimals (0.40)
        RefModifier.objects.create(modifier_code='26', description='Professional Component', percentage_adjustment=Decimal('40.00'))
        RefModifier.objects.create(modifier_code='50', description='Bilateral Procedure', percentage_adjustment=Decimal('150.00'))

        # 5. Rules & Conditions (USING specificity_score)
        
        # A. RBRVS (Specificity 10)
        r1 = PricingRule.objects.create(
            contract=self.contract, rule_name="RBRVS Standard", specificity_score=10, 
            methodology_code="RBRVS", base_fee_schedule=fs, multiplier=Decimal("1.50"),
            status=PricingRule.RuleStatus.ACTIVE
        )
        PricingRuleCondition.objects.create(pricing_rule=r1, attribute_name="procedure_code", operator="EQ", attribute_value="99213")

        # B. Flat Rate (Specificity 20)
        r2 = PricingRule.objects.create(
            contract=self.contract, rule_name="Radiology Flat", specificity_score=20, 
            methodology_code="FLAT_RATE", flat_rate=Decimal("75.00"),
            status=PricingRule.RuleStatus.ACTIVE
        )
        PricingRuleCondition.objects.create(pricing_rule=r2, attribute_name="procedure_code", operator="EQ", attribute_value="73030")
        
        # C. Percent Billed (Specificity 30)
        r3 = PricingRule.objects.create(
            contract=self.contract, rule_name="Surgery Percent", specificity_score=30, 
            methodology_code="PERCENT_BILLED", multiplier=Decimal("0.50"),
            status=PricingRule.RuleStatus.ACTIVE
        )
        PricingRuleCondition.objects.create(pricing_rule=r3, attribute_name="procedure_code", operator="EQ", attribute_value="29806")

        # D. Stop Loss (Specificity 99 - Highest, so it triggers first if conditions match)
        r4 = PricingRule.objects.create(
            contract=self.contract, rule_name="Stop Loss Protection", specificity_score=99,
            rule_type="STOP_LOSS", methodology_code="PERCENT_BILLED",
            flat_rate=Decimal("10000.00"), multiplier=Decimal("0.60"),
            status=PricingRule.RuleStatus.ACTIVE
        )
        PricingRuleCondition.objects.create(pricing_rule=r4, attribute_name="procedure_code", operator="EQ", attribute_value="SL-TRIG")

        # E. DRG (Specificity 40)
        r5 = PricingRule.objects.create(
            contract=self.contract, rule_name="Inpatient DRG", specificity_score=40,
            methodology_code="DRG", flat_rate=Decimal("6000.00"),
            status=PricingRule.RuleStatus.ACTIVE
        )
        PricingRuleCondition.objects.create(pricing_rule=r5, attribute_name="procedure_code", operator="EQ", attribute_value="DRG-470")
        
        r5b = PricingRule.objects.create(
             contract=self.contract, rule_name="Inpatient DRG 2", specificity_score=40,
             methodology_code="DRG", flat_rate=Decimal("6000.00"),
             status=PricingRule.RuleStatus.ACTIVE
        )
        PricingRuleCondition.objects.create(pricing_rule=r5b, attribute_name="procedure_code", operator="EQ", attribute_value="DRG-194")

        # F. Per Diem (Specificity 50)
        r6 = PricingRule.objects.create(
            contract=self.contract, rule_name="Per Diem Bed", specificity_score=50,
            methodology_code="PER_DIEM", flat_rate=Decimal("1200.00"),
            status=PricingRule.RuleStatus.ACTIVE
        )
        PricingRuleCondition.objects.create(pricing_rule=r6, attribute_name="procedure_code", operator="EQ", attribute_value="0120")

        # G. Anesthesia (Specificity 60)
        r7 = PricingRule.objects.create(
            contract=self.contract, rule_name="Anesthesia Group", specificity_score=60,
            methodology_code="ANESTHESIA", base_fee_schedule=fs, multiplier=Decimal("45.00"),
            status=PricingRule.RuleStatus.ACTIVE
        )
        PricingRuleCondition.objects.create(pricing_rule=r7, attribute_name="procedure_code", operator="EQ", attribute_value="00100")

        # H. Dependency (Specificity 15)
        r8 = PricingRule.objects.create(
             contract=self.contract, rule_name="AddOn Test", specificity_score=15,
             methodology_code="FLAT_RATE", flat_rate=Decimal("75.00"),
             status=PricingRule.RuleStatus.ACTIVE
        )
        PricingRuleCondition.objects.create(pricing_rule=r8, attribute_name="procedure_code", operator="EQ", attribute_value="99100")

        print("✅ Matrix Data Seeded.")