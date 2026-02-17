class PricingError(Exception):
    """Base class for all pricing engine errors."""
    pass

class ConfigurationError(PricingError):
    """Raised when the database data (contracts/rules) is invalid or incomplete."""
    pass

class PricingCalculationError(PricingError):
    """Raised when a mathematical operation fails (e.g., division by zero)."""
    pass