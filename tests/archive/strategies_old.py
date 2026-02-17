from abc import ABC, abstractmethod
from decimal import Decimal
from typing import List
from core.models import PricingRule, FeeScheduleRate, RefProcedureCode, RefModifier
from core.engine.exceptions import ConfigurationError, PricingCalculationError

# ---------------------------------------------------------
# The Interface (The Blueprint)
# ---------------------------------------------------------
class PricingMethodology(ABC):
    """
    Abstract base class for all pricing strategies.
    Point 2: Replace if/elif with polymorphic classes.
    """
    @abstractmethod
    def calculate(self, rule: PricingRule, code: str, billed: Decimal, units: int = 1, modifiers: List[str] = None) -> Decimal:
        pass

    def apply_modifiers(self, base_amount: Decimal, modifiers: List[str]) -> Decimal:
        """Shared logic for Point 9: Modifier application"""
        if not modifiers:
            return base_amount
        
        final_amount = base_amount
        # Point 9: Sort modifiers deterministically to prevent variance
        sorted_mods = sorted(modifiers) 
        
        for mod_code in sorted_mods:
            try:
                mod = RefModifier.objects.get(modifier_code=mod_code)
                # Math: Amount * (Percent / 100)
                final_amount *= (mod.percentage_adjustment / Decimal("100.00"))
            except RefModifier.DoesNotExist:
                # Decide: Log warning? Ignore? For now, ignore non-pricing modifiers.
                pass
        return final_amount

# ---------------------------------------------------------
# The Strategies (The Workers)
# ---------------------------------------------------------
class RBRVSMethod(PricingMethodology):
    def calculate(self, rule: PricingRule, code: str, billed: Decimal, units: int = 1, modifiers: List[str] = None) -> Decimal:
        # Point 8: Defensive Data Check
        if not rule.base_fee_schedule:
            raise ConfigurationError(f"Rule {rule.rule_name} (RBRVS) missing base_fee_schedule.")

        try:
            rate_obj = FeeScheduleRate.objects.get(
                fee_schedule=rule.base_fee_schedule, 
                code_id=code
            )
        except FeeScheduleRate.DoesNotExist:
            # We raise a specific error so the engine knows it's a "Missing Fee" issue, not a code bug.
            raise PricingCalculationError(f"Fee not found for code {code} in schedule {rule.base_fee_schedule.name}")

        # Core Math: Rate * Rule Multiplier * Units
        base_price = rate_obj.rate_amount * rule.multiplier * units
        return self.apply_modifiers(base_price, modifiers or [])

class FlatRateMethod(PricingMethodology):
    def calculate(self, rule: PricingRule, code: str, billed: Decimal, units: int = 1, modifiers: List[str] = None) -> Decimal:
        # Core Math: Flat Rate * Units (Modifiers usually don't apply to flat rates, but we allow it here)
        base_price = rule.flat_rate * units
        return self.apply_modifiers(base_price, modifiers or [])

class PercentBilledMethod(PricingMethodology):
    def calculate(self, rule: PricingRule, code: str, billed: Decimal, units: int = 1, modifiers: List[str] = None) -> Decimal:
        # Point 8: Defensive Check
        if rule.multiplier is None:
            raise ConfigurationError(f"Rule {rule.rule_name} (Percent Billed) missing multiplier.")
            
        # Core Math: Billed * Multiplier
        return billed * rule.multiplier

class DRGMethod(PricingMethodology):
    def calculate(self, rule: PricingRule, code: str, billed: Decimal, units: int = 1, modifiers: List[str] = None) -> Decimal:
        try:
            # In our seed data, DRG weight is stored in 'work_rvu' of RefProcedureCode
            ref_code = RefProcedureCode.objects.get(code_id=code)
        except RefProcedureCode.DoesNotExist:
            raise PricingCalculationError(f"DRG Code {code} not found in Reference Table")

        # Core Math: Base Rate (Flat Rate) * Weight
        base_price = rule.flat_rate * ref_code.work_rvu
        return base_price

class PerDiemMethod(PricingMethodology):
    def calculate(self, rule: PricingRule, code: str, billed: Decimal, units: int = 1, modifiers: List[str] = None) -> Decimal:
        # Core Math: Daily Rate (Flat Rate) * Length of Stay (Units)
        return rule.flat_rate * units
    
class AnesthesiaMethod(PricingMethodology):
    """
    Method: (Base Units + Time Units) * Conversion Factor
    Time Units = Billed Minutes / 15
    """
    def calculate(self, rule: PricingRule, code: str, billed: Decimal, units: int = 1, modifiers: List[str] = None) -> Decimal:
        # 1. Get Base Units (e.g., from Fee Schedule or Ref Table)
        # For this example, let's assume the 'rate_amount' in FeeSchedule is actually the Base Units.
        try:
            base_units = FeeScheduleRate.objects.get(
                fee_schedule=rule.base_fee_schedule, 
                code_id=code
            ).rate_amount
        except FeeScheduleRate.DoesNotExist:
             raise PricingCalculationError(f"Base units not found for {code}")

        # 2. Calculate Time Units (Units passed in are minutes)
        # Standard: 1 Unit per 15 minutes
        time_units = Decimal(units) / Decimal("15.00")
        
        # 3. Get Conversion Factor (Stored in Rule Multiplier)
        conversion_factor = rule.multiplier

        # 4. Math: (Base + Time) * Factor
        total_units = base_units + time_units
        price = total_units * conversion_factor
        
        return self.apply_modifiers(price, modifiers or [])

# ---------------------------------------------------------
# The Registry (The Switchboard)
# ---------------------------------------------------------
METHOD_REGISTRY = {
    'RBRVS': RBRVSMethod(),
    'FLAT_RATE': FlatRateMethod(),
    'PERCENT_BILLED': PercentBilledMethod(),
    'DRG': DRGMethod(),
    'PER_DIEM': PerDiemMethod(),
    'ANESTHESIA': AnesthesiaMethod(),
}

def get_methodology(code: str) -> PricingMethodology:
    """Factory function to get the right strategy."""
    method = METHOD_REGISTRY.get(code)
    if not method:
        raise ConfigurationError(f"Unsupported methodology code: {code}")
    return method