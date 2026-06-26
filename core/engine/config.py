"""
Step 6 extension: ContractPricingConfig abstraction.

ContractPricingConfig is immutable and request-scoped. It is constructed once per
pricing execution (or snapshot load) and must not be mutated during runtime.
Loader and resolver consume config instead of querying raw tables when config is provided.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Dict, Optional, List, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from core.models import (
        ProviderContract,
        ContractVersion,
        PricingRule,
        ContractMethodology,
        ContractStopLossRule,
        ContractOutlierRule,
        ContractCarveout,
        ContractCapFloor,
        ContractBlendingRule,
        MPPRDefinition,
    )


@dataclass(frozen=False)  # frozen=False so we can hold ORM models; do not mutate after construction
class ContractPricingConfig:
    """
    Resolved, effective pricing configuration for a contract + version.
    Immutable and request-scoped: construct once per pricing execution or snapshot load;
    do not mutate during runtime.
    """
    contract: ProviderContract
    version: Optional[ContractVersion]
    service_date: date
    rules: Tuple[PricingRule, ...]
    methodologies: Tuple[ContractMethodology, ...]
    stop_loss_rules: Tuple[ContractStopLossRule, ...]
    outlier_rules: Tuple[ContractOutlierRule, ...]
    # N+1 ELIMINATED (H2): DRG/APC base rates preloaded once per config build;
    # maps rate_type (e.g. 'DRG', 'APC') -> base_rate Decimal so load_context
    # never queries ContractBaseRate inside the per-line loop.
    base_rates: Dict[str, Decimal] = field(default_factory=dict)
    # Step 7: line-level carve-outs preloaded once; applied in ClaimOrchestrator line loop.
    carveouts: Tuple["ContractCarveout", ...] = field(default_factory=tuple)
    # Step 8: claim-level caps/floors preloaded once; applied after outlier.
    # Phase G: line_cap_floors are LINE-scope only; claim step uses cap_floors but skips LINE.
    cap_floors: Tuple["ContractCapFloor", ...] = field(default_factory=tuple)
    line_cap_floors: Tuple["ContractCapFloor", ...] = field(default_factory=tuple)
    # Step 9: blending rules preloaded once; applied after stop-loss/outlier, before caps.
    blending_rules: Tuple["ContractBlendingRule", ...] = field(default_factory=tuple)
    # Phase 1 staged engine: rules partitioned by rule_type (null/blank -> 'BASE') for resolve_for_stage.
    rules_by_stage: Dict[str, Tuple["PricingRule", ...]] = field(default_factory=dict)
    # Phase F: cross-line MPPR definitions (effective for service_date); applied after CLAIM_METHOD, before blending.
    mppr_definitions: Tuple["MPPRDefinition", ...] = field(default_factory=tuple)

    def __post_init__(self):
        if not isinstance(self.rules, tuple):
            object.__setattr__(self, "rules", tuple(self.rules))
        if not isinstance(self.methodologies, tuple):
            object.__setattr__(self, "methodologies", tuple(self.methodologies))
        if not isinstance(self.stop_loss_rules, tuple):
            object.__setattr__(self, "stop_loss_rules", tuple(self.stop_loss_rules))
        if not isinstance(self.outlier_rules, tuple):
            object.__setattr__(self, "outlier_rules", tuple(self.outlier_rules))
        if not isinstance(self.carveouts, tuple):
            object.__setattr__(self, "carveouts", tuple(self.carveouts))
        if not isinstance(self.cap_floors, tuple):
            object.__setattr__(self, "cap_floors", tuple(self.cap_floors))
        if not isinstance(self.line_cap_floors, tuple):
            object.__setattr__(self, "line_cap_floors", tuple(self.line_cap_floors))
        if not isinstance(self.blending_rules, tuple):
            object.__setattr__(self, "blending_rules", tuple(self.blending_rules))
        if not isinstance(self.mppr_definitions, tuple):
            object.__setattr__(self, "mppr_definitions", tuple(self.mppr_definitions))


@dataclass
class ClaimLineInput:
    """Single line input for claim pricing (stored claim line or batch line)."""
    procedure_code: str
    billed_amount: Decimal
    units: int = 1
    modifiers: List[str] = field(default_factory=list)
    cost_amount: Optional[Decimal] = None
    # Phase C: optional revenue code for resolver condition revenue_code
    revenue_code: Optional[str] = None


@dataclass
class ClaimPricingInput:
    """
    Claim-like input for unified claim pricing. Supports both stored ClaimHeader
    and ad-hoc batch payloads. Used by ClaimPricingService and ClaimOrchestrator.
    Phase E: drg_code and facility_id for claim-level DRG when claim_level_drg_enabled.
    """
    contract_id: Optional[int] = None
    contract: Optional[ProviderContract] = None
    service_date: Optional[date] = None
    claim_type: Optional[str] = None
    pricing_date: Optional[date] = None
    claim_id: Optional[int] = None
    lines: List[ClaimLineInput] = field(default_factory=list)
    # Phase E: claim-level DRG (from header or first line when not set)
    drg_code: Optional[str] = None
    facility_id: Optional[int] = None
    provider_id: Optional[int] = None
    # Step 14a: optional tier context from claim / simulate payload
    product_id: Optional[str] = None
    network_id: Optional[str] = None
