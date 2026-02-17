from decimal import Decimal
from core.models import PricingRule, FeeScheduleRate, RefProcedureCode, RefModifier
from .types import PricingContext, PricingInput

class PricingDataLoader:
    def load_context(self, input_data: PricingInput, rule: PricingRule) -> PricingContext:
        # 1. Initialize Context with Explicit Metadata
        context = PricingContext(
            input_data=input_data,
            contract_id=str(rule.contract.pk),  # <--- Use .pk instead of .id
            rule_id=rule.rule_id,
            rule_name=rule.rule_name,
            methodology_code=rule.methodology_code
        )

        # 2. Populate Methodology-Specific Fields
        # We explicitly map the generic 'multiplier/flat_rate' columns to specific context fields
        
        if rule.methodology_code == 'RBRVS':
            context.conversion_factor = rule.multiplier # The Contract Multiplier (e.g. 1.5)
        
        elif rule.methodology_code == 'ANESTHESIA':
             context.conversion_factor = rule.multiplier

        elif rule.methodology_code in ['FLAT_RATE', 'PER_DIEM']:
            context.flat_rate = rule.flat_rate

        elif rule.methodology_code == 'PERCENT_BILLED':
            context.percent_of_billed = rule.multiplier
        
        elif rule.methodology_code == 'DRG':
            context.flat_rate = rule.flat_rate # This acts as the DRG Base Rate ($6000)
            # DRG also needs a weight, fetched below

        # 3. Populate Stop Loss Fields (If applicable)
        if rule.rule_type == 'STOP_LOSS':
            context.is_stop_loss = True
            context.stop_loss_threshold = rule.flat_rate # The Threshold ($10k)
            context.stop_loss_multiplier = rule.multiplier # The Rate (60%)

        # 4. Fetch External Data (Rates, Weights, Modifiers)
        
        # A. Fee Schedule Rate
        if rule.base_fee_schedule:
            try:
                rate_obj = FeeScheduleRate.objects.get(
                    fee_schedule=rule.base_fee_schedule,
                    code_id=input_data.procedure_code
                )
                context.base_rate = rate_obj.rate_amount
            except FeeScheduleRate.DoesNotExist:
                context.base_rate = None

        # B. DRG Weight
        if rule.methodology_code == 'DRG':
            try:
                ref = RefProcedureCode.objects.get(code_id=input_data.procedure_code)
                context.drg_weight = ref.work_rvu # We are using work_rvu column to store weights for now
            except RefProcedureCode.DoesNotExist:
                context.drg_weight = None

        # C. Modifiers
        if input_data.modifiers:
            mods = RefModifier.objects.filter(modifier_code__in=input_data.modifiers)
            for m in mods:
                context.modifier_adjustments[m.modifier_code] = m.percentage_adjustment

        return context