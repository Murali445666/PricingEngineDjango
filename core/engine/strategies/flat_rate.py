from decimal import Decimal
from .base import PricingMethodology
from ..types import PricingContext

class FlatRateMethod(PricingMethodology):
    def calculate(self, context: PricingContext) -> Decimal:
        # NEW: Explicitly uses flat_rate
        rate = context.flat_rate or Decimal("0.00")
        price = rate * context.input_data.units
        return self.apply_modifiers(context, price)