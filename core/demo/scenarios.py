"""
Deterministic demo scenario metadata: claim JSON shapes and expected outcomes.

IDs (contract_id, version_id) are resolved at runtime after seeding via resolve_demo_registry().
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

DEMO_SERVICE_DATE = date(2026, 6, 1)
DEMO_SERVICE_DATE_STR = "2026-06-01"

DEMO_CONTRACT_KEYS = (
    "DEMO_RBRVS",
    "DEMO_DRG",
    "DEMO_FLAT",
    "DEMO_PCT_BILLED",
    "DEMO_APC",
    "DEMO_ASP",
    "DEMO_PER_DIEM",
    "DEMO_ANESTHESIA",
    "DEMO_POLICY",
)

# --- Base payment-type scenarios (one primary methodology per contract) ---

BASE_SCENARIOS: dict[str, dict[str, Any]] = {
    "DEMO_RBRVS": {
        "payment_type": "RBRVS",
        "service_type": "PROFESSIONAL",
        "member_provider_context": "Demo provider org; office visit professional claim",
        "procedure_code": "99213",
        "claim": {
            "service_date": DEMO_SERVICE_DATE_STR,
            "claim_type": "PROFESSIONAL",
            "lines": [
                {
                    "line_id": "L1",
                    "procedure_code": "99213",
                    "billed_amount": "200.00",
                    "units": 1,
                    "modifiers": [],
                }
            ],
        },
        "expected": {
            "line_status": "SUCCESS",
            "methodology": "RBRVS",
            "line_allowed": Decimal("150.00"),
            "total_allowed": Decimal("150.00"),
            "rule_name_contains": "RBRVS",
        },
        "explanation": (
            "Fee schedule rate $100.00 × rule multiplier 1.5 = $150.00 allowed. "
            "Billed $200 does not cap RBRVS on this demo contract."
        ),
    },
    "DEMO_DRG": {
        "payment_type": "DRG (claim-level)",
        "service_type": "INPATIENT",
        "member_provider_context": "Inpatient bundled DRG 470; claim-level DRG enabled on version",
        "procedure_code": "470",
        "claim": {
            "service_date": DEMO_SERVICE_DATE_STR,
            "claim_type": "INPATIENT",
            "drg_code": "470",
            "lines": [
                {
                    "line_id": "L1",
                    "procedure_code": "470",
                    "billed_amount": "50000.00",
                    "units": 1,
                    "modifiers": [],
                }
            ],
        },
        "expected": {
            "line_status": "SUCCESS",
            "methodology": "DRG",
            "total_allowed": Decimal("12000.00"),
            "claim_trace_contains": "CLAIM_DRG_APPLIED",
        },
        "explanation": (
            "Claim-level DRG: facility base rate $6,000 × DRG 470 relative weight 2.0 = $12,000 "
            "bundled claim payment (replaces line rollup when claim_level_drg_enabled)."
        ),
    },
    "DEMO_FLAT": {
        "payment_type": "FLAT_RATE",
        "service_type": "OUTPATIENT",
        "member_provider_context": "Outpatient fixed fee for procedure 00100",
        "procedure_code": "00100",
        "claim": {
            "service_date": DEMO_SERVICE_DATE_STR,
            "claim_type": "OUTPATIENT",
            "lines": [
                {
                    "line_id": "L1",
                    "procedure_code": "00100",
                    "billed_amount": "300.00",
                    "units": 1,
                    "modifiers": [],
                }
            ],
        },
        "expected": {
            "line_status": "SUCCESS",
            "methodology": "FLAT_RATE",
            "line_allowed": Decimal("250.00"),
            "total_allowed": Decimal("250.00"),
        },
        "explanation": "Flat-rate rule pays fixed $250.00 regardless of $300 billed.",
    },
    "DEMO_PCT_BILLED": {
        "payment_type": "PCT_BILLED",
        "service_type": "OUTPATIENT",
        "member_provider_context": "Percent-of-billed professional/outpatient line",
        "procedure_code": "99213",
        "claim": {
            "service_date": DEMO_SERVICE_DATE_STR,
            "claim_type": "OUTPATIENT",
            "lines": [
                {
                    "line_id": "L1",
                    "procedure_code": "99213",
                    "billed_amount": "200.00",
                    "units": 1,
                    "modifiers": [],
                }
            ],
        },
        "expected": {
            "line_status": "SUCCESS",
            "methodology": "PCT_BILLED",
            "line_allowed": Decimal("160.00"),
            "total_allowed": Decimal("160.00"),
        },
        "explanation": "Multiplier 0.8 × billed $200.00 = $160.00 allowed.",
    },
    "DEMO_APC": {
        "payment_type": "APC",
        "service_type": "OUTPATIENT",
        "member_provider_context": "OPPS/APC outpatient procedure",
        "procedure_code": "5121",
        "claim": {
            "service_date": DEMO_SERVICE_DATE_STR,
            "claim_type": "OUTPATIENT",
            "lines": [
                {
                    "line_id": "L1",
                    "procedure_code": "5121",
                    "billed_amount": "500.00",
                    "units": 1,
                    "modifiers": [],
                }
            ],
        },
        "expected": {
            "line_status": "SUCCESS",
            "methodology": "APC",
            "line_allowed": Decimal("150.00"),
            "total_allowed": Decimal("150.00"),
        },
        "explanation": (
            "APC relative weight 1.5 × conversion factor $100.00 × 1 unit = $150.00."
        ),
    },
    "DEMO_ASP": {
        "payment_type": "ASP",
        "service_type": "PROFESSIONAL",
        "member_provider_context": "Drug J-code ASP pricing",
        "procedure_code": "J0129",
        "claim": {
            "service_date": DEMO_SERVICE_DATE_STR,
            "claim_type": "PROFESSIONAL",
            "lines": [
                {
                    "line_id": "L1",
                    "procedure_code": "J0129",
                    "billed_amount": "50.00",
                    "units": 2,
                    "modifiers": [],
                }
            ],
        },
        "expected": {
            "line_status": "SUCCESS",
            "methodology": "ASP",
            "line_allowed": Decimal("24.00"),
            "total_allowed": Decimal("24.00"),
        },
        "explanation": "ASP payment limit $12.00 per unit × 2 units = $24.00 (2026-Q2 quarter).",
    },
    "DEMO_PER_DIEM": {
        "payment_type": "PER_DIEM",
        "service_type": "INPATIENT",
        "member_provider_context": "Inpatient per-diem by day count",
        "procedure_code": "0120",
        "claim": {
            "service_date": DEMO_SERVICE_DATE_STR,
            "claim_type": "INPATIENT",
            "lines": [
                {
                    "line_id": "L1",
                    "procedure_code": "0120",
                    "billed_amount": "5000.00",
                    "units": 3,
                    "modifiers": [],
                }
            ],
        },
        "expected": {
            "line_status": "SUCCESS",
            "methodology": "PER_DIEM",
            "line_allowed": Decimal("1200.00"),
            "total_allowed": Decimal("1200.00"),
        },
        "explanation": "Per-diem rate $400.00 × 3 days/units = $1,200.00.",
    },
    "DEMO_ANESTHESIA": {
        "payment_type": "ANESTHESIA",
        "service_type": "PROFESSIONAL",
        "member_provider_context": "Anesthesia base units + time units",
        "procedure_code": "00100",
        "claim": {
            "service_date": DEMO_SERVICE_DATE_STR,
            "claim_type": "PROFESSIONAL",
            "lines": [
                {
                    "line_id": "L1",
                    "procedure_code": "00100",
                    "billed_amount": "1000.00",
                    "units": 30,
                    "modifiers": [],
                }
            ],
        },
        "expected": {
            "line_status": "SUCCESS",
            "methodology": "ANESTHESIA",
            "line_allowed": Decimal("315.00"),
            "total_allowed": Decimal("315.00"),
        },
        "explanation": (
            "Base units 5 (from fee schedule) + time units 30÷15=2; "
            "(5+2) × conversion factor $45.00 = $315.00."
        ),
    },
}

# --- Policy contract: non-base behaviors (DEMO_POLICY) ---

POLICY_SCENARIOS: dict[str, dict[str, Any]] = {
    "carveout_exclude": {
        "payment_type": "Policy — carve-out EXCLUDE",
        "service_type": "PROFESSIONAL",
        "procedure_code": "99100",
        "claim": {
            "service_date": DEMO_SERVICE_DATE_STR,
            "claim_type": "PROFESSIONAL",
            "lines": [
                {
                    "line_id": "L1",
                    "procedure_code": "99100",
                    "billed_amount": "150.00",
                    "units": 1,
                    "modifiers": [],
                }
            ],
        },
        "expected": {
            "line_status": "CARVEOUT_EXCLUDED",
            "line_allowed": Decimal("0.00"),
            "base_allowed_before_policy": Decimal("100.00"),
            "total_allowed": Decimal("0.00"),
        },
        "explanation": (
            "RBRVS base would pay $100.00; EXCLUDE carve-out on 99100 zeros the line "
            "(base_allowed_amount retained for audit)."
        ),
    },
    "stop_loss": {
        "payment_type": "Policy — stop-loss",
        "service_type": "PROFESSIONAL",
        "procedure_code": "99213",
        "claim": {
            "service_date": DEMO_SERVICE_DATE_STR,
            "claim_type": "PROFESSIONAL",
            "lines": [
                {
                    "line_id": "L1",
                    "procedure_code": "99213",
                    "billed_amount": "200.00",
                    "units": 1,
                    "modifiers": [],
                    "cost_amount": "9000.00",
                }
            ],
        },
        "expected": {
            "claim_status": "STOP_LOSS_APPLIED",
            "line_allowed_before_policy": Decimal("150.00"),
            "total_allowed": Decimal("5000.00"),
        },
        "explanation": (
            "Line RBRVS allowed $150.00; claim cost $9,000 exceeds threshold $1,000. "
            "Stop-loss pays $1,000 + 50% of excess $8,000 = $5,000 claim total."
        ),
    },
    "outlier": {
        "payment_type": "Policy — outlier",
        "service_type": "OUTPATIENT",
        "procedure_code": "73030",
        "claim": {
            "service_date": DEMO_SERVICE_DATE_STR,
            "claim_type": "OUTPATIENT",
            "lines": [
                {
                    "line_id": "L1",
                    "procedure_code": "73030",
                    "billed_amount": "5000.00",
                    "units": 1,
                    "modifiers": [],
                }
            ],
        },
        "expected": {
            "claim_status": "OUTLIER_APPLIED",
            "line_allowed_before_policy": Decimal("75.00"),
            "total_allowed": Decimal("4000.00"),
        },
        "explanation": (
            "Flat line allowed $75.00; total billed $5,000 exceeds outlier threshold $1,000. "
            "Outlier replaces claim total with 80% of charges = $4,000."
        ),
    },
    "blending_add": {
        "payment_type": "Policy — blending ADD",
        "service_type": "OUTPATIENT",
        "procedure_code": "73030",
        "claim": {
            "service_date": DEMO_SERVICE_DATE_STR,
            "claim_type": "OUTPATIENT",
            "lines": [
                {
                    "line_id": "L1",
                    "procedure_code": "73030",
                    "billed_amount": "1000.00",
                    "units": 1,
                    "modifiers": [],
                }
            ],
        },
        "expected": {
            "total_before_blending": Decimal("75.00"),
            "total_allowed": Decimal("175.00"),
        },
        "explanation": (
            "Base flat allowed $75.00; ADD blending adds 10% of billed ($100) → $175.00 claim total."
        ),
    },
    "claim_cap": {
        "payment_type": "Policy — claim CAP",
        "service_type": "PROFESSIONAL",
        "procedure_code": "99213",
        "claim": {
            "service_date": DEMO_SERVICE_DATE_STR,
            "claim_type": "PROFESSIONAL",
            "lines": [
                {
                    "line_id": "L1",
                    "procedure_code": "99213",
                    "billed_amount": "200.00",
                    "units": 1,
                    "modifiers": [],
                },
                {
                    "line_id": "L2",
                    "procedure_code": "99213",
                    "billed_amount": "200.00",
                    "units": 1,
                    "modifiers": [],
                },
            ],
        },
        "expected": {
            "total_before_cap": Decimal("300.00"),
            "total_allowed": Decimal("250.00"),
        },
        "explanation": (
            "Two RBRVS lines at $150 each = $300; claim CAP $250 clamps the final total."
        ),
    },
    "claim_floor": {
        "payment_type": "Policy — claim FLOOR",
        "service_type": "OUTPATIENT",
        "procedure_code": "73030",
        "claim": {
            "service_date": DEMO_SERVICE_DATE_STR,
            "claim_type": "OUTPATIENT",
            "lines": [
                {
                    "line_id": "L1",
                    "procedure_code": "73030",
                    "billed_amount": "100.00",
                    "units": 1,
                    "modifiers": [],
                }
            ],
        },
        "expected": {
            "total_before_floor": Decimal("75.00"),
            "total_allowed": Decimal("100.00"),
        },
        "explanation": (
            "Flat allowed $75.00; claim FLOOR $100 raises the final claim total."
        ),
    },
    "mppr": {
        "payment_type": "Policy — MPPR",
        "service_type": "PROFESSIONAL",
        "procedure_code": "99213",
        "claim": {
            "service_date": DEMO_SERVICE_DATE_STR,
            "claim_type": "PROFESSIONAL",
            "lines": [
                {
                    "line_id": "L1",
                    "procedure_code": "99213",
                    "billed_amount": "200.00",
                    "units": 1,
                    "modifiers": [],
                },
                {
                    "line_id": "L2",
                    "procedure_code": "99213",
                    "billed_amount": "200.00",
                    "units": 1,
                    "modifiers": [],
                },
            ],
        },
        "expected": {
            "line1_allowed": Decimal("150.00"),
            "line2_allowed_after_mppr": Decimal("75.00"),
            "total_after_mppr_before_blend": Decimal("225.00"),
        },
        "explanation": (
            "Two identical 99213 lines at $150 each; MPPR pays 100% on highest and 50% on second "
            "→ $225 before downstream blending/cap on other scenarios."
        ),
    },
}

NEGATIVE_SCENARIO = {
    "contract_key": "DEMO_RBRVS",
    "payment_type": "No matching rule",
    "claim": {
        "service_date": DEMO_SERVICE_DATE_STR,
        "claim_type": "OUTPATIENT",
        "lines": [
            {
                "line_id": "L1",
                "procedure_code": "NOMATCH999",
                "billed_amount": "100.00",
                "units": 1,
                "modifiers": [],
            }
        ],
    },
    "expected": {
        "line_status": "DENIED_NO_RULE",
        "line_allowed": Decimal("0.00"),
        "rule_id": 0,
    },
    "explanation": "No ACTIVE rule matches procedure NOMATCH999 → denied line.",
}
