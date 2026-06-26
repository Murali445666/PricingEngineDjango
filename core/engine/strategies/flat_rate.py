from datetime import date
from decimal import Decimal

from django.db.models import Q

from .base import PricingMethodology
from ..types import PricingContext


def _resolve_flat_rate(context: PricingContext) -> Decimal:
    """
    Resolve rate: from rule's base_fee_schedule by procedure_code if present, else context.flat_rate.
    """
    base_fs_id = getattr(context, "base_fee_schedule_id", None)
    procedure_code = getattr(context.input_data, "procedure_code", None) or ""
    service_date = getattr(context.input_data, "service_date", None) or date.today()

    if base_fs_id and procedure_code:
        from core.models import FeeScheduleRate

        try:
            qs = FeeScheduleRate.objects.filter(
                fee_schedule_id=base_fs_id,
                code_id=procedure_code,
            ).filter(
                Q(effective_start_date__isnull=True) | Q(effective_start_date__lte=service_date)
            ).filter(
                Q(effective_end_date__isnull=True) | Q(effective_end_date__gte=service_date)
            )
            rate_row = qs.order_by("-year").first()
            if rate_row is None:
                rate_row = FeeScheduleRate.objects.filter(
                    fee_schedule_id=base_fs_id,
                    code_id=procedure_code,
                ).first()
            if rate_row is not None and rate_row.rate_amount is not None:
                return rate_row.rate_amount
        except Exception:
            pass

    return context.flat_rate or Decimal("0.00")


class FlatRateMethod(PricingMethodology):
    def calculate(self, context: PricingContext) -> Decimal:
        rate = _resolve_flat_rate(context)
        units = getattr(context.input_data, "units", None) or Decimal("1")
        if not isinstance(units, Decimal):
            units = Decimal(str(units))
        price = rate * units
        return self.apply_modifiers(context, price)