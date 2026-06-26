"""
Backfill baseline LINE PCT_BILLED_CAP (100%) on existing ContractVersions.

Operator-invoked only — not run automatically. Idempotent.
"""
from django.core.management.base import BaseCommand

from core.models import ContractCapFloor, ContractVersion
from core.signals import _BASELINE_LESSER_OF_FILTER, ensure_default_lesser_of_billed_cap


class Command(BaseCommand):
    help = (
        "Attach baseline lesser-of-billed LINE cap (PCT_BILLED_CAP @ 100%) to versions "
        "that lack one. Idempotent."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report how many caps would be created without writing",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        versions = ContractVersion.objects.all().order_by("version_id")
        total = versions.count()
        already_have = 0
        would_create = 0
        created = 0

        for version in versions:
            has_baseline = ContractCapFloor.objects.filter(
                version=version,
                **_BASELINE_LESSER_OF_FILTER,
            ).exists()
            if has_baseline:
                already_have += 1
                continue
            would_create += 1
            if dry_run:
                continue
            was_created, _ = ensure_default_lesser_of_billed_cap(version)
            if was_created:
                created += 1

        if dry_run:
            self.stdout.write(
                f"Dry run: {total} version(s) scanned; "
                f"{already_have} already have baseline cap; "
                f"{would_create} would be created."
            )
        else:
            self.stdout.write(
                f"Backfill complete: {total} version(s) scanned; "
                f"{already_have} already had baseline cap; "
                f"{created} created."
            )
