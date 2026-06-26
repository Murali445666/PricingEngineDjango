"""
Run all reference-data loaders using files in reference_data/ (Steps 1–3).
Use --dry-run to preview. Requires reference_data/ with modifiers.csv,
PPRRVU25_JAN.csv, GPCI2025.csv.

Usage:
  python manage.py load_reference_data
  python manage.py load_reference_data --dry-run
"""
from pathlib import Path

from django.core.management.base import BaseCommand
from django.core.management import call_command


class Command(BaseCommand):
    help = 'Load all reference data from reference_data/ (modifiers, PPRRVU, GPCI).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--base-dir',
            type=str,
            default='reference_data',
            help='Base directory for CSV files (default: reference_data)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Pass --dry-run to loaders that support it',
        )

    def handle(self, *args, **options):
        base = Path(options['base_dir'])
        dry_run = options.get('dry_run', False)
        if not base.exists():
            self.stdout.write(self.style.ERROR(f'Base dir not found: {base}'))
            return
        kwargs = {'verbosity': options.get('verbosity', 1)}
        if dry_run:
            self.stdout.write('DRY RUN – no changes will be saved.')
        # Step 1: Modifiers
        mod_path = base / 'modifiers.csv'
        if mod_path.exists():
            self.stdout.write('Loading modifiers (Step 1)...')
            call_command('load_cms_codes', modifiers=str(mod_path), **kwargs)
        else:
            self.stdout.write(self.style.WARNING(f'Skip modifiers: {mod_path} not found'))
        # Step 2: CPT/HCPCS + MPFS RVU
        pprrvu_path = base / 'PPRRVU25_JAN.csv'
        if pprrvu_path.exists():
            self.stdout.write('Loading PPRRVU → RefCptHcpcsCode + RefMpfsRvu (Step 2)...')
            call_command('load_pprrvu', path=str(pprrvu_path), year=2025, dry_run=dry_run, **kwargs)
        else:
            self.stdout.write(self.style.WARNING(f'Skip PPRRVU: {pprrvu_path} not found'))
        # Step 3: GPCI
        gpci_path = base / 'GPCI2025.csv'
        if gpci_path.exists():
            self.stdout.write('Loading GPCI → RefGeoIndex (Step 3)...')
            call_command('load_gpci', path=str(gpci_path), year=2025, dry_run=dry_run, **kwargs)
        else:
            self.stdout.write(self.style.WARNING(f'Skip GPCI: {gpci_path} not found'))
        self.stdout.write(self.style.SUCCESS('Reference data load complete.'))
