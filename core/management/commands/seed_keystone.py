"""
Seed KEYSTONE-* multi-entity resolution scenario data.

Usage:
  python manage.py seed_keystone
  python manage.py seed_keystone --wipe
"""
from django.core.management.base import BaseCommand

from core.demo.seed_keystone import PREFIX, seed_keystone_atomic


class Command(BaseCommand):
    help = (
        "Idempotent seed for KEYSTONE-* resolution scenarios (IDN, facilities, "
        "cardiology group, Horizon contracts). --wipe removes only KEYSTONE- rows."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--wipe",
            action="store_true",
            help="Delete KEYSTONE- rows (guarded) then reload",
        )

    def handle(self, *args, **options):
        result = seed_keystone_atomic(wipe=options["wipe"], stdout=self.stdout)

        self.stdout.write(self.style.SUCCESS("\nseed_keystone completed."))

        self.stdout.write("\nRows created this run (get_or_create):")
        created = result["created_stats"]
        if created:
            for table, count in sorted(created.items()):
                if count:
                    self.stdout.write(f"  {table}: +{count}")
        else:
            self.stdout.write("  (none — already seeded)")

        self.stdout.write(f"\nKEYSTONE- row counts in database (prefix {PREFIX!r}):")
        for table, count in sorted(result["keystone_row_counts"].items()):
            self.stdout.write(f"  {table}: {count}")
