"""
Load APC reference from CSV or Excel (Phase 2).
CSV columns: apc_code (required), description, relative_weight, status_indicator,
  payment_rate, year (required).
Excel: January 2025 Web Addendum B — use --year and optional --excel-skip-rows.

Usage:
  python manage.py load_apc --path path/to/apc.csv
  python manage.py load_apc --path "January 2025 Web Addendum B.12.31.24.xlsx" --year 2025
"""
import csv
from decimal import Decimal
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import transaction

from core.models import RefApc

# CMS OPPS Addendum B: HCPCS-to-APC mapping; each row has HCPCS Code, APC (may be empty), etc.
# We load only rows where APC is non-empty (one ref_apc row per unique APC).
APC_FIELD_ALIASES = {
    "apc_code": ["APC", "APC Code", "APCCode", "HCPCS/APC"],
    "description": ["Short Descriptor", "Description", "APC Description", "Title"],
    "relative_weight": ["Relative Weight", "RW", "Rel Weight", "Weight"],
    "status_indicator": ["SI", "Status Indicator", "Status Ind", "Status"],
    "payment_rate": ["Payment Rate", "Payment Amount", "Payment", "Rate", "Unadjusted Payment"],
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
        return int(Decimal(str(s).strip()))
    except Exception:
        return default


def _normalize_cell(val):
    """Strip value; treat None, empty string, or whitespace-only as empty."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return val
    s = str(val).strip()
    return s if s else None


def _read_rows(path: Path, excel_skip_rows: int | None, excel_sheet: int = 0):
    suffix = path.suffix.lower()
    if suffix in (".xlsx", ".xls"):
        from core.management.utils.excel_reader import read_excel_to_dicts, map_row
        # Dynamic header finder: use row that starts with "HCPCS Code" as header (unless skip_rows set)
        kwargs = {"path": path, "sheet_index": excel_sheet}
        if excel_skip_rows is None:
            kwargs["find_header_sentinel"] = "HCPCS Code"
            kwargs["skip_rows"] = 0
        else:
            kwargs["skip_rows"] = excel_skip_rows
        raw = read_excel_to_dicts(**kwargs)
        return [map_row(r, APC_FIELD_ALIASES) for r in raw]
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


class Command(BaseCommand):
    help = "Load APC reference from CSV or Excel (e.g. January 2025 Web Addendum B)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--path",
            type=str,
            required=True,
            help="Path to APC CSV or Excel (OPPS Addendum B)",
        )
        parser.add_argument(
            "--year",
            type=int,
            default=None,
            help="Year for APC (required for Excel; optional for CSV if column present)",
        )
        parser.add_argument(
            "--excel-skip-rows",
            type=int,
            default=None,
            metavar="N",
            help="Override: skip N rows before header. If not set, header row is found by searching for 'HCPCS Code' in the first column.",
        )
        parser.add_argument(
            "--excel-sheet",
            type=int,
            default=0,
            help="Zero-based sheet index (default 0). Use if APC data is on another sheet.",
        )
        parser.add_argument(
            "--show-headers",
            action="store_true",
            help="Print first row headers and a sample row, then exit (for debugging).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print what would be done without writing to DB",
        )

    def handle(self, *args, **options):
        path = Path(options["path"])
        if not path.is_absolute():
            # Try relative to cwd, then reference_data
            if not path.exists():
                alt = Path("reference_data") / path.name
                if alt.exists():
                    path = alt
        if not path.exists():
            self.stdout.write(self.style.ERROR(f"File not found: {path}"))
            return
        dry_run = options.get("dry_run", False)
        year_arg = options.get("year")
        excel_skip_rows = options.get("excel_skip_rows")
        excel_sheet = options.get("excel_sheet", 0)
        show_headers = options.get("show_headers", False)
        if dry_run:
            self.stdout.write("DRY RUN – no changes will be saved.")
        rows = _read_rows(path, excel_skip_rows, excel_sheet)
        if show_headers:
            self.stdout.write(f"Total rows read: {len(rows)}")
            if rows:
                first = rows[0]
                self.stdout.write("Mapped keys: " + ", ".join(first.keys()))
                self.stdout.write("First row (mapped): " + str(first))
                apc_empty = (first.get("apc_code") is None or str(first.get("apc_code", "")).strip() == "")
                if apc_empty:
                    self.stdout.write(self.style.WARNING("First row has empty APC — only rows with non-empty APC are loaded."))
            else:
                self.stdout.write(self.style.WARNING("No data rows. Check --excel-skip-rows and --excel-sheet."))
            return
        count = 0
        skipped_no_apc = 0
        with transaction.atomic():
            for row in rows:
                apc_code = row.get("apc_code")
                # Value stripping: treat None, "", and whitespace-only (e.g. " ") as empty
                apc_code = _normalize_cell(apc_code)
                if apc_code is None:
                    skipped_no_apc += 1
                    continue
                if isinstance(apc_code, (int, float)):
                    apc_code = str(int(apc_code))
                else:
                    apc_code = str(apc_code).strip()
                if not apc_code:
                    skipped_no_apc += 1
                    continue
                year = _int(row.get("year")) if row.get("year") is not None else year_arg
                if year is None:
                    self.stdout.write(self.style.WARNING(f"Skipping {apc_code}: year required (use --year for Excel)"))
                    continue
                description = (row.get("description") or "").strip() or None
                if description and len(description) > 255:
                    description = description[:255]
                relative_weight = _decimal(row.get("relative_weight"), Decimal("0"))
                status_indicator = (row.get("status_indicator") or "")
                if status_indicator is not None:
                    status_indicator = str(status_indicator).strip() or None
                if status_indicator and len(status_indicator) > 10:
                    status_indicator = status_indicator[:10]
                payment_rate = _decimal(row.get("payment_rate"))
                if dry_run:
                    self.stdout.write(f"Would upsert APC: {apc_code} year={year} rw={relative_weight}")
                    count += 1
                    continue
                RefApc.objects.update_or_create(
                    apc_code=apc_code,
                    defaults={
                        "description": description,
                        "relative_weight": relative_weight,
                        "status_indicator": status_indicator,
                        "payment_rate": payment_rate,
                        "year": year,
                    },
                )
                count += 1
        self.stdout.write(self.style.SUCCESS(f"APC rows loaded/updated: {count}"))
        if count == 0 and skipped_no_apc > 0:
            self.stdout.write(
                self.style.WARNING(
                    f"All {skipped_no_apc} rows had empty APC column. "
                    "Addendum B lists HCPCS codes; APC is filled only for rows that map to an APC. "
                    "If your file has APC data on another sheet, try --excel-sheet 1 or 2. "
                    "Use --show-headers to see which columns are being read."
                )
            )
