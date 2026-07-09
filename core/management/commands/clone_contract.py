"""
Clone a contract as a template for a new provider/payer (Gap D §16).

Usage:
  python manage.py clone_contract --source 213 --name "Standard Commercial PPO — NewOrg"
  python manage.py clone_contract --source 213 --name "..." --org KEYSTONE-IDN --payer 1
"""
from django.core.management.base import BaseCommand, CommandError

from core.services.contract_cloning import clone_contract


class Command(BaseCommand):
    help = 'Deep-clone a contract (ACTIVE version graph) into a new DRAFT contract.'

    def add_arguments(self, parser):
        parser.add_argument('--source', type=int, required=True, help='Source contract_id')
        parser.add_argument('--name', type=str, required=True, help='Name for the new contract')
        parser.add_argument(
            '--org',
            type=str,
            default=None,
            help='Target provider organization_id (re-points provider + matching ORG covered entities)',
        )
        parser.add_argument(
            '--payer',
            type=int,
            default=None,
            help='Target payer_org id',
        )

    def handle(self, *args, **options):
        source_id = options['source']
        try:
            new_contract, summary = clone_contract(
                source_id,
                new_name=options['name'],
                target_provider_org_id=options.get('org'),
                target_payer_org_id=options.get('payer'),
            )
        except Exception as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(self.style.SUCCESS(
            f'Cloned contract {summary.source_contract_id} -> {summary.new_contract_id} '
            f'"{summary.new_contract_name}"'
        ))
        self.stdout.write(f'  version: {summary.source_version_id} -> {summary.new_version_id}')
        if options.get('org'):
            self.stdout.write(f'  provider_org -> {options["org"]}')
        if options.get('payer'):
            self.stdout.write(f'  payer_org -> {options["payer"]}')
        self.stdout.write('  copied:')
        for label, count in sorted(summary.counts.items()):
            if count:
                self.stdout.write(f'    {label}: {count}')
