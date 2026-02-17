from decimal import Decimal
from .base import PricingMethodology
from ..types import PricingContext
from ..exceptions import PricingCalculationError

class DRGMethod(PricingMethodology):
    def calculate(self, context: PricingContext) -> Decimal:
        # NEW: Explicitly checks drg_weight
        if context.drg_weight is None:
             raise PricingCalculationError(f"DRG Weight not found")
        
        # NEW: Explicitly uses flat_rate as the Base Rate
        base_rate = context.flat_rate or Decimal("0.00")
        return base_rate * context.drg_weight