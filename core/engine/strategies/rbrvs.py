from decimal import Decimal
from .base import PricingMethodology
from ..types import PricingContext
from ..exceptions import PricingCalculationError

class RBRVSMethod(PricingMethodology):
    def calculate(self, context: PricingContext) -> Decimal:
        if context.base_rate is None:
            raise PricingCalculationError(f"Rate not found for {context.input_data.procedure_code}")
        
        # NEW: Explicitly uses conversion_factor
        multiplier = context.conversion_factor or Decimal("1.0")
        base_price = context.base_rate * multiplier * context.input_data.units
        
        return self.apply_modifiers(context, base_price)