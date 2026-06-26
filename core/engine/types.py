from datetime import date
from enum import Enum
from dataclasses import dataclass, field
from decimal import Decimal
from typing import List, Optional, Dict, Any
import uuid

# --- Enums ---
class PricingStatus(Enum):
    SUCCESS = "SUCCESS"
    DENIED_NO_RULE = "DENIED_NO_RULE"
    DENIED_MISSING_DATA = "DENIED_MISSING_DATA"
    DENIED_CALCULATION_ERROR = "DENIED_CALCULATION_ERROR"
    NO_APC_FOUND = "NO_APC_FOUND"
    NO_ASP_FOUND = "NO_ASP_FOUND"
    OUTLIER_APPLIED = "OUTLIER_APPLIED"
    STOP_LOSS_APPLIED = "STOP_LOSS_APPLIED"
    # Step 7 – carve-outs
    CARVEOUT_EXCLUDED = "CARVEOUT_EXCLUDED"   # line zeroed; code excluded from coverage
    CARVEOUT_REPRICED = "CARVEOUT_REPRICED"   # line repriced via PCT_BILLED or FIXED_RATE
    # Step 8 – caps / floors
    CAP_APPLIED = "CAP_APPLIED"               # claim total reduced to cap
    FLOOR_APPLIED = "FLOOR_APPLIED"           # claim total raised to floor
    # Step 9 – blending
    BLENDING_APPLIED = "BLENDING_APPLIED"     # claim total modified by blending rule

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
    # Phase 2B: optional claim context for methodology resolution and rule filtering
    service_date: Optional[date] = None
    claim_type: Optional[str] = None  # INPATIENT, OUTPATIENT, PROFESSIONAL
    # Phase 5: full claim context passed through all flows
    pricing_date: Optional[date] = None
    contract_effective_date: Optional[date] = None  # or derived from contract
    # Phase C: optional revenue code for resolver condition revenue_code
    revenue_code: Optional[str] = None
    # Step 14a: optional product / network tier context (claim header); used when FEATURE_TIERED_RESOLUTION
    product_id: Optional[str] = None
    network_id: Optional[str] = None

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
    # When set, FlatRateMethod may look up rate from FeeScheduleRate by procedure_code instead of using flat_rate
    base_fee_schedule_id: Optional[int] = None
    percent_of_billed: Optional[Decimal] = None
    drg_weight: Optional[Decimal] = None

    # Phase 1: RBRVS from RefMpfsRvu + GPCI from RefGeoIndex
    work_rvu: Optional[Decimal] = None
    pe_rvu: Optional[Decimal] = None
    mp_rvu: Optional[Decimal] = None
    gpci_work: Optional[Decimal] = None
    gpci_pe: Optional[Decimal] = None
    gpci_mp: Optional[Decimal] = None

    # Modifiers
    modifier_adjustments: Dict[str, Decimal] = field(default_factory=dict)

    # Stop Loss
    is_stop_loss: bool = False
    stop_loss_threshold: Optional[Decimal] = None
    stop_loss_multiplier: Optional[Decimal] = None

    # Phase 3: ASP pricing for drug methodology (when implemented)
    asp_price: Optional[Decimal] = None
    asp_payment_limit: Optional[Decimal] = None

# --- Staged execution state (Phase 1) ---
@dataclass
class LinePricingState:
    """Per-line state that evolves during staged execution (BASE → ADJUSTMENT)."""
    input: PricingInput
    base_allowed_amount: Optional[Decimal] = None
    current_allowed_amount: Decimal = Decimal("0")


# --- Phase A: ExecutionContext + unified trace ---
@dataclass
class LineState:
    """Per-line state in ExecutionContext (input + base/current allowed)."""
    input: PricingInput
    base_allowed_amount: Optional[Decimal] = None
    current_allowed_amount: Decimal = Decimal("0")


@dataclass
class TraceEntry:
    """Single entry in the unified execution trace (serializable for audit)."""
    stage: str  # "LINE" | "CLAIM"
    phase: str  # "BASE" | "ADJUSTMENT" | "STOP_LOSS" | "OUTLIER" | "BLENDING" | "CAP_FLOOR"
    line_index: Optional[int] = None
    rule_id: Optional[int] = None
    methodology_code: str = ""
    message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "stage": self.stage,
            "phase": self.phase,
            "line_index": self.line_index,
            "rule_id": self.rule_id,
            "methodology_code": self.methodology_code,
            "message": self.message,
        }


@dataclass
class ExecutionContext:
    """Single execution context per claim (Phase A). Holds line states and unified trace. Phase E: claim-level payment fields."""
    claim_id: Optional[int] = None
    contract: Any = None
    version: Any = None
    provider_id: Optional[int] = None
    facility_id: Optional[int] = None
    service_date: Optional[date] = None
    claim_type: Optional[str] = None
    pricing_date: Optional[date] = None
    line_states: List[LineState] = field(default_factory=list)
    claim_total: Decimal = Decimal("0")
    trace: List[TraceEntry] = field(default_factory=list)
    # Phase E: claim-level methodology result (e.g. DRG payment = base_rate × weight)
    claim_level_payment: Optional[Decimal] = None
    drg_applied: bool = False
    drg_code: Optional[str] = None


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

    # Traceability
    contract_id: str = ""
    rule_id: int = 0
    applied_rule_ids: List[int] = field(default_factory=list)

    trace: PricingTrace = field(default_factory=PricingTrace)
    engine_version: str = "1.0.0"
    execution_time_ms: float = 0.0

    # Step 7: carve-out audit fields
    carveout_applied: bool = False
    carveout_id: Optional[int] = None          # ContractCarveout.carveout_id when applied
    base_allowed_amount: Optional[Decimal] = None  # strategy result before carve-out override

    # Step 9: blending audit fields
    blended_allowed_amount: Optional[Decimal] = None  # post-blending line amount (LINE scope only)
    blending_rule_id: Optional[int] = None             # ContractBlendingRule.blending_rule_id when applied

    # Phase G: line-level cap/floor audit
    applied_line_cap_floor_id: Optional[int] = None    # ContractCapFloor.cap_floor_id when LINE_CAP_FLOOR applied


# --- Phase 5B: Stored claim pricing result ---
@dataclass
class ClaimPricingResult:
    claim_id: int
    contract_id: str
    lines: List[LineResult]
    total_allowed: Decimal
    line_count: int
    status: PricingStatus = PricingStatus.SUCCESS
    claim_trace: List[str] = field(default_factory=list)
    # Phase 6 hardening: financial audit
    original_total_allowed: Optional[Decimal] = None
    final_total_allowed: Optional[Decimal] = None
    applied_outlier_rule_id: Optional[int] = None
    # Phase 7: stop-loss (evaluated before outlier)
    applied_stop_loss_rule_id: Optional[int] = None

    # Step 8: cap/floor audit fields
    pre_cap_total_allowed: Optional[Decimal] = None   # total before cap/floor clamp
    applied_cap_floor_id: Optional[int] = None        # ContractCapFloor.cap_floor_id when applied

    # Step 9: blending audit fields
    blended_total_allowed: Optional[Decimal] = None         # post-blending claim total
    applied_blending_rule_ids: List[int] = field(default_factory=list)  # rules applied

    # Phase A: unified execution trace (list of dicts, one per stage/phase)
    execution_trace: List[Dict[str, Any]] = field(default_factory=list)


# ── Stage 4: Pricing Context DTOs ─────────────────────────────────────────────

@dataclass(frozen=True)
class ProviderPricingContext:
    billing_org_id: str | None           # ProviderOrganization.organization_id
    billing_org_tax_id: str | None
    rendering_provider_id: int | None    # providers.Provider.id
    rendering_provider_specialty: str | None
    facility_id: int | None              # providers.Facility.id
    facility_type: str | None
    place_of_service: str | None
    network_status: str | None           # IN_NETWORK / OUT_OF_NETWORK / UNKNOWN
    network_tier: str | None             # TIER_1 / TIER_2 / None
    affiliation_verified: bool = False


@dataclass(frozen=True)
class MemberPricingContext:
    member_id: str | None                # members.Member.member_id (the string ID)
    product_id: int | None               # products.Product.id
    lob: str | None                      # products.LineOfBusiness.code
    network_id: int | None               # products.Network.id
    locality_zip: str | None
    enrollment_id: int | None            # members.Enrollment.id


@dataclass(frozen=True)
class ClaimPricingContext:
    """
    Fully resolved, immutable context DTO consumed by ClaimPricingService.
    Produced by PricingContextResolver. The engine never constructs this directly.
    """
    resolution_mode: str                 # DIRECT / RESOLVED / OON / NO_MEMBER
    contract_id: int
    version_id: int | None
    provider: ProviderPricingContext
    member: MemberPricingContext
    service_date: date
    pricing_date: date
    claim_type: str                      # professional / institutional
    lines: list                          # list of dicts matching ClaimLineInput fields
    simulation_mode: bool = False
    draft_rule: dict | None = None
    trace_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    requested_by: str | None = None


@dataclass
class RawClaimInput:
    """
    Unresolved claim input submitted by a caller.
    PricingContextResolver consumes this and produces ClaimPricingContext.
    """
    billing_npi: str | None = None
    rendering_npi: str | None = None
    member_id: str | None = None
    service_date: date | None = None
    pricing_date: date | None = None
    claim_type: str = 'professional'
    lines: list = field(default_factory=list)
    # Optional caller overrides — bypass resolution when set
    override_contract_id: int | None = None
    override_network_id: int | None = None