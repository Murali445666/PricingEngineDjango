from core.engine.exceptions import ConfigurationError

# Import classes from their separate files
from .base import PricingMethodology
from .rbrvs import RBRVSMethod
from .drg import DRGMethod
from .anesthesia import AnesthesiaMethod
from .flat_rate import FlatRateMethod
from .percent import PercentBilledMethod
from .per_diem import PerDiemMethod

# The Registry
METHOD_REGISTRY = {
    'RBRVS': RBRVSMethod(),
    'DRG': DRGMethod(),
    'ANESTHESIA': AnesthesiaMethod(),
    'FLAT_RATE': FlatRateMethod(),
    'PERCENT_BILLED': PercentBilledMethod(),
    'PER_DIEM': PerDiemMethod(),
}

def get_methodology(code: str) -> PricingMethodology:
    method = METHOD_REGISTRY.get(code)
    if not method:
        raise ConfigurationError(f"Unsupported methodology code: {code}")
    return method