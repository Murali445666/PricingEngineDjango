"""
Deterministic demo seeding for pricing engine UI and regression tests.

Usage:
  python manage.py seed_demo

Creates nine DEMO_* contracts (one primary payment type each, plus DEMO_POLICY)
with fixed reference data and reproducible expected amounts. See docs/DEMO_TEST_CASES.md.
"""
import logging

from django.core.management.base import BaseCommand

from core.demo.deterministic_seed import seed_deterministic_demos_atomic, resolve_demo_registry
from core.demo.scenarios import DEMO_CONTRACT_KEYS

logger = logging.getLogger(__name__)


def generate_bulk_claims(contract_key: str, count: int):
    """
    Generate simple multi-line claims for bulk pricing demos.
    Returns list of claim dicts with contract_id, lines, service_date.
    """
    from core.models import ProviderContract

    contract = ProviderContract.objects.filter(legacy_contract_number=contract_key).first()
    if not contract:
        return []
    code = "99213" if contract_key == "DEMO_RBRVS" else "00100"
    claims = []
    for i in range(count):
        claims.append({
            "contract_id": contract.contract_id,
            "service_date": "2026-06-01",
            "lines": [
                {
                    "procedure_code": code,
                    "billed_amount": "200.00",
                    "units": 1,
                    "modifiers": [],
                }
            ],
        })
    return claims


class Command(BaseCommand):
    help = (
        "Idempotent deterministic demo seed: DEMO_RBRVS, DEMO_DRG, DEMO_FLAT, "
        "DEMO_PCT_BILLED, DEMO_APC, DEMO_ASP, DEMO_PER_DIEM, DEMO_ANESTHESIA, DEMO_POLICY."
    )

    def handle(self, *args, **options):
        verbosity = options.get("verbosity", 1)
        if verbosity > 0:
            logging.basicConfig(level=logging.INFO)

        registry = seed_deterministic_demos_atomic()

        self.stdout.write(self.style.SUCCESS("seed_demo completed successfully."))
        self.stdout.write("Contracts created:")
        for key in DEMO_CONTRACT_KEYS:
            meta = registry.get(key, {})
            self.stdout.write(
                f"  - {key}: contract_id={meta.get('contract_id')} version_id={meta.get('version_id')}"
            )
        self.stdout.write(
            "See docs/DEMO_TEST_CASES.md for claim JSON examples and expected results."
        )
