from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from candidate_manager import CandidateManager
from csv_manager import CSVManager
from session_manager import SessionManager
from version_history_manager import VersionHistoryManager


def _clone_records(records: list[dict[str, str]]) -> list[dict[str, str]]:
    return [dict(record) for record in records]


def _clone_candidates(candidates: list[dict[str, str]]) -> list[dict[str, str]]:
    return [dict(candidate) for candidate in candidates]


def run_self_test(
    *,
    storage_root: Path,
    csv_manager: CSVManager,
    candidate_manager: CandidateManager,
    session_manager: SessionManager,
    version_history_manager: VersionHistoryManager,
    logger: logging.Logger,
) -> dict[str, Any]:
    logger.info("Starting self-test in %s", storage_root)

    startup_state = session_manager.mark_startup()
    session_state = session_manager.load_session_state()
    if startup_state.get("clean_shutdown", True):
        raise AssertionError("Startup state should mark clean_shutdown as false during runtime.")
    if session_state.get("selected_candidate", "None") != "None":
        raise AssertionError("Fresh session state should not have an active candidate.")

    candidates: list[dict[str, str]] = []
    primary_candidate = candidate_manager.create_candidate(candidates, "Alpha Example")
    candidate_manager.save_candidates(candidates)
    candidates = candidate_manager.load_candidates()
    if len(candidates) != 1:
        raise AssertionError("Candidate create flow did not persist exactly one candidate.")

    form_data = {
        "title": "Initial Intake",
        "application_number": "APP-001",
        "candidate_id": primary_candidate.get("candidate_id", ""),
        "name": primary_candidate.get("display_name", ""),
        "phone_number": "1234567890",
        "status": "Open",
        "short_note": "Created by self-test",
    }
    created_record = csv_manager.build_new_record(form_data)
    csv_manager.save_records([created_record], backup_reason="created")
    version_history_manager.add_version(
        created_record.get("record_id", ""),
        "CREATE",
        created_record,
        changed_at=created_record.get("updated_at", ""),
    )

    records = csv_manager.load_records()
    if len(records) != 1:
        raise AssertionError("Record create flow did not persist exactly one record.")

    updated_candidates = _clone_candidates(candidates)
    renamed_candidate = candidate_manager.rename_candidate(
        updated_candidates,
        primary_candidate.get("candidate_id", ""),
        "Beta Example",
    )
    updated_records, renamed_affected_records = candidate_manager.sync_records_to_candidate(
        _clone_records(records),
        renamed_candidate,
    )
    csv_manager.save_records(updated_records, backup_reason="candidate_renamed")
    candidate_manager.save_candidates(updated_candidates)
    for affected_record in renamed_affected_records:
        version_history_manager.add_version(
            affected_record.get("record_id", ""),
            "CANDIDATE_EDIT",
            affected_record,
            changed_at=renamed_candidate.get("updated_at", ""),
        )

    renamed_records = csv_manager.load_records()
    renamed_record = csv_manager.find_record(renamed_records, created_record.get("record_id", ""))
    if renamed_record is None or renamed_record.get("name", "") != "Beta Example":
        raise AssertionError("Candidate rename did not update linked record.")

    updated_record = csv_manager.build_updated_record(
        created_record.get("record_id", ""),
        {
            "title": "Updated Intake",
            "application_number": "APP-002",
            "candidate_id": renamed_candidate.get("candidate_id", ""),
            "name": renamed_candidate.get("display_name", ""),
            "phone_number": "1987654321",
            "status": "In Progress",
            "short_note": "Record updated by self-test",
        },
        renamed_record,
    )
    csv_manager.save_records([updated_record], backup_reason="updated")
    version_history_manager.add_version(
        updated_record.get("record_id", ""),
        "UPDATE",
        updated_record,
        changed_at=updated_record.get("updated_at", ""),
    )

    updated_candidates = candidate_manager.load_candidates()
    archived_candidate_list = _clone_candidates(updated_candidates)
    archived_candidate = candidate_manager.archive_candidate(
        archived_candidate_list,
        renamed_candidate.get("candidate_id", ""),
    )
    archived_records, archived_affected_records = candidate_manager.sync_records_to_candidate(
        _clone_records(csv_manager.load_records()),
        archived_candidate,
        archive_records=True,
        archive_timestamp=archived_candidate.get("archived_at", ""),
    )
    csv_manager.save_records(archived_records, backup_reason="candidate_archived")
    candidate_manager.save_candidates(archived_candidate_list)
    for affected_record in archived_affected_records:
        version_history_manager.add_version(
            affected_record.get("record_id", ""),
            "CANDIDATE_ARCHIVE",
            affected_record,
            changed_at=archived_candidate.get("archived_at", ""),
        )

    archived_record = csv_manager.find_record(csv_manager.load_records(), created_record.get("record_id", ""))
    if archived_record is None or not archived_record.get("archived_at", "").strip():
        raise AssertionError("Candidate archive did not archive linked record.")

    restored_candidate_list = _clone_candidates(candidate_manager.load_candidates())
    restored_candidate = candidate_manager.restore_candidate(
        restored_candidate_list,
        archived_candidate.get("candidate_id", ""),
    )
    candidate_manager.save_candidates(restored_candidate_list)

    unarchived_record = csv_manager.build_unarchived_record(archived_record)
    csv_manager.save_records([unarchived_record], backup_reason="record_unarchived")
    version_history_manager.add_version(
        unarchived_record.get("record_id", ""),
        "UNARCHIVE",
        unarchived_record,
        changed_at=unarchived_record.get("updated_at", ""),
    )

    version_one_snapshot = version_history_manager.get_snapshot(created_record.get("record_id", ""), 1)
    if version_one_snapshot is None:
        raise AssertionError("Version history did not retain baseline snapshot.")
    restored_snapshot = dict(version_one_snapshot)
    restored_snapshot["candidate_id"] = restored_candidate.get("candidate_id", "")
    restored_snapshot["name"] = restored_candidate.get("display_name", "")
    restored_record = csv_manager.build_restored_record(created_record.get("record_id", ""), restored_snapshot)
    csv_manager.save_records([restored_record], backup_reason="restored")
    version_history_manager.add_version(
        restored_record.get("record_id", ""),
        "RESTORE",
        restored_record,
        changed_at=restored_record.get("updated_at", ""),
    )

    export_dir = storage_root / "exports"
    export_path = export_dir / "candidate_records_beta_example.csv"
    csv_manager.export_records(csv_manager.load_records(), export_path)
    if not export_path.exists():
        raise AssertionError("CSV export did not create destination file.")

    final_records = csv_manager.load_records()
    final_record = csv_manager.find_record(final_records, created_record.get("record_id", ""))
    if final_record is None:
        raise AssertionError("Final record missing after restore flow.")
    if final_record.get("title", "") != version_one_snapshot.get("title", ""):
        raise AssertionError("Restore flow did not apply requested version snapshot.")
    if final_record.get("candidate_id", "") != restored_candidate.get("candidate_id", ""):
        raise AssertionError("Restore flow lost candidate linkage.")

    final_session_state = {
        "window_geometry": "1280x800+10+10",
        "window_state": "normal",
        "selected_candidate": restored_candidate.get("display_name", ""),
        "selected_candidate_id": restored_candidate.get("candidate_id", ""),
        "view_mode": "Active",
        "selected_record_id": final_record.get("record_id", ""),
        "mode": "edit",
        "last_opened_at": final_record.get("updated_at", ""),
        "form_values": {
            "record_id": final_record.get("record_id", ""),
            "title": final_record.get("title", ""),
            "application_number": final_record.get("application_number", ""),
            "candidate_id": final_record.get("candidate_id", ""),
            "name": final_record.get("name", ""),
            "phone_number": final_record.get("phone_number", ""),
            "status": final_record.get("status", ""),
            "short_note": final_record.get("short_note", ""),
        },
    }
    session_manager.save_session_state(final_session_state)
    session_manager.record_successful_save(len(final_records))
    session_manager.record_error("")
    session_manager.mark_clean_shutdown(final_session_state)

    app_state = session_manager.load_app_state()
    if not app_state.get("clean_shutdown", False):
        raise AssertionError("Clean shutdown marker was not restored after self-test.")

    version_entries = version_history_manager.list_versions(created_record.get("record_id", ""))
    if len(version_entries) < 6:
        raise AssertionError("Version history flow did not record expected entries.")

    report = {
        "storage_root": str(storage_root),
        "record_id": created_record.get("record_id", ""),
        "candidate_id": restored_candidate.get("candidate_id", ""),
        "record_count": len(final_records),
        "candidate_count": len(candidate_manager.load_candidates()),
        "version_count": len(version_entries),
        "export_path": str(export_path),
        "backup_count": len(list(csv_manager.backup_dir.glob("*.csv"))),
    }
    logger.info("Self-test complete: %s", report)
    return report
