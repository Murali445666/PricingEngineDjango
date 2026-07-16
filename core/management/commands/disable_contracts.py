"""
Soft-disable contracts (and their versions) so the resolver and UI ignore them,
without deleting any rows. Reversible: flip status/effective_end_date back.

Ref tables and entity tables are never touched — only `contracts` and
`contract_versions` are updated.

Usage:
  python manage.py disable_contracts                 # disable ALL contracts
  python manage.py disable_contracts --keep 44 45    # disable all EXCEPT these
  python manage.py disable_contracts --dry-run       # report only, no writes
"""
from datetime import date

from django.core.management.base import BaseCommand
from django.db import transaction

from core.models import ContractVersion, ProviderContract

# A date safely before any test service date, so the resolver's
# effective_start/effective_end window filter excludes these contracts.
DISABLED_END_DATE = date(2000, 1, 1)


class Command(BaseCommand):
    help = "Soft-disable contracts + versions (status=ARCHIVED, past end date). Reversible."

    def add_arguments(self, parser):
        parser.add_argument(
            "--keep",
            type=int,
            nargs="*",
            default=[],
            help="Contract IDs to leave untouched (e.g. the new clean contract).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would change without writing.",
        )

    def handle(self, *args, **options):
        keep = set(options["keep"])
        dry = options["dry_run"]

        contracts = ProviderContract.objects.exclude(pk__in=keep)
        versions = ContractVersion.objects.exclude(contract_id__in=keep)

        c_count = contracts.count()
        v_count = versions.count()

        if keep:
            self.stdout.write(f"Keeping contract_id(s): {sorted(keep)}")
        self.stdout.write(
            f"Will disable {c_count} contract(s) and {v_count} version(s) "
            f"(status=ARCHIVED, effective_end_date={DISABLED_END_DATE})."
        )

        if dry:
            self.stdout.write(self.style.WARNING("Dry run — no changes written."))
            return

        with transaction.atomic():
            c_updated = contracts.update(
                status="ARCHIVED",
                effective_end_date=DISABLED_END_DATE,
            )
            v_updated = versions.update(
                status=ContractVersion.VersionStatus.ARCHIVED,
                effective_end_date=DISABLED_END_DATE,
            )

        remaining_active = ProviderContract.objects.filter(status="ACTIVE").count()
        self.stdout.write(
            self.style.SUCCESS(
                f"Disabled {c_updated} contract(s), {v_updated} version(s). "
                f"Active contracts remaining: {remaining_active}."
            )
        )
