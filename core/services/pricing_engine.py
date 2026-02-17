from decimal import Decimal
from datetime import datetime
from django.db.models import Q
from core.models import ProviderContract, PricingRule, FeeScheduleRate, PricingRuleCondition

class PricingTrace:
    def __init__(self):
        self.logs = []
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
            "trace": self.logs
        }

class PricingEngine:
    
    # ---------------------------------------------------------
    # 1. MAIN ENTRY POINT: CALCULATE CLAIM (Multi-Line)
    # ---------------------------------------------------------
    def calculate_claim(self, claim_request):
        """
        Main orchestration method. 
        Expects a dict with 'provider_id', 'date_of_service', 'lines', and optional 'plan_id'.
        """
        provider_id = claim_request.get('provider_id')
        dos = claim_request.get('date_of_service')
        network_status = claim_request.get('network_status', 'INN')
        plan_id = claim_request.get('plan_id') # New: Support for Plan Overrides

        # A. Shared Contract Lookup
        temp_trace = PricingTrace()
        contract = self._find_active_contract(provider_id, dos, temp_trace)
        
        response = {
            "claim_total": Decimal('0.00'),
            "status": "PRICED",
            "contract_used": contract.contract_name if contract else "NONE",
            "lines": []
        }

        if not contract:
            response["status"] = "REJECTED_NO_CONTRACT"
            return response

        # B. PRE-FLIGHT CHECK: Add-on Dependencies
        # Rule: Code X requires Code Y to be present on the claim
        claim_codes = set(line.get('code') for line in claim_request.get('lines', []))
        dependency_map = {
            '+99100': ['00100', '00102'], # Anesthesia Add-on
            '+90785': ['90832', '90834']  # Psych Add-on
        }

        # C. PRICE EACH LINE (Gross Amount)
        priced_lines = []
        for line in claim_request.get('lines', []):
            line_code = line.get('code')
            
            # 1. Validation Check
            denial_reason = None
            if line_code in dependency_map:
                required_parents = dependency_map[line_code]
                if not any(parent in claim_codes for parent in required_parents):
                    denial_reason = f"DENIED: Add-on code {line_code} requires primary {required_parents}"

            # 2. Build Context
            line_context = {
                "provider_id": provider_id,
                "date_of_service": dos,
                "network_status": network_status,
                "plan_id": plan_id,
                **line
            }
            
            # 3. Calculate Price (or Deny)
            if denial_reason:
                line_result = {
                    "allowed_amount": Decimal('0.00'),
                    "status": "DENIED_DEPENDENCY",
                    "methodology": "DENIED",
                    "trace": [{"step": "DENY", "message": denial_reason, "timestamp": datetime.now().isoformat()}]
                }
            else:
                line_result = self._calculate_single_line(contract, line_context)
            
            # 4. Store for MPPR Processing
            priced_lines.append({
                "line_id": line.get("line_id"),
                "code": line_code,
                "gross_allowed": line_result['allowed_amount'],
                "final_allowed": line_result['allowed_amount'], # Default to gross
                "status": line_result.get('status', 'PAYABLE'),
                "methodology": line_result.get('methodology'),
                "trace": line_result['trace'],
                # Only RBRVS logic usually triggers MPPR
                "is_mppr_eligible": line_result.get('methodology') == 'RBRVS' and line_result.get('status') == 'PAYABLE'
            })

        # D. APPLY MPPR (Multiple Procedure Payment Reduction)
        # Sort eligible lines by Gross Amount (Highest -> Lowest)
        mppr_candidates = [l for l in priced_lines if l['is_mppr_eligible']]
        mppr_candidates.sort(key=lambda x: x['gross_allowed'], reverse=True)
        
        for index, candidate in enumerate(mppr_candidates):
            if index > 0:
                # 2nd, 3rd, etc. lines get 50% reduction
                original = candidate['gross_allowed']
                reduced = original * Decimal('0.50')
                candidate['final_allowed'] = reduced
                candidate['trace'].append({
                    "step": "MPPR", 
                    "message": f"MPPR Applied: Rank {index+1}. Reduced {original} -> {reduced} (50%)",
                    "timestamp": datetime.now().isoformat()
                })

        # E. FINALIZE TOTALS
        total = Decimal('0.00')
        for pl in priced_lines:
            if pl['status'] == 'PAYABLE':
                total += pl['final_allowed']
            response['lines'].append(pl)
        
        response['claim_total'] = total
        return response

    # ---------------------------------------------------------
    # 2. HELPER: PRICE SINGLE LINE (With Error Handling)
    # ---------------------------------------------------------
    def _calculate_single_line(self, contract, line_data):
        trace = PricingTrace()
        trace.log("INIT", f"Pricing Line Code: {line_data.get('code')}")

        result_status = "DENIED_NO_RULE" # Default
        total_price = Decimal('0.00')
        primary_methodology = None

        try:
            dos = line_data.get('date_of_service')
            billed_units = int(line_data.get('units', 1))
            
            # Fetch Rules
            rules = PricingRule.objects.filter(
                contract=contract,
                status='ACTIVE',
                effective_start_date__lte=dos
            ).filter(
                Q(effective_end_date__gte=dos) | Q(effective_end_date__isnull=True)
            ).order_by('-specificity_score')

            base_rule_applied = False
            
            for rule in rules:
                if self._check_conditions(rule, line_data, trace):
                    
                    if rule.rule_type == 'BASE':
                        if base_rule_applied: continue
                        
                        try:
                            price = self._calculate_math(rule, line_data, trace)
                            total_price += price
                            base_rule_applied = True
                            primary_methodology = rule.methodology.methodology_code
                            result_status = "PAYABLE"
                            trace.log("ACCUM", f"[BASE] Rule (Score: {rule.specificity_score}): +${price}")
                        except ValueError as e:
                            # Catch data integrity errors (Section C)
                            trace.log("ERROR", f"Calculation Failed: {str(e)}")
                            return {
                                "allowed_amount": Decimal('0.00'),
                                "status": "SUSPEND_DATA_ERROR",
                                "methodology": "ERROR",
                                "trace": trace.logs
                            }

                    elif rule.rule_type == 'STOP_LOSS':
                        # Stop Loss logic (Simplified for this file)
                        billed = Decimal(str(line_data.get('billed_amount', '0')))
                        threshold = rule.threshold_amount or Decimal('0')
                        if billed > threshold:
                            excess = billed - threshold
                            pay = excess * rule.multiplier
                            total_price += pay
                            trace.log("OUTLIER", f"Stop Loss Triggered: +${pay}")

            # Apply Modifiers (Stacking) & Units - ONLY if Payable
            if result_status == "PAYABLE":
                modifiers = line_data.get('modifiers', [])
                if modifiers:
                    total_price = self._apply_modifier_stack(contract, modifiers, total_price, dos, trace)

                if primary_methodology in ['RBRVS', 'FLAT_RATE', 'FEE_SCHEDULE']:
                    if billed_units > 1:
                        old = total_price
                        total_price = total_price * billed_units
                        trace.log("UNITS", f"Applied {billed_units} Units: ${old} -> ${total_price}")

            return {
                "allowed_amount": total_price,
                "status": result_status,
                "methodology": primary_methodology,
                "trace": trace.logs
            }

        except Exception as e:
            trace.log("CRITICAL", f"Engine Crash: {str(e)}")
            return {
                "allowed_amount": Decimal('0.00'), 
                "status": "CRITICAL_ERROR", 
                "trace": trace.logs
            }

    # ---------------------------------------------------------
    # 3. HELPER: MODIFIER STACKING
    # ---------------------------------------------------------
    def _apply_modifier_stack(self, contract, modifiers, current_price, dos, trace):
        adj_rules = PricingRule.objects.filter(
            contract=contract,
            rule_type='ADJUSTMENT',
            status='ACTIVE',
            effective_start_date__lte=dos
        )
        for mod in modifiers:
            matched_rule = None
            for rule in adj_rules:
                # Manual condition check for modifier
                for cond in rule.conditions.all():
                    if cond.attribute_name == 'modifier' and cond.attribute_value == mod:
                        matched_rule = rule
                        break
                if matched_rule: break
            
            if matched_rule:
                factor = matched_rule.multiplier
                old = current_price
                current_price = current_price * factor
                trace.log("ADJUST", f"Modifier {mod}: x{factor} (${old} -> ${current_price})")
            else:
                trace.log("WARN", f"Modifier {mod} not found in contract.")
        return current_price

    # ---------------------------------------------------------
    # 4. HELPER: CHECK CONDITIONS (Now supports Plan ID)
    # ---------------------------------------------------------
    def _check_conditions(self, rule, claim_data, trace):
        for condition in rule.conditions.all():
            attr = condition.attribute_name
            operator = condition.operator
            rule_val = condition.attribute_value
            
            # Support for attributes not directly on the line (like network_status, plan_id)
            if attr in ['network_status', 'plan_id']:
                claim_val = claim_data.get(attr)
                # If claim doesn't have plan_id but rule requires it -> No Match
                if claim_val is None and attr == 'plan_id': return False 
                if claim_val is None: claim_val = 'INN' # Default network
            else:
                claim_val = claim_data.get(attr)
            
            if claim_val is None: return False

            match = False
            if operator == 'EQ': match = str(claim_val) == str(rule_val)
            elif operator == 'GT':
                try: match = float(claim_val) > float(rule_val)
                except: match = False
            elif operator == 'LT':
                try: match = float(claim_val) < float(rule_val)
                except: match = False
            
            if not match: return False
        return True

    # ---------------------------------------------------------
    # 5. HELPER: MATH CALCULATION (With Data Integrity Check)
    # ---------------------------------------------------------
    def _calculate_math(self, rule, claim_data, trace):
        method_code = rule.methodology.methodology_code

        if method_code == 'RBRVS':
            code = claim_data.get('code')
            if not rule.base_fee_schedule:
                raise ValueError("Rule configuration error: Missing base fee schedule")

            try:
                rate_obj = FeeScheduleRate.objects.get(
                    fee_schedule=rule.base_fee_schedule,
                    code__code=code
                )
                return rate_obj.rate_amount * (rule.multiplier or Decimal('1.0'))
            except FeeScheduleRate.DoesNotExist:
                # This raises the error that triggers "SUSPEND_DATA_ERROR"
                raise ValueError(f"Fee Rate missing for code {code}")

        elif method_code == 'FLAT_RATE':
            return rule.flat_rate

        elif method_code == 'PERCENT_BILLED':
            billed = Decimal(str(claim_data.get('billed_amount', '0.00')))
            return billed * rule.multiplier
            
        elif method_code == 'DRG':
             code = claim_data.get('code')
             try:
                 rate_obj = FeeScheduleRate.objects.get(fee_schedule=rule.base_fee_schedule, code__code=code)
                 return rule.flat_rate * rate_obj.rate_amount # Base * Weight
             except: return Decimal('0.00')
             
        elif method_code == 'PER_DIEM':
             return rule.flat_rate * int(claim_data.get('units', 1))

        return Decimal('0.00')

    def _find_active_contract(self, provider_id, dos, trace):
        try:
            return ProviderContract.objects.get(
                provider_org__organization_id=provider_id,
                status='ACTIVE',
                effective_start_date__lte=dos
            )
        except:
            return None