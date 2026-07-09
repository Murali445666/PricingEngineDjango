from abc import ABC, abstractmethod
from decimal import Decimal
from ..types import PricingContext, ModifierTraceEvent

class PricingMethodology(ABC):
    @abstractmethod
    def calculate(self, context: PricingContext) -> Decimal:
        pass

    def apply_modifiers(self, context: PricingContext, base_amount: Decimal) -> Decimal:
        """
        Applies modifiers found in the context.
        """
        if not context.input_data.modifiers:
            return base_amount
        
        final_amount = base_amount
        for mod_code in context.input_data.modifiers:
            if mod_code in context.modifier_adjustments:
                factor = context.modifier_adjustments[mod_code]
                pre = final_amount
                final_amount = final_amount * (factor / Decimal("100.00"))
                context.modifier_events.append(ModifierTraceEvent(
                    code=mod_code,
                    status="APPLIED",
                    message=(
                        f"modifier={mod_code} factor={factor}% "
                        f"pre={pre} post={final_amount}"
                    ),
                ))
            else:
                context.modifier_events.append(ModifierTraceEvent(
                    code=mod_code,
                    status="IGNORED",
                    message=(
                        f"modifier={mod_code} present but no adjustment found "
                        f"(RefModifier/ModifierAdjustment) — NOT applied"
                    ),
                ))

        return final_amount