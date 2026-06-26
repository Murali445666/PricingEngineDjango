"""
Load CPT/HCPCS master (RefCptHcpcsCode) and MPFS RVU (RefMpfsRvu) from PPRRVU CSV (e.g. PPRRVU25_JAN.csv).
Skips first 9 rows. RefCptHcpcsCode: col 0=code, col 2=description, col 3=status_indicator.
RefMpfsRvu: col 0=code, col 3=status_indicator, col 5=work_rvu, col 6=pe_rvu, col 10=mp_rvu, col 11=total_rvu.
Uses year from --year or filename.

Usage:
  python manage.py load_pprrvu --path reference_data/PPRRVU25_JAN.csv
  python manage.py load_pprrvu --path reference_data/PPRRVU25_JAN.csv --year 2025
"""
import csv
import re
from decimal import Decimal
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import transaction

from core.models import RefCptHcpcsCode, RefMpfsRvu


def _decimal(s, default=None):
    if s is None or str(s).strip() == '':
        return default
    try:
        return Decimal(str(s).strip())
    except Exception:
        return default


def _year_from_path(path: Path) -> int | None:
    """Try to infer year from filename, e.g. PPRRVU25_JAN.csv -> 2025."""
    m = re.search(r'(?:PPRRVU|RVU)?(\d{2})[_\.]', path.name, re.I)
    if m:
        yy = int(m.group(1))
        return 2000 + yy if yy < 90 else 1900 + yy
    return None


class Command(BaseCommand):
    help = 'Load CPT/HCPCS master and MPFS RVU from PPRRVU CSV (Step 2).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--path',
            type=str,
            required=True,
            help='Path to PPRRVU CSV (e.g. reference_data/PPRRVU25_JAN.csv)',
        )
        parser.add_argument(
            '--year',
            type=int,
            default=None,
            help='RVU year (default: from filename or 2025)',
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
        skip_rows = 9
        codes_loaded = 0
        rvu_loaded = 0
        with open(path, newline='', encoding='utf-8-sig') as f:
            reader = csv.reader(f)
            for _ in range(skip_rows):
                next(reader, None)
            for row in reader:
                if len(row) < 12:
                    continue
                code = (row[0] or '').strip()
                if not code:
                    continue
                description = (row[2] or '').strip() or None
                status_indicator = (row[3] or '').strip() or None
                work_rvu = _decimal(row[5], Decimal('0.0000'))
                pe_rvu = _decimal(row[6], Decimal('0.0000'))
                mp_rvu = _decimal(row[10], Decimal('0.0000'))
                total_rvu = _decimal(row[11], None)
                if dry_run:
                    self.stdout.write(f'Would upsert: {code} year={year} work={work_rvu} pe={pe_rvu} mp={mp_rvu} total={total_rvu}')
                    codes_loaded += 1
                    rvu_loaded += 1
                    continue
                RefCptHcpcsCode.objects.update_or_create(
                    code=code,
                    defaults={
                        'code_type': 'HCPCS',
                        'description': description,
                        'status_indicator': status_indicator,
                        'effective_year': year,
                    },
                )
                codes_loaded += 1
                RefMpfsRvu.objects.update_or_create(
                    code=code,
                    year=year,
                    defaults={
                        'status_indicator': status_indicator,
                        'work_rvu': work_rvu,
                        'pe_rvu': pe_rvu,
                        'mp_rvu': mp_rvu,
                        'total_rvu': total_rvu,
                    },
                )
                rvu_loaded += 1
        self.stdout.write(self.style.SUCCESS(
            f'RefCptHcpcsCode: {codes_loaded}, RefMpfsRvu: {rvu_loaded} (year={year})'
        ))
