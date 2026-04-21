from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from utils import current_timestamp, safe_json_load, safe_json_write


class VersionHistoryManager:
    def __init__(self, history_path: Path, logger: logging.Logger) -> None:
        self.history_path = history_path
        self.logger = logger

    def _load_store(self) -> dict[str, list[dict[str, Any]]]:
        payload = safe_json_load(
            self.history_path,
            {},
            logger=self.logger,
            invalid_backup_dir=self.history_path.parent / "invalid",
        )
        normalized: dict[str, list[dict[str, Any]]] = {}
        for record_id, entries in payload.items():
            if not isinstance(entries, list):
                continue
            normalized_entries: list[dict[str, Any]] = []
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                try:
                    version = int(entry.get("version", 0))
                except (TypeError, ValueError):
                    continue
                snapshot = entry.get("snapshot", {})
                if not isinstance(snapshot, dict):
                    snapshot = {}
                normalized_entries.append(
                    {
                        "version": version,
                        "change": str(entry.get("change", "")).strip() or "UNKNOWN",
                        "changed_at": str(entry.get("changed_at", "")).strip(),
                        "snapshot": {str(key): str(value) for key, value in snapshot.items()},
                    }
                )
            normalized_entries.sort(key=lambda item: item["version"])
            normalized[str(record_id)] = normalized_entries
        return normalized

    def _save_store(self, store: dict[str, list[dict[str, Any]]]) -> None:
        safe_json_write(self.history_path, store)

    def _normalize_snapshot(self, snapshot: dict[str, Any]) -> dict[str, str]:
        return {str(key): str(value).strip() for key, value in snapshot.items()}

    def ensure_baseline(self, records: list[dict[str, str]], change: str = "LEGACY_MIGRATION") -> None:
        store = self._load_store()
        changed = False
        for record in records:
            record_id = record.get("record_id", "").strip()
            if not record_id or store.get(record_id):
                continue
            store[record_id] = [
                {
                    "version": 1,
                    "change": change,
                    "changed_at": record.get("updated_at", "").strip() or current_timestamp(),
                    "snapshot": self._normalize_snapshot(record),
                }
            ]
            changed = True
        if changed:
            self._save_store(store)

    def list_versions(self, record_id: str) -> list[dict[str, Any]]:
        store = self._load_store()
        entries = store.get(record_id, [])
        return sorted(entries, key=lambda item: item["version"], reverse=True)

    def add_version(self, record_id: str, change: str, snapshot: dict[str, Any], changed_at: str | None = None) -> dict[str, Any]:
        store = self._load_store()
        entries = store.setdefault(record_id, [])
        next_version = max((int(entry.get("version", 0)) for entry in entries), default=0) + 1
        entry = {
            "version": next_version,
            "change": change,
            "changed_at": changed_at or current_timestamp(),
            "snapshot": self._normalize_snapshot(snapshot),
        }
        entries.append(entry)
        entries.sort(key=lambda item: item["version"])
        self._save_store(store)
        return entry

    def get_snapshot(self, record_id: str, version_number: int) -> dict[str, str] | None:
        for entry in self.list_versions(record_id):
            if int(entry.get("version", 0)) == version_number:
                snapshot = entry.get("snapshot", {})
                if isinstance(snapshot, dict):
                    return {str(key): str(value) for key, value in snapshot.items()}
        return None
