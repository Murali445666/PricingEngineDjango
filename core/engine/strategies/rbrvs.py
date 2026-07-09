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
            context.methodology_events.append(
                f"RBRVS base via RVU×GPCI cf={multiplier} units={units} "
                f"work={context.work_rvu} pe={context.pe_rvu} mp={context.mp_rvu} raw={base_price}"
            )
            return self.apply_modifiers(context, base_price)

        # Fallback: use fee schedule base_rate when no RVU+GPCI
        if context.base_rate is None:
            raise PricingCalculationError(
                f"Rate not found for {context.input_data.procedure_code}"
            )
        base_price = context.base_rate * multiplier * units
        skip_parts = []
        if not has_rvu:
            skip_parts.append("RVU missing")
        if not has_gpci:
            skip_parts.append("GPCI null")
        skip_reason = ", ".join(skip_parts) if skip_parts else "RVU×GPCI unavailable"
        context.methodology_events.append(
            f"RBRVS base via FEE_SCHEDULE base_rate={context.base_rate} cf={multiplier} "
            f"units={units} raw={base_price} (RVU×GPCI skipped: {skip_reason})"
        )
        return self.apply_modifiers(context, base_price)