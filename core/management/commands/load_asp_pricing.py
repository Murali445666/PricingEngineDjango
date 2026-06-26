"""
Load ASP pricing from CSV or Excel (Phase 3).
CSV columns: hcpcs_code (required), quarter (required), asp, payment_limit (optional).
Excel: January 2025 ASP NDC-HCPCS Crosswalk or ASP Drug Pricing — use --quarter (e.g. 2025-Q1) if not in file.

Usage:
  python manage.py load_asp_pricing --path path/to/asp.csv
  python manage.py load_asp_pricing --path "January 2025 ASP NDC-HCPCS Crosswalk updated 052725.xls" --quarter 2025-Q1
"""
import csv
import re
from decimal import Decimal
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import transaction

from core.models import RefAspPricing

# ASP / NDC-HCPCS crosswalk common column name variants
ASP_FIELD_ALIASES = {
    "hcpcs_code": ["HCPCS", "HCPCS Code", "HCPCS Code / J-Code", "J-Code", "Code"],
    "quarter": ["Quarter", "Quarter/Year", "Payment Quarter", "Qtr"],
    "asp": ["ASP", "Average Sales Price", "ASP Price", "Unit ASP"],
    "payment_limit": ["Payment Limit", "Payment Limit Amount", "Limiting Charge", "Limit"],
}


def _decimal(s, default=None):
    if s is None or (isinstance(s, str) and str(s).strip() == ""):
        return default
    try:
        return Decimal(str(s).strip())
    except Exception:
        return default


def _infer_quarter_from_path(path: Path) -> str | None:
    """Infer quarter from filename, e.g. 'January 2025' -> 2025-Q1."""
    name = path.stem
    m = re.search(r"(?:January|Jan)\s*(\d{4})", name, re.I)
    if m:
        return f"{m.group(1)}-Q1"
    m = re.search(r"(\d{4})[-_]Q([1-4])", name, re.I)
    if m:
        return f"{m.group(1)}-Q{m.group(2)}"
    m = re.search(r"(\d{4})", name)
    if m:
        return f"{m.group(1)}-Q1"
    return None


def _read_rows(path: Path, excel_skip_rows: int):
    suffix = path.suffix.lower()
    if suffix in (".xlsx", ".xls"):
        from core.management.utils.excel_reader import read_excel_to_dicts, map_row
        raw = read_excel_to_dicts(path, skip_rows=excel_skip_rows)
        return [map_row(r, ASP_FIELD_ALIASES) for r in raw]
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


class Command(BaseCommand):
    help = "Load ASP pricing from CSV or Excel (e.g. ASP NDC-HCPCS Crosswalk)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--path",
            type=str,
            required=True,
            help="Path to ASP CSV or Excel",
        )
        parser.add_argument(
            "--quarter",
            type=str,
            default=None,
            help="Quarter for pricing (e.g. 2025-Q1); required for Excel if file has no quarter column",
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
        quarter_arg = (options.get("quarter") or "").strip() or None
        if not quarter_arg:
            quarter_arg = _infer_quarter_from_path(path)
        excel_skip_rows = options.get("excel_skip_rows", 0)
        if dry_run:
            self.stdout.write("DRY RUN – no changes will be saved.")
        rows = _read_rows(path, excel_skip_rows)
        count = 0
        with transaction.atomic():
            for row in rows:
                hcpcs_code = (row.get("hcpcs_code") or "")
                if isinstance(hcpcs_code, (int, float)):
                    hcpcs_code = str(int(hcpcs_code))
                else:
                    hcpcs_code = str(hcpcs_code).strip()
                if not hcpcs_code:
                    continue
                quarter = (row.get("quarter") or "")
                if isinstance(quarter, (int, float)):
                    quarter = str(int(quarter)) if quarter is not None else ""
                else:
                    quarter = str(quarter).strip() if quarter is not None else ""
                if not quarter:
                    quarter = quarter_arg
                if not quarter:
                    self.stdout.write(
                        self.style.WARNING(f"Skipping {hcpcs_code}: quarter required (use --quarter or add column)")
                    )
                    continue
                asp = _decimal(row.get("asp"))
                if asp is None:
                    continue
                payment_limit = _decimal(row.get("payment_limit"))
                if dry_run:
                    self.stdout.write(f"Would upsert ASP: {hcpcs_code} {quarter} asp={asp}")
                    count += 1
                    continue
                RefAspPricing.objects.update_or_create(
                    hcpcs_code=hcpcs_code,
                    quarter=quarter,
                    defaults={"asp": asp, "payment_limit": payment_limit},
                )
                count += 1
        self.stdout.write(self.style.SUCCESS(f"ASP pricing rows loaded/updated: {count}"))
