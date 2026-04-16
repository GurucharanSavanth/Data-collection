from __future__ import annotations

import csv
import logging
import os
import tempfile
import uuid
from pathlib import Path
from typing import Any

from utils import CSV_ENCODING, backup_file, current_timestamp, ensure_dir


LEGACY_HEADERS = (
    "record_id",
    "title",
    "category",
    "status",
    "notes",
    "created_at",
    "updated_at",
)


class CSVManager:
    def __init__(
        self,
        csv_path: Path,
        backup_dir: Path,
        temp_dir: Path,
        headers: list[str],
        logger: logging.Logger,
    ) -> None:
        self.csv_path = csv_path
        self.backup_dir = backup_dir
        self.temp_dir = temp_dir
        self.headers = headers
        self.logger = logger
        self.ensure_storage()

    def ensure_storage(self) -> None:
        ensure_dir(self.csv_path.parent)
        ensure_dir(self.backup_dir)
        ensure_dir(self.temp_dir)

        if not self.csv_path.exists() or self.csv_path.stat().st_size == 0:
            self._write_header_only()
            return

        with self.csv_path.open("r", encoding=CSV_ENCODING, newline="") as handle:
            reader = csv.reader(handle)
            header = tuple(next(reader, []))

        if list(header) == self.headers:
            return

        if header == LEGACY_HEADERS:
            self.logger.info("Migrating legacy CSV schema in %s", self.csv_path)
            self._migrate_legacy_csv()
            return

        self.logger.warning("CSV header mismatch detected in %s", self.csv_path)
        backup_file(self.csv_path, self.backup_dir, "records_header_mismatch")
        self._write_header_only()

    def _write_header_only(self) -> None:
        with self.csv_path.open("w", encoding=CSV_ENCODING, newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=self.headers)
            writer.writeheader()

    def _normalize_record(self, record: dict[str, Any], allow_generated_id: bool = False) -> dict[str, str]:
        normalized = {column: str(record.get(column, "")).strip() for column in self.headers}
        if not normalized["record_id"]:
            if allow_generated_id:
                normalized["record_id"] = self.generate_record_id()
            else:
                raise ValueError("record_id is required")
        return normalized

    def _write_records_atomically(self, normalized_records: list[dict[str, str]], backup_reason: str, create_backup: bool) -> None:
        temp_handle, temp_name = tempfile.mkstemp(
            prefix="records_",
            suffix=".csv",
            dir=str(self.temp_dir),
            text=True,
        )
        temp_path = Path(temp_name)

        try:
            with os.fdopen(temp_handle, "w", encoding=CSV_ENCODING, newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=self.headers)
                writer.writeheader()
                writer.writerows(normalized_records)

            with temp_path.open("r", encoding=CSV_ENCODING, newline="") as verify_handle:
                reader = csv.DictReader(verify_handle)
                if reader.fieldnames != self.headers:
                    raise ValueError("Temporary CSV validation failed due to header mismatch")
                for row in reader:
                    if row is None or None in row:
                        raise ValueError("Temporary CSV validation failed due to malformed row")

            if create_backup and self.csv_path.exists():
                backup_file(self.csv_path, self.backup_dir, f"records_{backup_reason}")

            os.replace(temp_path, self.csv_path)
        except Exception:
            self.logger.exception("Failed to write CSV data")
            temp_path.unlink(missing_ok=True)
            raise

    def _migrate_legacy_csv(self) -> None:
        with self.csv_path.open("r", encoding=CSV_ENCODING, newline="") as handle:
            reader = csv.DictReader(handle)
            migrated_records = []
            for row in reader:
                migrated_records.append(
                    self._normalize_record(
                        {
                            "record_id": row.get("record_id", ""),
                            "title": row.get("title", ""),
                            "category": row.get("category", ""),
                            "name": "",
                            "phone_number": "",
                            "status": row.get("status", "Open"),
                            "short_note": row.get("notes", ""),
                            "created_at": row.get("created_at", ""),
                            "updated_at": row.get("updated_at", ""),
                        },
                        allow_generated_id=True,
                    )
                )

        self._write_records_atomically(migrated_records, backup_reason="schema_upgrade", create_backup=True)

    def load_records(self) -> list[dict[str, str]]:
        self.ensure_storage()
        records: list[dict[str, str]] = []

        with self.csv_path.open("r", encoding=CSV_ENCODING, newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames != self.headers:
                self.logger.warning("CSV headers invalid during load, resetting file")
                backup_file(self.csv_path, self.backup_dir, "records_invalid_headers")
                self._write_header_only()
                return []

            for index, row in enumerate(reader, start=2):
                if row is None or None in row:
                    self.logger.warning("Skipping malformed CSV row %s", index)
                    continue
                try:
                    normalized = self._normalize_record(row)
                    records.append(normalized)
                except Exception:
                    self.logger.exception("Failed to normalize CSV row %s", index)

        records.sort(key=lambda item: item.get("updated_at", ""), reverse=True)
        return records

    def save_records(self, records: list[dict[str, Any]], backup_reason: str) -> None:
        self.ensure_storage()
        normalized_records = [self._normalize_record(record) for record in records]
        self._write_records_atomically(normalized_records, backup_reason=backup_reason, create_backup=True)

    def generate_record_id(self) -> str:
        return f"REC-{uuid.uuid4().hex[:12].upper()}"

    def build_new_record(self, form_data: dict[str, str]) -> dict[str, str]:
        timestamp = current_timestamp()
        record = {
            "record_id": self.generate_record_id(),
            "title": form_data.get("title", "").strip(),
            "category": form_data.get("category", "").strip(),
            "name": form_data.get("name", "").strip(),
            "phone_number": form_data.get("phone_number", "").strip(),
            "status": form_data.get("status", "").strip(),
            "short_note": form_data.get("short_note", "").strip(),
            "created_at": timestamp,
            "updated_at": timestamp,
        }
        return self._normalize_record(record)

    def build_updated_record(self, record_id: str, form_data: dict[str, str], existing_record: dict[str, str]) -> dict[str, str]:
        updated = dict(existing_record)
        updated["record_id"] = record_id
        updated["title"] = form_data.get("title", "").strip()
        updated["category"] = form_data.get("category", "").strip()
        updated["name"] = form_data.get("name", "").strip()
        updated["phone_number"] = form_data.get("phone_number", "").strip()
        updated["status"] = form_data.get("status", "").strip()
        updated["short_note"] = form_data.get("short_note", "").strip()
        updated["created_at"] = existing_record.get("created_at", "") or current_timestamp()
        updated["updated_at"] = current_timestamp()
        return self._normalize_record(updated)

    def find_record(self, records: list[dict[str, str]], record_id: str) -> dict[str, str] | None:
        for record in records:
            if record.get("record_id") == record_id:
                return record
        return None

    def filter_records(self, records: list[dict[str, str]], search_text: str) -> list[dict[str, str]]:
        query = search_text.strip().lower()
        if not query:
            return list(records)

        filtered: list[dict[str, str]] = []
        for record in records:
            haystack = " ".join(
                [
                    record.get("record_id", ""),
                    record.get("title", ""),
                    record.get("category", ""),
                    record.get("name", ""),
                    record.get("phone_number", ""),
                    record.get("status", ""),
                    record.get("short_note", ""),
                ]
            ).lower()
            if query in haystack:
                filtered.append(record)
        return filtered

    def get_unique_values(self, records: list[dict[str, str]], field_name: str) -> list[str]:
        values = {record.get(field_name, "").strip() for record in records if record.get(field_name, "").strip()}
        return sorted(values, key=str.lower)
