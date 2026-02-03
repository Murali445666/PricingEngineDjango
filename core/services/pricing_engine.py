from decimal import Decimal
from datetime import date
from django.db.models import Q
from core.models import ProviderContract, PricingRule, FeeScheduleRate

class PricingTrace:
    def __init__(self):
        self.logs = []
        self.final_price = Decimal('0.00')
        self.rule_applied = None # Stores the ID of the winning Base Rule

    def log(self, step, message):
        """
        Records a step in the pricing logic.
        """
        self.logs.append({
            "step": step,
            "message": message
        })

    def to_dict(self):
        """
        Formats the object for API/Test consumption.
        Keys match what test_pricing.py expects.
        """
        return {
            "allowed_amount": self.final_price,
            "rule_id": self.rule_applied, # <--- Matches test script key
            "trace": self.logs            # <--- Matches test script key
        }

class PricingEngine:
    """
    Requirement 4.1: Stateless Execution Interface
    Accepts context (claim) + As-Of Date.
    """
    
    def calculate_price(self, claim_data):
        trace = PricingTrace()
        trace.log("INIT", f"Pricing Claim for Provider {claim_data.get('provider_id')}")

        # 1. PARSE CONTEXT
        provider_id = claim_data.get('provider_id')
        dos = claim_data.get('date_of_service') 
        
        # 2. FIND CONTRACT
        contract = self._find_active_contract(provider_id, dos, trace)
        if not contract:
            trace.log("STOP", "No Active Contract found.")
            return trace.to_dict()

        # 3. FETCH RULES (SORTED BY SPECIFICITY SCORE DESCENDING)
        rules = PricingRule.objects.filter(
            contract=contract,
            status='ACTIVE',
            effective_start_date__lte=dos
        ).filter(
            Q(effective_end_date__gte=dos) | Q(effective_end_date__isnull=True)
        ).order_by('-specificity_score') # <--- CHANGED: High score wins!

        if not rules.exists():
            trace.log("WARN", "No rules found.")
            return trace.to_dict()

        # 4. ACCUMULATOR LOGIC
        total_price = Decimal('0.00')
        base_rule_applied = False
        
        for rule in rules:
            # Check conditions
            if self._check_conditions(rule, claim_data, trace):
                
                # CASE A: BASE RULE (Exclusive)
                if rule.rule_type == 'BASE':
                    if base_rule_applied:
                        # We found a Base rule with a higher score already. Skip this generic one.
                        trace.log("SKIP", f"Rule (Score: {rule.specificity_score}) skipped (Higher score Base already applied).")
                        continue
                    
                    price = self._calculate_math(rule, claim_data, trace)
                    total_price += price
                    base_rule_applied = True
                    # CHANGED: Log the Score, not priority
                    trace.log("ACCUM", f"[BASE] Rule (Score: {rule.specificity_score}) Added: +${price}")
                    trace.rule_applied = str(rule.pricing_rule_id)

                # CASE B: ADD-ON RULE (Cumulative)
                elif rule.rule_type == 'ADD_ON':
                    price = self._calculate_math(rule, claim_data, trace)
                    total_price += price
                    trace.log("ACCUM", f"[ADD-ON] Rule (Score: {rule.specificity_score}) Added: +${price}")

                # CASE C: ADJUSTMENT (Modifiers)
                elif rule.rule_type == 'ADJUSTMENT':
                    # Multiplier is stored in rule.multiplier (e.g., 1.50)
                    factor = rule.multiplier
                    if factor:
                        old_price = total_price
                        total_price = total_price * factor
                        trace.log("ADJUST", f"Rule (Score: {rule.specificity_score}) Multiplier: {factor} (Price ${old_price} -> ${total_price})")

                # CASE D: STOP LOSS (Outlier)
                elif rule.rule_type == 'STOP_LOSS':
                    billed = Decimal(str(claim_data.get('billed_amount', '0')))
                    threshold = rule.threshold_amount or Decimal('0')
                    
                    if billed > threshold:
                        excess = billed - threshold
                        percentage = rule.multiplier # e.g., 0.80 (80% of excess)
                        outlier_payment = excess * percentage
                        
                        total_price += outlier_payment
                        trace.log("OUTLIER", f"Billed ${billed} > Threshold ${threshold}. Paying 80% of excess (${excess}) = +${outlier_payment}")
                    else:
                         trace.log("SKIP", f"Stop Loss threshold (${threshold}) not met.")

                # CASE E: CAP (Limit)
                elif rule.rule_type == 'CAP':
                    limit = rule.flat_rate
                    if total_price > limit:
                        diff = total_price - limit
                        total_price = limit
                        trace.log("LIMIT", f"Price capped at ${limit} (Reduced by ${diff})")

        # FINAL CHECK
        if total_price == 0 and not base_rule_applied:
            trace.log("STOP", "No applicable rules matched.")
        else:
            trace.final_price = total_price
            trace.log("SUCCESS", f"Final Stacked Price: ${total_price}")

        return trace.to_dict()

    def _find_active_contract(self, provider_id, dos, trace):
        """
        Locates the single valid contract header for the DOS.
        """
        # In a real app, handle multiple contracts. For now, grab the first active one.
        contract = ProviderContract.objects.filter(
            provider_org__organization_id=provider_id,
            status='ACTIVE',
            effective_start_date__lte=dos
        ).first()
        
        if contract:
            trace.log("CONTRACT", f"Using Contract: {contract.contract_name}")
        return contract

    def _check_conditions(self, rule, claim_data, trace):
        """
        Req 1.5: Condition Evaluation Logic
        """
        for condition in rule.conditions.all():
            attr = condition.attribute_name
            operator = condition.operator
            rule_val = condition.attribute_value
            
            # Get value from claim (default to None if missing)
            claim_val = claim_data.get(attr)
            
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
                # FIX: Replaced 'rule_priority' with 'specificity_score'
                trace.log("SKIP", f"Rule (Score: {rule.specificity_score}): Failed {attr} ({claim_val} {operator} {rule_val})")
                return False
                
        return True

    def _calculate_math(self, rule, claim_data, trace):
        # ... (Previous variables) ...
        method_code = rule.methodology.methodology_code

        # --- EXISTING LOGIC ---
        if method_code == 'FLAT_RATE':
            return rule.flat_rate

        elif method_code == 'PER_DIEM':
            units = int(claim_data.get('units', 1))
            return rule.flat_rate * units
            
        elif method_code == 'RBRVS':
            # ... (Existing RBRVS logic) ...
            code = claim_data.get('code')
            # ... (lookup code) ...
            # ... (return rate * multiplier) ...
            # (Copy your existing RBRVS block here if not already distinct)
            # For brevity, I assume RBRVS is already there.

        # --- NEW DRG LOGIC ---
        elif method_code == 'DRG':
            # Formula: Contract Base Rate * DRG Weight
            hospital_base_rate = rule.flat_rate # Defined in Rule ($10,000)
            
            # Fetch Weight from Fee Schedule
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

        return Decimal('0.00')