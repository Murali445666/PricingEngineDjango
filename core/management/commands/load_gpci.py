"""
Load GPCI (geographic practice cost indices) into RefGeoIndex (Step 3).
Expects CMS-style CSV: skip first 3 rows; columns MAC, State, Locality Number,
Locality Name, PW GPCI, PE GPCI, MP GPCI. locality_code = State + Locality Number.

Usage:
  python manage.py load_gpci --path reference_data/GPCI2025.csv
  python manage.py load_gpci --path reference_data/GPCI2025.csv --year 2025
"""
import csv
import re
from decimal import Decimal
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import transaction

from core.models import RefGeoIndex


def _decimal(s, default=None):
    if s is None or str(s).strip() == '':
        return default
    try:
        return Decimal(str(s).strip())
    except Exception:
        return default


def _year_from_path(path: Path) -> int | None:
    """Infer year from filename, e.g. GPCI2025.csv -> 2025."""
    m = re.search(r'(\d{4})', path.name)
    return int(m.group(1)) if m else None


class Command(BaseCommand):
    help = 'Load GPCI data from CMS CSV into RefGeoIndex (Step 3).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--path',
            type=str,
            required=True,
            help='Path to GPCI CSV (e.g. reference_data/GPCI2025.csv)',
        )
        parser.add_argument(
            '--year',
            type=int,
            default=None,
            help='GPCI year (default: from filename or 2025)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Print what would be done without writing to DB',
        )

    def handle(self, *args, **options):
        path = Path(options['path'])
        if not path.exists():
            self.stdout.write(self.style.ERROR(f'File not found: {path}'))
            return
        year = options.get('year') or _year_from_path(path) or 2025
        dry_run = options.get('dry_run', False)
        if dry_run:
            self.stdout.write('DRY RUN – no changes will be saved.')
        skip_rows = 3
        loaded = 0
        with open(path, newline='', encoding='utf-8-sig') as f:
            reader = csv.reader(f)
            for _ in range(skip_rows):
                next(reader, None)
            for row in reader:
                if len(row) < 7:
                    continue
                state = (row[1] or '').strip()
                loc_num = (row[2] or '').strip()
                locality_name = (row[3] or '').strip() or None
                gpci_w = _decimal(row[4], None)
                gpci_pe = _decimal(row[5], None)
                gpci_mp = _decimal(row[6], None)
                if gpci_w is None and gpci_pe is None and gpci_mp is None:
                    continue
                locality_code = f"{state}{loc_num}" if state and loc_num is not None else state or loc_num or None
                if not locality_code:
                    continue
                if dry_run:
                    self.stdout.write(f'Would upsert: {locality_code} {locality_name} w={gpci_w} pe={gpci_pe} mp={gpci_mp}')
                    loaded += 1
                    continue
                RefGeoIndex.objects.update_or_create(
                    locality_code=locality_code,
                    year=year,
                    defaults={
                        'description': locality_name,
                        'gpci_work': gpci_w,
                        'gpci_pe': gpci_pe,
                        'gpci_mp': gpci_mp,
                    },
                )
                loaded += 1
        self.stdout.write(self.style.SUCCESS(f'RefGeoIndex loaded/updated: {loaded} rows (year={year})'))
