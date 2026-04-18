from __future__ import annotations

import csv
import hashlib
import shutil
import uuid
from pathlib import Path
from typing import Any

from constants import LEGACY_RECORD_HEADERS, RECORD_STATUS_FORFEITED
from utils import CSV_ENCODING, current_timestamp_for_filename, ensure_dir


class CSVManager:
    def __init__(
        self,
        *,
        csv_path: Path,
        backup_dir: Path,
        snapshot_dir: Path,
        logger: Any,
    ) -> None:
        self.csv_path = csv_path
        self.backup_dir = backup_dir
        self.snapshot_dir = snapshot_dir
        self.logger = logger
        self.ensure_legacy_storage()

    def ensure_legacy_storage(self) -> None:
        ensure_dir(self.csv_path.parent)
        ensure_dir(self.backup_dir)
        ensure_dir(self.snapshot_dir)
        if self.csv_path.exists():
            return
        with self.csv_path.open("w", encoding=CSV_ENCODING, newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=LEGACY_RECORD_HEADERS)
            writer.writeheader()

    def load_legacy_records(self) -> list[dict[str, str]]:
        self.ensure_legacy_storage()
        if not self.csv_path.exists():
            return []

        with self.csv_path.open("r", encoding=CSV_ENCODING, newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None:
                return []
            missing = [header for header in LEGACY_RECORD_HEADERS if header not in reader.fieldnames]
            if missing:
                self.logger.warning("Legacy CSV missing expected columns: %s", ", ".join(missing))
                return []

            records: list[dict[str, str]] = []
            for row in reader:
                if row is None:
                    continue
                normalized = {
                    header: str(row.get(header, "") or "").strip()
                    for header in LEGACY_RECORD_HEADERS
                }
                if not any(normalized.values()):
                    continue
                records.append(normalized)
            return records

    def backup_legacy_file(self, prefix: str) -> Path | None:
        if not self.csv_path.exists():
            return None
        target_dir = ensure_dir(self.backup_dir / "legacy_csv")
        target = target_dir / f"{prefix}_{current_timestamp_for_filename()}{self.csv_path.suffix or '.csv'}"
        shutil.copy2(self.csv_path, target)
        return target

    def store_raw_snapshot(self, raw_bytes: bytes, *, prefix: str) -> tuple[Path, str]:
        ensure_dir(self.snapshot_dir)
        checksum = hashlib.sha256(raw_bytes).hexdigest()
        target = self.snapshot_dir / f"{prefix}_{current_timestamp_for_filename()}_{checksum[:12]}.csv"
        target.write_bytes(raw_bytes)
        return target, checksum

    def export_records_csv(self, records: list[dict[str, object]], export_path: Path) -> Path:
        export_headers = [
            "public_id",
            "candidate_login_id",
            "application_number",
            "title_display",
            "name",
            "phone_number",
            "status",
            "short_note",
            "created_at",
            "updated_at",
        ]
        ensure_dir(export_path.parent)
        with export_path.open("w", encoding=CSV_ENCODING, newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=export_headers)
            writer.writeheader()
            for record in records:
                writer.writerow(
                    {
                        "public_id": str(record.get("public_id", "")),
                        "candidate_login_id": str(record.get("candidate_login_id", "")),
                        "application_number": str(record.get("application_number", "")),
                        "title_display": str(record.get("title_display", "")),
                        "name": str(record.get("name", "")),
                        "phone_number": str(record.get("phone_number", "")),
                        "status": str(record.get("status", "")),
                        "short_note": str(record.get("short_note", "")),
                        "created_at": str(record.get("created_at", "")),
                        "updated_at": str(record.get("updated_at", "")),
                    }
                )
        return export_path

    def generate_record_public_id(self) -> str:
        return f"REC-{uuid.uuid4().hex[:12].upper()}"

    def map_legacy_status(self, status: str) -> str:
        normalized = status.strip()
        if normalized.lower() == "close":
            return RECORD_STATUS_FORFEITED
        if normalized:
            return normalized
        return "Open"
