"""
Seed DEMO-UC-* use-case transactional data for identity-first pricing demos.

Usage:
  python manage.py seed_use_cases
  python manage.py seed_use_cases --wipe
"""
from django.core.management.base import BaseCommand

from core.demo.seed_use_cases import seed_use_cases_atomic
from core.demo.use_cases import PREFIX, USE_CASES


class Command(BaseCommand):
    help = (
        "Idempotent seed for DEMO-UC-* use cases (~36 scenarios). "
        "Isolated from existing data; --wipe removes only DEMO-UC- rows."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--wipe",
            action="store_true",
            help="Delete DEMO-UC- rows (guarded) then reload",
        )

    def handle(self, *args, **options):
        result = seed_use_cases_atomic(wipe=options["wipe"], stdout=self.stdout)

        self.stdout.write(self.style.SUCCESS("seed_use_cases completed."))

        self.stdout.write("\nRows created this run (get_or_create):")
        for table, count in sorted(result["created_stats"].items()):
            if count:
                self.stdout.write(f"  {table}: +{count}")

        self.stdout.write(f"\nDEMO-UC- row counts in database (prefix {PREFIX!r}):")
        for table, count in sorted(result["demo_row_counts"].items()):
            self.stdout.write(f"  {table}: {count}")

        self.stdout.write("\nUse-case payloads (build reprice requests from these):")
        for row in result["use_cases"]:
            cid = row.get("contract_id") or "—"
            self.stdout.write(
                f"  {row['id']} [{row['family']}] "
                f"member={row['member_id']} billing={row['billing_npi']} "
                f"contract={row['contract_name']} id={cid} "
                f"expected={row['expected_status']}"
            )

        self.stdout.write(
            f"\nRegistry: {len(result['registry'])} contract entries. "
            f"Full catalog: core/demo/use_cases.py ({len(USE_CASES)} cases)."
        )
