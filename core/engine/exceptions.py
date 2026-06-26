class PricingError(Exception):
    """Base class for all pricing engine errors."""
    pass

class ConfigurationError(PricingError):
    """Raised when the database data (contracts/rules) is invalid or incomplete."""
    pass

class PricingCalculationError(PricingError):
    """Raised when a mathematical operation fails (e.g., division by zero)."""
    pass


class NoApcFoundError(PricingError):
    """Raised when RefApc has no record for the given procedure code and year."""
    pass


class NoAspFoundError(PricingError):
    """Raised when RefAspPricing has no record and no fee schedule fallback."""
    pass


class ContractResolutionError(PricingError):
    """Raised when no contract can be resolved for a claim (e.g. no participation or no matching scope)."""
    pass


class ContractResolutionTieError(PricingError):
    """Raised when multiple contracts tie after ranking and a single deterministic contract cannot be chosen."""
    pass