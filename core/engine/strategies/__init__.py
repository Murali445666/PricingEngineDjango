from core.engine.exceptions import ConfigurationError

# Import classes from their separate files
from .base import PricingMethodology
from .rbrvs import RBRVSMethod
from .drg import DRGMethod
from .anesthesia import AnesthesiaMethod
from .flat_rate import FlatRateMethod
from .percent import PercentBilledMethod
from .per_diem import PerDiemMethod
from .apc import ApcPricingStrategy
from .drug import AspPricingStrategy

# The Registry (multiple codes can map to the same strategy)
_APC_STRATEGY = ApcPricingStrategy()
_ASP_STRATEGY = AspPricingStrategy()

_PERCENT_BILLED_STRATEGY = PercentBilledMethod()
METHOD_REGISTRY = {
    'RBRVS': RBRVSMethod(),
    'DRG': DRGMethod(),
    'ANESTHESIA': AnesthesiaMethod(),
    'FLAT_RATE': FlatRateMethod(),
    'PERCENT_BILLED': _PERCENT_BILLED_STRATEGY,
    'PCT_BILLED': _PERCENT_BILLED_STRATEGY,
    'PER_DIEM': PerDiemMethod(),
    'OPPS': _APC_STRATEGY,
    'APC': _APC_STRATEGY,
    'DRUG': _ASP_STRATEGY,
    'ASP': _ASP_STRATEGY,
}


def get_methodology(code: str) -> PricingMethodology:
    if not code:
        raise ConfigurationError("Methodology code is required")
    key = (code or "").strip().upper()
    method = METHOD_REGISTRY.get(key)
    if not method:
        raise ConfigurationError(f"Unsupported methodology code: {code!r}")
    return method