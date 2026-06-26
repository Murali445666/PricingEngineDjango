from decimal import Decimal
from .base import PricingMethodology
from ..types import PricingContext
from ..exceptions import PricingCalculationError


class RBRVSMethod(PricingMethodology):
    def calculate(self, context: PricingContext) -> Decimal:
        multiplier = context.conversion_factor or Decimal("1.0")
        units = context.input_data.units

        # Phase 1: when RefMpfsRvu + GPCI are present, use (work*gpci_work + pe*gpci_pe + mp*gpci_mp) * CF
        has_rvu = (
            context.work_rvu is not None
            and context.pe_rvu is not None
            and context.mp_rvu is not None
        )
        has_gpci = (
            context.gpci_work is not None
            and context.gpci_pe is not None
            and context.gpci_mp is not None
        )
        if has_rvu and has_gpci:
            base_price = (
                context.work_rvu * context.gpci_work
                + context.pe_rvu * context.gpci_pe
                + context.mp_rvu * context.gpci_mp
            ) * multiplier * units
            return self.apply_modifiers(context, base_price)

        # Fallback: use fee schedule base_rate when no RVU+GPCI
        if context.base_rate is None:
            raise PricingCalculationError(
                f"Rate not found for {context.input_data.procedure_code}"
            )
        base_price = context.base_rate * multiplier * units
        return self.apply_modifiers(context, base_price)