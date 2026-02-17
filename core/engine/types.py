from enum import Enum
from dataclasses import dataclass, field
from decimal import Decimal
from typing import List, Optional, Dict
import uuid

# --- Enums ---
class PricingStatus(Enum):
    SUCCESS = "SUCCESS"
    DENIED_NO_RULE = "DENIED_NO_RULE"
    DENIED_MISSING_DATA = "DENIED_MISSING_DATA"
    DENIED_CALCULATION_ERROR = "DENIED_CALCULATION_ERROR"

class RulePhase(Enum):
    STOP_LOSS = "STOP_LOSS"
    BASE = "BASE"

# --- Inputs ---
@dataclass(frozen=True)
class PricingInput:
    procedure_code: str
    billed_amount: Decimal
    units: int = 1
    modifiers: List[str] = field(default_factory=list)

# --- Context ---
@dataclass
class PricingContext:
    # 1. REQUIRED FIELDS
    input_data: PricingInput
    contract_id: str
    rule_id: int
    rule_name: str
    methodology_code: str

    # 2. OPTIONAL FIELDS
    base_rate: Optional[Decimal] = None
    conversion_factor: Optional[Decimal] = None
    flat_rate: Optional[Decimal] = None
    percent_of_billed: Optional[Decimal] = None
    drg_weight: Optional[Decimal] = None
    
    # Modifiers
    modifier_adjustments: Dict[str, Decimal] = field(default_factory=dict)

    # Stop Loss
    is_stop_loss: bool = False
    stop_loss_threshold: Optional[Decimal] = None
    stop_loss_multiplier: Optional[Decimal] = None

# --- Trace ---
@dataclass
class PricingTrace:
    trace_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    logs: List[str] = field(default_factory=list)
    
    def log(self, phase: str, message: str):
        self.logs.append(f"[{phase}] {message}")

# --- Outputs (UPDATED) ---
@dataclass
class LineResult:
    status: PricingStatus
    allowed_amount: Decimal = Decimal("0.00")
    methodology: str = ""
    details: str = ""
    
    # NEW: Traceability Fields
    contract_id: str = ""
    rule_id: int = 0
    
    trace: PricingTrace = field(default_factory=PricingTrace)
    engine_version: str = "1.0.0"
    execution_time_ms: float = 0.0