"""
APC (Ambulatory Payment Classification) pricing strategy.
Uses RefApc: allowed_amount = relative_weight * conversion_factor (from ContractMethodology).
"""
from datetime import date
from decimal import Decimal

from core.models import RefApc
from .base import PricingMethodology
from ..types import PricingContext
from ..exceptions import NoApcFoundError


class ApcPricingStrategy(PricingMethodology):
    """OPPS/APC methodology: look up RefApc by procedure code (as apc_code) and service year."""

    def calculate(self, context: PricingContext) -> Decimal:
        procedure_code = (context.input_data.procedure_code or "").strip()
        service_date = context.input_data.service_date or date.today()
        year = service_date.year

        apc = (
            RefApc.objects.filter(apc_code=procedure_code, year=year).first()
            or RefApc.objects.filter(apc_code=procedure_code).first()
        )
        if apc is None:
            raise NoApcFoundError(f"No APC record for code={procedure_code!r} year={year}")

        relative_weight = apc.relative_weight or Decimal("0.00")
        conversion_factor = context.conversion_factor or Decimal("0.00")
        base_price = relative_weight * conversion_factor * context.input_data.units
        return self.apply_modifiers(context, base_price)
