from decimal import Decimal
from .base import PricingMethodology
from ..types import PricingContext
from ..exceptions import PricingCalculationError

class AnesthesiaMethod(PricingMethodology):
    def calculate(self, context: PricingContext) -> Decimal:
        if context.base_rate is None:
             raise PricingCalculationError(f"Base units not found for {context.input_data.procedure_code}")

        time_units = Decimal(context.input_data.units) / Decimal("15.00")
        base_units = context.base_rate
        
        # NEW: Explicitly uses conversion_factor
        cf = context.conversion_factor or Decimal("0.00")
        
        price = (base_units + time_units) * cf
        context.methodology_events.append(
            f"ANESTHESIA base_units={base_units} time_units={time_units} cf={cf} raw={price}"
        )
        return self.apply_modifiers(context, price)