"""
Load procedure codes (and optionally modifiers) from CSV.
Usage:
  python manage.py load_cms_codes --path path/to/codes.csv
  python manage.py load_cms_codes --path path/to/codes.csv --modifiers path/to/modifiers.csv

CSV for procedure codes: code_id, code_type, description, work_rvu, pe_rvu, mp_rvu (optional).
  code_id (required), code_type (default CPT), description (optional), work_rvu (optional).
CSV for modifiers: modifier_code, description, percentage_adjustment (optional).
"""
import csv
from decimal import Decimal
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import transaction

from core.models import RefProcedureCode, RefModifier


def _decimal(s, default=None):
    if s is None or str(s).strip() == '':
        return default
    try:
        return Decimal(str(s).strip())
    except Exception:
        return default


class Command(BaseCommand):
    help = 'Load procedure codes (and optionally modifiers) from CSV files.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--path',
            type=str,
            help='Path to procedure codes CSV (columns: code_id, code_type, description, work_rvu, pe_rvu, mp_rvu)',
        )
        parser.add_argument(
            '--modifiers',
            type=str,
            default=None,
            help='Path to modifiers CSV (columns: modifier_code, description, percentage_adjustment)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Print what would be done without writing to DB',
        )

    def handle(self, *args, **options):
        path = options.get('path')
        modifiers_path = options.get('modifiers')
        dry_run = options.get('dry_run', False)
        if not path and not modifiers_path:
            self.stdout.write(self.style.ERROR('Provide at least --path or --modifiers.'))
            return
        if dry_run:
            self.stdout.write('DRY RUN – no changes will be saved.')
        codes_loaded = 0
        mods_loaded = 0
        if path:
            p = Path(path)
            if not p.exists():
                self.stdout.write(self.style.ERROR(f'File not found: {path}'))
                return
            with open(p, newline='', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                rows = list(reader)
            with transaction.atomic():
                for row in rows:
                    code_id = (row.get('code_id') or '').strip()
                    if not code_id:
                        continue
                    code_type = (row.get('code_type') or 'CPT').strip() or 'CPT'
                    description = (row.get('description') or '').strip() or None
                    work_rvu = _decimal(row.get('work_rvu'), Decimal('0.0000'))
                    pe_rvu = _decimal(row.get('pe_rvu'), Decimal('0.0000'))
                    mp_rvu = _decimal(row.get('mp_rvu'), Decimal('0.0000'))
                    if dry_run:
                        self.stdout.write(f'Would upsert: {code_id} ({code_type}) {description or ""}')
                        codes_loaded += 1
                        continue
                    RefProcedureCode.objects.update_or_create(
                        code_id=code_id,
                        defaults={
                            'code_type': code_type,
                            'description': description,
                            'work_rvu': work_rvu,
                            'pe_rvu': pe_rvu,
                            'mp_rvu': mp_rvu,
                        },
                    )
                    codes_loaded += 1
            self.stdout.write(self.style.SUCCESS(f'Procedure codes loaded/updated: {codes_loaded}'))
        if modifiers_path:
            p = Path(modifiers_path)
            if not p.exists():
                self.stdout.write(self.style.ERROR(f'File not found: {modifiers_path}'))
                return
            with open(p, newline='', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                rows = list(reader)
            with transaction.atomic():
                for row in rows:
                    modifier_code = (row.get('modifier_code') or '').strip()
                    if not modifier_code:
                        continue
                    description = (row.get('description') or '').strip() or None
                    pct = _decimal(row.get('percentage_adjustment'), Decimal('100.00'))
                    if dry_run:
                        self.stdout.write(f'Would upsert modifier: {modifier_code} {description or ""}')
                        mods_loaded += 1
                        continue
                    RefModifier.objects.update_or_create(
                        modifier_code=modifier_code,
                        defaults={
                            'description': description,
                            'percentage_adjustment': pct,
                        },
                    )
                    mods_loaded += 1
            self.stdout.write(self.style.SUCCESS(f'Modifiers loaded/updated: {mods_loaded}'))
