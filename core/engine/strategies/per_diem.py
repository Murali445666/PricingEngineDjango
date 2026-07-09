from decimal import Decimal
from .base import PricingMethodology
from ..types import PricingContext

class PerDiemMethod(PricingMethodology):
    def calculate(self, context: PricingContext) -> Decimal:
        # FIX: Look for flat_rate, NOT conversion_factor
        rate = context.flat_rate or Decimal("0.00")
        
        # Math: Rate ($1200) * Units (5 Days)
        price = rate * context.input_data.units
        context.methodology_events.append(
            f"PER_DIEM rate={rate} units={context.input_data.units} raw={price}"
        )

        return self.apply_modifiers(context, price)