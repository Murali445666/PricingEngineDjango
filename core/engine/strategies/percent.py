from decimal import Decimal, InvalidOperation
from .base import PricingMethodology
from ..types import PricingContext


def _to_decimal(v) -> Decimal:
    """Safely cast to Decimal for calculation; avoids string/Decimal type mismatch."""
    if v is None:
        return Decimal("0.00")
    if isinstance(v, Decimal):
        return v
    try:
        return Decimal(str(v))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0.00")


class PercentBilledMethod(PricingMethodology):
    def calculate(self, context: PricingContext) -> Decimal:
        factor = _to_decimal(context.percent_of_billed)

        # FIX: Stop Loss Logic
        if context.is_stop_loss:
            threshold = _to_decimal(context.stop_loss_threshold)

            # If bill is BELOW threshold, Stop Loss doesn't apply.
            billed = _to_decimal(getattr(context.input_data, "billed_amount", None))
            if billed < threshold:
                return Decimal("0.00")

            # If triggered, use the Stop Loss Multiplier
            factor = _to_decimal(context.stop_loss_multiplier)

        billed_amount = _to_decimal(getattr(context.input_data, "billed_amount", None))
        price = billed_amount * factor
        return self.apply_modifiers(context, price)