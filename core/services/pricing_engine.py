from decimal import Decimal
from datetime import datetime
from django.db.models import Q
from core.models import ProviderContract, PricingRule, FeeScheduleRate, PricingRuleCondition

class PricingTrace:
    def __init__(self):
        self.logs = []
        self.rule_applied = None
        self.final_price = Decimal('0.00')

    def log(self, step, message):
        self.logs.append({
            "step": step,
            "message": message,
            "timestamp": datetime.now().isoformat()
        })

    def to_dict(self):
        return {
            "allowed_amount": self.final_price,
            "rule_applied": self.rule_applied,
            "trace": self.logs
        }

class PricingEngine:
    
    # ---------------------------------------------------------
    # 1. Main Entry Point (With Error Handling)
    # ---------------------------------------------------------
    def calculate_price(self, claim_data):
        trace = PricingTrace()
        trace.log("INIT", f"Pricing Claim for Provider {claim_data.get('provider_id')}")

        try:
            # 1. PARSE CONTEXT
            provider_id = claim_data.get('provider_id')
            dos = claim_data.get('date_of_service') 
            
            # 2. FIND CONTRACT
            contract = self._find_active_contract(provider_id, dos, trace)
            if not contract:
                trace.log("STOP", "No Active Contract found for this Provider/DOS.")
                return trace.to_dict()

            # 3. FETCH RULES
            rules = PricingRule.objects.filter(
                contract=contract,
                status='ACTIVE',
                effective_start_date__lte=dos
            ).filter(
                Q(effective_end_date__gte=dos) | Q(effective_end_date__isnull=True)
            ).order_by('-specificity_score')

            if not rules.exists():
                trace.log("WARN", "No rules found.")
                # We don't stop here necessarily, but usually this means $0
                
            # 4. ACCUMULATOR LOGIC
            total_price = Decimal('0.00')
            base_rule_applied = False
            
            for rule in rules:
                if self._check_conditions(rule, claim_data, trace):
                    
                    if rule.rule_type == 'BASE':
                        if base_rule_applied:
                            trace.log("SKIP", f"Rule (Score: {rule.specificity_score}) skipped (Higher score Base already applied).")
                            continue
                        
                        price = self._calculate_math(rule, claim_data, trace)
                        total_price += price
                        base_rule_applied = True
                        trace.log("ACCUM", f"[BASE] Rule (Score: {rule.specificity_score}) Added: +${price}")
                        trace.rule_applied = str(rule.pricing_rule_id)

                    elif rule.rule_type == 'ADD_ON':
                        price = self._calculate_math(rule, claim_data, trace)
                        total_price += price
                        trace.log("ACCUM", f"[ADD-ON] Rule (Score: {rule.specificity_score}) Added: +${price}")

                    elif rule.rule_type == 'ADJUSTMENT':
                        factor = rule.multiplier
                        if factor:
                            old_price = total_price
                            total_price = total_price * factor
                            trace.log("ADJUST", f"Rule (Score: {rule.specificity_score}) Multiplier: {factor} (Price ${old_price} -> ${total_price})")

                    elif rule.rule_type == 'STOP_LOSS':
                        billed = Decimal(str(claim_data.get('billed_amount', '0')))
                        threshold = rule.threshold_amount or Decimal('0')
                        if billed > threshold:
                            excess = billed - threshold
                            outlier_payment = excess * rule.multiplier
                            total_price += outlier_payment
                            trace.log("OUTLIER", f"Billed ${billed} > Threshold ${threshold}. Paying excess: +${outlier_payment}")
                        else:
                            trace.log("SKIP", f"Stop Loss threshold (${threshold}) not met.")

            if total_price == 0 and not base_rule_applied:
                trace.log("STOP", "No applicable rules matched.")
            else:
                trace.final_price = total_price
                trace.log("SUCCESS", f"Final Stacked Price: ${total_price}")

            return trace.to_dict()

        except Exception as e:
            # THE SAFETY NET: Catch generic crashes
            trace.log("CRITICAL", f"Engine Crash: {str(e)}")
            return {
                "allowed_amount": Decimal('0.00'),
                "status": "ERROR",
                "error_message": str(e),
                "trace": trace.logs
            }

    # ---------------------------------------------------------
    # 2. Helper: Find Contract
    # ---------------------------------------------------------
    def _find_active_contract(self, provider_id, dos, trace):
        try:
            contract = ProviderContract.objects.get(
                provider_org__organization_id=provider_id,
                status='ACTIVE',
                effective_start_date__lte=dos
            )
            trace.log("CONTRACT", f"Using Contract: {contract.contract_name}")
            return contract
        except ProviderContract.DoesNotExist:
            return None
        except ProviderContract.MultipleObjectsReturned:
            trace.log("ERROR", "Multiple active contracts found. Ambiguous.")
            return None

    # ---------------------------------------------------------
    # 3. Helper: Check Conditions (With Network Status)
    # ---------------------------------------------------------
    def _check_conditions(self, rule, claim_data, trace):
        for condition in rule.conditions.all():
            attr = condition.attribute_name
            operator = condition.operator
            rule_val = condition.attribute_value
            
            # --- Network Status Default Logic ---
            if attr == 'network_status':
                claim_val = claim_data.get('network_status', 'INN')
            else:
                claim_val = claim_data.get(attr)
            
            if claim_val is None:
                # trace.log("SKIP", f"Rule (Score: {rule.specificity_score}): Claim missing attribute '{attr}'")
                return False

            match = False
            
            if operator == 'EQ':
                match = str(claim_val) == str(rule_val)
            elif operator == 'GT':
                try:
                    match = float(claim_val) > float(rule_val)
                except (ValueError, TypeError):
                    match = False
            elif operator == 'LT':
                try:
                    match = float(claim_val) < float(rule_val)
                except (ValueError, TypeError):
                    match = False
            elif operator == 'IN':
                match = str(claim_val) in rule_val.split(',')
                
            if not match:
                # trace.log("SKIP", f"Rule (Score: {rule.specificity_score}): Failed {attr} ({claim_val} {operator} {rule_val})")
                return False
                
        return True

    # ---------------------------------------------------------
    # 4. Helper: Math Calculation (DRG, RBRVS, Flat, %)
    # ---------------------------------------------------------
    def _calculate_math(self, rule, claim_data, trace):
        method_code = rule.methodology.methodology_code

        if method_code == 'FLAT_RATE':
            return rule.flat_rate

        elif method_code == 'PER_DIEM':
            units = int(claim_data.get('units', 1))
            return rule.flat_rate * units
            
        elif method_code == 'RBRVS':
            # Logic: Look up code in fee schedule, multiply by rule multiplier
            code = claim_data.get('code')
            if not rule.base_fee_schedule:
                trace.log("ERROR", "Rule missing base fee schedule")
                return Decimal('0.00')

            try:
                rate_obj = FeeScheduleRate.objects.get(
                    fee_schedule=rule.base_fee_schedule,
                    code__code=code
                )
                base_rate = rate_obj.rate_amount
                multiplier = rule.multiplier or Decimal('1.0')
                price = base_rate * multiplier
                trace.log("CALC", f"Strategy: RBRVS (${base_rate} * {multiplier}) = ${price}")
                return price
            except FeeScheduleRate.DoesNotExist:
                trace.log("ERROR", f"Code {code} not found in Fee Schedule")
                return Decimal('0.00')

        elif method_code == 'DRG':
            # Formula: Contract Base Rate * DRG Weight
            hospital_base_rate = rule.flat_rate 
            
            drg_code = claim_data.get('code')
            if not rule.base_fee_schedule:
                trace.log("ERROR", "Rule missing base fee schedule for DRG lookup.")
                return Decimal('0.00')

            try:
                rate_obj = FeeScheduleRate.objects.get(
                    fee_schedule=rule.base_fee_schedule,
                    code__code=drg_code
                )
                drg_weight = rate_obj.rate_amount
                
                price = hospital_base_rate * drg_weight
                trace.log("CALC", f"Strategy: DRG (Base ${hospital_base_rate} * Weight {drg_weight}) = ${price}")
                return price
            except FeeScheduleRate.DoesNotExist:
                trace.log("ERROR", f"DRG Weight for code {drg_code} not found in Fee Schedule.")
                return Decimal('0.00')

        elif method_code == 'PERCENT_BILLED':
            try:
                billed = Decimal(str(claim_data.get('billed_amount', '0.00')))
                factor = rule.multiplier
                price = billed * factor
                trace.log("CALC", f"Strategy: % Billed (${billed} * {factor}) = ${price}")
                return price
            except Exception as e:
                trace.log("ERROR", f"Failed to calculate % Billed: {str(e)}")
                return Decimal('0.00')

        return Decimal('0.00')