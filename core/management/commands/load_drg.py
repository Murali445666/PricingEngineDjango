"""
Load DRG reference from CSV or Excel (Phase 2).
CSV columns: drg_code (required), description, relative_weight, geometric_mean_los,
  arithmetic_mean_los, mdc, year (required).
Excel: FY2025 IPPS Final Rule Table 5.xlsx — use --year and optional --excel-skip-rows if header is not row 0.

Usage:
  python manage.py load_drg --path path/to/drg.csv
  python manage.py load_drg --path "FY2025 IPPS Final Rule and Correction Notice Table 5.xlsx" --year 2025
"""
import csv
from decimal import Decimal
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import transaction

from core.models import RefDrg

# CMS IPPS Table 5 common column name variants
DRG_FIELD_ALIASES = {
    "drg_code": ["MS-DRG", "MS-DRG No", "DRG", "DRG Code", "MSDRG", "MS DRG"],
    "description": ["Title", "Description", "MS-DRG Title", "DRG Description"],
    "relative_weight": ["Relative Weight", "RW", "Rel Weight", "Weight"],
    "geometric_mean_los": ["Geometric Mean LOS", "Geo Mean LOS", "Geometric Mean Length of Stay"],
    "arithmetic_mean_los": ["Arithmetic Mean LOS", "Arith Mean LOS", "Arithmetic Mean Length of Stay"],
    "mdc": ["MDC", "Major Diagnostic Category"],
}


def _decimal(s, default=None):
    if s is None or (isinstance(s, str) and str(s).strip() == ""):
        return default
    try:
        return Decimal(str(s).strip())
    except Exception:
        return default


def _int(s, default=None):
    if s is None or (isinstance(s, str) and str(s).strip() == ""):
        return default
    try:
        return int(Decimal(str(s).strip()))  # handle 1.0 -> 1
    except Exception:
        return default


def _read_rows(path: Path, excel_skip_rows: int):
    suffix = path.suffix.lower()
    if suffix in (".xlsx", ".xls"):
        from core.management.utils.excel_reader import read_excel_to_dicts, map_row
        raw = read_excel_to_dicts(path, skip_rows=excel_skip_rows)
        return [map_row(r, DRG_FIELD_ALIASES) for r in raw]
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


class Command(BaseCommand):
    help = "Load DRG reference from CSV or Excel (e.g. FY2025 IPPS Table 5.xlsx)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--path",
            type=str,
            required=True,
            help="Path to DRG CSV or Excel (IPPS Table 5)",
        )
        parser.add_argument(
            "--year",
            type=int,
            default=None,
            help="Fiscal/year for DRG (required for Excel; optional for CSV if column present)",
        )
        parser.add_argument(
            "--excel-skip-rows",
            type=int,
            default=0,
            help="Number of rows to skip before header in Excel (default 0)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print what would be done without writing to DB",
        )

    def handle(self, *args, **options):
        path = Path(options["path"])
        if not path.exists():
            self.stdout.write(self.style.ERROR(f"File not found: {path}"))
            return
        dry_run = options.get("dry_run", False)
        year_arg = options.get("year")
        excel_skip_rows = options.get("excel_skip_rows", 0)
        if dry_run:
            self.stdout.write("DRY RUN – no changes will be saved.")
        rows = _read_rows(path, excel_skip_rows)
        count = 0
        with transaction.atomic():
            for row in rows:
                drg_code = (row.get("drg_code") or "")
                if isinstance(drg_code, (int, float)):
                    drg_code = str(int(drg_code)).zfill(3)
                else:
                    drg_code = str(drg_code).strip()
                if not drg_code:
                    continue
                year = _int(row.get("year")) if row.get("year") is not None else year_arg
                if year is None:
                    self.stdout.write(self.style.WARNING(f"Skipping {drg_code}: year required (use --year for Excel)"))
                    continue
                description = (row.get("description") or "").strip() or None
                if description and len(description) > 255:
                    description = description[:255]
                relative_weight = _decimal(row.get("relative_weight"), Decimal("0"))
                geometric_mean_los = _decimal(row.get("geometric_mean_los"))
                arithmetic_mean_los = _decimal(row.get("arithmetic_mean_los"))
                mdc = (row.get("mdc") or "")
                if mdc is not None:
                    mdc = str(mdc).strip() or None
                if dry_run:
                    self.stdout.write(f"Would upsert DRG: {drg_code} year={year} rw={relative_weight}")
                    count += 1
                    continue
                RefDrg.objects.update_or_create(
                    drg_code=drg_code,
                    defaults={
                        "description": description,
                        "relative_weight": relative_weight,
                        "geometric_mean_los": geometric_mean_los,
                        "arithmetic_mean_los": arithmetic_mean_los,
                        "mdc": mdc,
                        "year": year,
                    },
                )
                count += 1
        self.stdout.write(self.style.SUCCESS(f"DRG rows loaded/updated: {count}"))
