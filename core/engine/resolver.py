from core.models import ProviderContract, PricingRule
from .types import PricingInput, PricingTrace

class StrictRuleResolver:
    def __init__(self, contract: ProviderContract):
        self.contract = contract

    def resolve(self, request: PricingInput, trace: PricingTrace) -> PricingRule:
        # 1. Fetch all enabled rules for this contract
        # FIX: Order by 'specificity_score' descending (Highest score = Best Match)
        rules = PricingRule.objects.filter(
            contract=self.contract,
            is_active=1
        ).order_by('-specificity_score').prefetch_related('conditions')

        trace.log("RESOLVER", f"Evaluating {len(rules)} rules for Contract {self.contract.contract_name}")

        # 2. Iterate and Match
        for rule in rules:
            if self._matches(rule, request, trace):
                trace.log("RESOLVER", f"✅ MATCH: {rule.rule_name} (Score: {rule.specificity_score})")
                return rule
            
        trace.log("RESOLVER", "❌ NO MATCH found.")
        return None

    def _matches(self, rule: PricingRule, request: PricingInput, trace: PricingTrace) -> bool:
        conditions = rule.conditions.all()
        
        if not conditions:
            return False 

        for condition in conditions:
            request_attr = condition.attribute_name
            
            # Map 'code' to 'procedure_code'
            if request_attr == 'code': 
                request_attr = 'procedure_code'

            request_value = getattr(request, request_attr, None)
            
            if request_value is None:
                return False
                
            if str(request_value) != str(condition.attribute_value):
                return False
        
        return True