"""
ASP (Average Sales Price) / Drug pricing strategy.
Uses RefAspPricing: allowed_amount = payment_limit * units (or asp * units if payment_limit missing).
Falls back to fee schedule base_rate when no ASP record is found.
"""
from datetime import date
from decimal import Decimal

from core.models import RefAspPricing
from .base import PricingMethodology
from ..types import PricingContext
from ..exceptions import NoAspFoundError


def _quarter_from_date(d: date) -> str | None:
    """Return quarter string e.g. '2024-Q1' for ASP lookup."""
    if d is None:
        return None
    month = d.month
    if month <= 3:
        q = "Q1"
    elif month <= 6:
        q = "Q2"
    elif month <= 9:
        q = "Q3"
    else:
        q = "Q4"
    return f"{d.year}-{q}"


class AspPricingStrategy(PricingMethodology):
    """DRUG/ASP methodology: look up RefAspPricing by HCPCS and quarter from service_date."""

    def calculate(self, context: PricingContext) -> Decimal:
        procedure_code = (context.input_data.procedure_code or "").strip()
        service_date = context.input_data.service_date or date.today()
        quarter = _quarter_from_date(service_date)
        units = context.input_data.units

        if not quarter:
            if context.base_rate is not None:
                base_price = context.base_rate * units
                return self.apply_modifiers(context, base_price)
            raise NoAspFoundError(f"No quarter for service_date={service_date}; no ASP or fallback rate")

        try:
            asp_row = RefAspPricing.objects.get(
                hcpcs_code=procedure_code,
                quarter=quarter,
            )
        except RefAspPricing.DoesNotExist:
            asp_row = None

        if asp_row is not None:
            # Prefer payment_limit; fall back to asp
            amount_per_unit = getattr(asp_row, "payment_limit", None) or asp_row.asp
            if amount_per_unit is not None:
                base_price = amount_per_unit * units
                return self.apply_modifiers(context, base_price)

        # Fallback: standard fee schedule rate
        if context.base_rate is not None:
            base_price = context.base_rate * units
            return self.apply_modifiers(context, base_price)

        raise NoAspFoundError(f"No ASP record for HCPCS={procedure_code!r} quarter={quarter}; no fallback rate")
