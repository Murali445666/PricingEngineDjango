from decimal import Decimal
from .base import PricingMethodology
from ..types import PricingContext

class PercentBilledMethod(PricingMethodology):
    def calculate(self, context: PricingContext) -> Decimal:
        factor = context.percent_of_billed or Decimal("0.00")

        # FIX: Stop Loss Logic
        if context.is_stop_loss:
            threshold = context.stop_loss_threshold or Decimal("0.00")
            
            # If bill is BELOW threshold, Stop Loss doesn't apply.
            # In a real engine, this might fall back to another rule, 
            # but for this specific rule execution, the price is 0 (Denied/Not Applicable).
            if context.input_data.billed_amount < threshold:
                return Decimal("0.00")

            # If triggered, use the Stop Loss Multiplier
            factor = context.stop_loss_multiplier or Decimal("0.00")
            
        price = context.input_data.billed_amount * factor
        return self.apply_modifiers(context, price)