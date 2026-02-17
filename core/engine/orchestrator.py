import time
from decimal import Decimal
from core.models import ProviderContract
from .types import PricingInput, LineResult, PricingStatus, PricingTrace
from .loader import PricingDataLoader
from .resolver import StrictRuleResolver
from .strategies import get_methodology

class PricingEngine:
    VERSION = "1.0.1-Traceability"

    def __init__(self):
        self.loader = PricingDataLoader()

    def calculate_line(self, contract: ProviderContract, request: PricingInput) -> LineResult:
        start_time = time.perf_counter()
        trace = PricingTrace()
        trace.log("ORCHESTRATOR", f"Processing {request.procedure_code} | TraceID: {trace.trace_id}")

        # Helper to wrap results with timing and Traceability
        def build_result(status, amount=None, method="", details="", rule=None):
            duration = (time.perf_counter() - start_time) * 1000 # ms
            
            # Extract IDs for traceability
            r_id = rule.rule_id if rule else 0
            # Use .pk to safely get ID regardless of field name (contract_id vs id)
            c_id = str(contract.pk) if contract else "UNKNOWN"

            return LineResult(
                status=status,
                allowed_amount=amount if amount else Decimal("0.00"),
                methodology=method,
                details=details,
                contract_id=c_id,  # <--- Stamped
                rule_id=r_id,      # <--- Stamped
                trace=trace,
                engine_version=self.VERSION,
                execution_time_ms=round(duration, 2)
            )

        # 1. Rule Resolution
        resolver = StrictRuleResolver(contract)
        rule = resolver.resolve(request, trace)

        if not rule:
            return build_result(PricingStatus.DENIED_NO_RULE, details="No matching rule found in contract.")

        # 2. Data Loading
        try:
            context = self.loader.load_context(request, rule)
        except Exception as e:
            return build_result(
                PricingStatus.DENIED_MISSING_DATA, 
                method=PricingStatus.DENIED_MISSING_DATA.value,
                details=str(e),
                rule=rule # Trace the rule even if loading fails
            )

        # 3. Strategy Execution
        try:
            strategy = get_methodology(rule.methodology_code)
            price = strategy.calculate(context)
            
            return build_result(
                PricingStatus.SUCCESS,
                amount=price,
                method=rule.methodology_code,
                rule=rule # <--- Pass the rule so we capture the ID
            )
        except Exception as e:
            return build_result(
                PricingStatus.DENIED_CALCULATION_ERROR, 
                method=PricingStatus.DENIED_CALCULATION_ERROR.value,
                details=str(e),
                rule=rule
            )