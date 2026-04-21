from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Any

from utils import current_timestamp, safe_json_load, safe_json_write


CANDIDATE_STORE_DEFAULT: dict[str, Any] = {
    "candidates": [],
}


class CandidateManager:
    def __init__(self, candidate_path: Path, logger: logging.Logger) -> None:
        self.candidate_path = candidate_path
        self.logger = logger

    def _load_store(self) -> dict[str, Any]:
        payload = safe_json_load(
            self.candidate_path,
            CANDIDATE_STORE_DEFAULT,
            logger=self.logger,
            invalid_backup_dir=self.candidate_path.parent / "invalid",
        )
        if not isinstance(payload.get("candidates"), list):
            payload["candidates"] = []
        return payload

    def _save_store(self, store: dict[str, Any]) -> None:
        safe_json_write(self.candidate_path, store)

    def normalize_display_name(self, display_name: str) -> str:
        return " ".join(str(display_name).strip().split())

    def generate_candidate_id(self) -> str:
        return f"CAN-{uuid.uuid4().hex[:12].upper()}"

    def _normalize_candidate(self, candidate: dict[str, Any], allow_generated_id: bool = False) -> dict[str, str]:
        candidate_id = str(candidate.get("candidate_id", "")).strip()
        if not candidate_id:
            if allow_generated_id:
                candidate_id = self.generate_candidate_id()
            else:
                raise ValueError("candidate_id is required")

        display_name = self.normalize_display_name(str(candidate.get("display_name", "")))
        if not display_name:
            raise ValueError("display_name is required")

        created_at = str(candidate.get("created_at", "")).strip() or current_timestamp()
        updated_at = str(candidate.get("updated_at", "")).strip() or created_at

        return {
            "candidate_id": candidate_id,
            "display_name": display_name,
            "archived_at": str(candidate.get("archived_at", "")).strip(),
            "created_at": created_at,
            "updated_at": updated_at,
        }

    def load_candidates(self) -> list[dict[str, str]]:
        store = self._load_store()
        candidates: list[dict[str, str]] = []
        for raw_candidate in store.get("candidates", []):
            if not isinstance(raw_candidate, dict):
                continue
            try:
                candidates.append(self._normalize_candidate(raw_candidate))
            except Exception:
                self.logger.exception("Failed to normalize candidate entry")
        candidates.sort(key=lambda item: (item.get("display_name", "").lower(), item.get("created_at", ""), item.get("candidate_id", "")))
        return candidates

    def save_candidates(self, candidates: list[dict[str, Any]]) -> None:
        normalized_candidates = [self._normalize_candidate(candidate, allow_generated_id=False) for candidate in candidates]
        normalized_candidates.sort(key=lambda item: (item.get("display_name", "").lower(), item.get("created_at", ""), item.get("candidate_id", "")))
        self._save_store({"candidates": normalized_candidates})

    def find_candidate(self, candidates: list[dict[str, str]], candidate_id: str) -> dict[str, str] | None:
        target_id = str(candidate_id).strip()
        for candidate in candidates:
            if candidate.get("candidate_id", "") == target_id:
                return candidate
        return None

    def find_candidates_by_name(
        self,
        candidates: list[dict[str, str]],
        display_name: str,
        *,
        active_only: bool = True,
        exclude_candidate_id: str = "",
    ) -> list[dict[str, str]]:
        normalized_name = self.normalize_display_name(display_name).casefold()
        excluded = str(exclude_candidate_id).strip()
        if not normalized_name:
            return []

        matches: list[dict[str, str]] = []
        for candidate in candidates:
            if excluded and candidate.get("candidate_id", "") == excluded:
                continue
            if active_only and candidate.get("archived_at", "").strip():
                continue
            if candidate.get("display_name", "").casefold() == normalized_name:
                matches.append(candidate)
        matches.sort(key=lambda item: (item.get("created_at", ""), item.get("candidate_id", "")))
        return matches

    def build_dropdown_options(
        self,
        candidates: list[dict[str, str]],
        *,
        view_mode: str = "Active",
    ) -> tuple[list[str], dict[str, str], dict[str, str]]:
        normalized_view_mode = str(view_mode).strip().lower() or "active"
        if normalized_view_mode == "archived":
            visible_candidates = [candidate for candidate in candidates if candidate.get("archived_at", "").strip()]
        elif normalized_view_mode == "all":
            visible_candidates = list(candidates)
        else:
            visible_candidates = [candidate for candidate in candidates if not candidate.get("archived_at", "").strip()]

        name_counts: dict[str, int] = {}
        for candidate in visible_candidates:
            key = candidate.get("display_name", "")
            name_counts[key] = name_counts.get(key, 0) + 1

        labels: list[str] = []
        candidate_id_by_label: dict[str, str] = {}
        candidate_label_by_id: dict[str, str] = {}
        for candidate in visible_candidates:
            label = candidate.get("display_name", "")
            if name_counts.get(label, 0) > 1:
                label = f"{label} [{candidate.get('candidate_id', '')[-6:]}]"
            if candidate.get("archived_at", "").strip():
                label = f"{label} (Archived)"
            labels.append(label)
            candidate_id_by_label[label] = candidate.get("candidate_id", "")
            candidate_label_by_id[candidate.get("candidate_id", "")] = label
        return labels, candidate_id_by_label, candidate_label_by_id

    def get_archived_candidates(self, candidates: list[dict[str, str]]) -> list[dict[str, str]]:
        archived_candidates = [candidate for candidate in candidates if candidate.get("archived_at", "").strip()]
        archived_candidates.sort(
            key=lambda item: (
                item.get("archived_at", ""),
                item.get("display_name", "").lower(),
                item.get("candidate_id", ""),
            ),
            reverse=True,
        )
        return archived_candidates

    def create_candidate(self, candidates: list[dict[str, str]], display_name: str) -> dict[str, str]:
        candidate = self._normalize_candidate(
            {
                "candidate_id": self.generate_candidate_id(),
                "display_name": display_name,
                "archived_at": "",
                "created_at": current_timestamp(),
                "updated_at": current_timestamp(),
            },
            allow_generated_id=False,
        )
        candidates.append(candidate)
        candidates.sort(key=lambda item: (item.get("display_name", "").lower(), item.get("created_at", ""), item.get("candidate_id", "")))
        return candidate

    def rename_candidate(self, candidates: list[dict[str, str]], candidate_id: str, display_name: str) -> dict[str, str]:
        candidate = self.find_candidate(candidates, candidate_id)
        if candidate is None:
            raise ValueError("Selected candidate no longer exists.")
        candidate["display_name"] = self.normalize_display_name(display_name)
        candidate["updated_at"] = current_timestamp()
        return candidate

    def archive_candidate(self, candidates: list[dict[str, str]], candidate_id: str) -> dict[str, str]:
        candidate = self.find_candidate(candidates, candidate_id)
        if candidate is None:
            raise ValueError("Selected candidate no longer exists.")
        timestamp = current_timestamp()
        candidate["archived_at"] = timestamp
        candidate["updated_at"] = timestamp
        return candidate

    def restore_candidate(self, candidates: list[dict[str, str]], candidate_id: str) -> dict[str, str]:
        candidate = self.find_candidate(candidates, candidate_id)
        if candidate is None:
            raise ValueError("Selected candidate no longer exists.")
        candidate["archived_at"] = ""
        candidate["updated_at"] = current_timestamp()
        return candidate

    def ensure_candidates_for_records(
        self,
        records: list[dict[str, str]],
    ) -> tuple[list[dict[str, str]], list[dict[str, str]], bool]:
        candidates = self.load_candidates()
        updated_records: list[dict[str, str]] = []
        records_changed = False
        candidates_changed = False

        for record in records:
            updated_record = dict(record)
            candidate_id = str(updated_record.get("candidate_id", "")).strip()
            display_name = self.normalize_display_name(updated_record.get("name", ""))

            candidate: dict[str, str] | None = None
            if candidate_id:
                candidate = self.find_candidate(candidates, candidate_id)
                if candidate is None:
                    fallback_name = display_name or candidate_id
                    candidate = self._normalize_candidate(
                        {
                            "candidate_id": candidate_id,
                            "display_name": fallback_name,
                            "archived_at": updated_record.get("archived_at", ""),
                            "created_at": updated_record.get("created_at", ""),
                            "updated_at": updated_record.get("updated_at", ""),
                        }
                    )
                    candidates.append(candidate)
                    candidates_changed = True
            elif display_name:
                name_matches = self.find_candidates_by_name(candidates, display_name, active_only=False)
                if len(name_matches) == 1:
                    candidate = name_matches[0]
                else:
                    candidate = self.create_candidate(candidates, display_name)
                    candidates_changed = True
                updated_record["candidate_id"] = candidate.get("candidate_id", "")
                records_changed = True

            if candidate is not None:
                if candidate.get("archived_at", "").strip() and not updated_record.get("archived_at", "").strip():
                    candidate["archived_at"] = ""
                    candidate["updated_at"] = current_timestamp()
                    candidates_changed = True
                if updated_record.get("candidate_id", "") != candidate.get("candidate_id", ""):
                    updated_record["candidate_id"] = candidate.get("candidate_id", "")
                    records_changed = True
                if updated_record.get("name", "") != candidate.get("display_name", ""):
                    updated_record["name"] = candidate.get("display_name", "")
                    records_changed = True

            updated_records.append(updated_record)

        if candidates_changed:
            self.save_candidates(candidates)
            candidates = self.load_candidates()
        return candidates, updated_records, records_changed

    def sync_records_to_candidate(
        self,
        records: list[dict[str, str]],
        candidate: dict[str, str],
        *,
        archive_records: bool = False,
        archive_timestamp: str = "",
    ) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
        updated_records: list[dict[str, str]] = []
        affected_records: list[dict[str, str]] = []
        timestamp = archive_timestamp or current_timestamp()

        for record in records:
            updated_record = dict(record)
            if updated_record.get("candidate_id", "") == candidate.get("candidate_id", ""):
                changed = False
                if updated_record.get("name", "") != candidate.get("display_name", ""):
                    updated_record["name"] = candidate.get("display_name", "")
                    changed = True
                if archive_records and not updated_record.get("archived_at", "").strip():
                    updated_record["archived_at"] = timestamp
                    updated_record["updated_at"] = timestamp
                    changed = True
                elif changed:
                    updated_record["updated_at"] = timestamp
                if changed:
                    affected_records.append(updated_record)
            updated_records.append(updated_record)

        return updated_records, affected_records
