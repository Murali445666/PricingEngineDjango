"""
Seed the clean Highmark–Keystone agreement from docs CSVs.

Usage:
  python manage.py seed_agreement
  python manage.py seed_agreement --roster docs/provider_roster.csv --members docs/members.csv
"""
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from core.demo.seed_agreement import seed_agreement_atomic


class Command(BaseCommand):
    help = (
        'Idempotent seed for the Highmark–Keystone Commercial PPO agreement '
        '(payer, orgs, roster, members, contract).'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--roster',
            type=str,
            default=None,
            help='Path to provider_roster.csv (default: docs/provider_roster.csv)',
        )
        parser.add_argument(
            '--members',
            type=str,
            default=None,
            help='Path to members.csv (default: docs/members.csv)',
        )

    def handle(self, *args, **options):
        roster = Path(options['roster']) if options.get('roster') else None
        members = Path(options['members']) if options.get('members') else None

        try:
            result = seed_agreement_atomic(
                roster_path=roster,
                members_path=members,
                stdout=self.stdout,
            )
        except Exception as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(self.style.SUCCESS('\nseed_agreement completed.'))

        created = result['created_stats']
        if created:
            self.stdout.write('\nRows created this run:')
            for table, count in sorted(created.items()):
                if count:
                    self.stdout.write(f'  {table}: +{count}')
        else:
            self.stdout.write('\n(no new rows — already seeded)')

        self.stdout.write(
            self.style.SUCCESS(
                f"\nUse for import_fee_schedule: "
                f"--contract {result['contract_id']} --contract-version {result['version_id']}"
            )
        )
