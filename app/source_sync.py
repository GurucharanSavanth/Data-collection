from __future__ import annotations

import csv
import hashlib
import io
import logging
import sqlite3
from pathlib import Path
from typing import Any
from urllib.request import urlopen

from constants import (
    AUDIT_ACTION_IMPORT_COMMIT,
    AUDIT_ACTION_IMPORT_PREVIEW,
    AUDIT_ACTION_SOURCE_CONFIG_UPDATED,
    DIRECT_CHILD_ROLES,
    IMPORT_OPTIONAL_COLUMNS,
    IMPORT_REQUIRED_COLUMNS,
    PASSWORD_STATE_RESET_REQUIRED,
    ROLE_ORDER,
    ROLE_SUPER_ADMIN,
)
from repositories import AuditRepository, SourceRepository, UserRepository
from security import hash_password
from utils import current_timestamp
from validators import (
    ensure_candidate_referral,
    normalize_login_id,
    validate_login_id,
    validate_phone_number,
    validate_role,
    validate_source_reference,
)


class SourceSyncService:
    def __init__(
        self,
        *,
        db_manager: Any,
        user_repository: UserRepository,
        source_repository: SourceRepository,
        audit_repository: AuditRepository,
        csv_manager: Any,
        logger: logging.Logger,
    ) -> None:
        self.db_manager = db_manager
        self.user_repository = user_repository
        self.source_repository = source_repository
        self.audit_repository = audit_repository
        self.csv_manager = csv_manager
        self.logger = logger

    def get_source_config(self) -> dict[str, object]:
        with self.db_manager.connection() as connection:
            return self.source_repository.get_source_config(connection)

    def update_source_config(
        self,
        actor: dict[str, object],
        *,
        source_mode: str,
        local_path: str,
        remote_url: str,
    ) -> dict[str, object]:
        self._require_super_admin(actor)
        source_reference = validate_source_reference(source_mode, local_path, remote_url)
        with self.db_manager.transaction() as connection:
            config = self.source_repository.update_source_config(
                connection,
                source_mode=source_mode,
                local_path=local_path.strip(),
                remote_url=remote_url.strip(),
                last_sync_status=f"Configured {source_mode} source",
                last_error="",
            )
            self.audit_repository.log(
                connection,
                actor_user_id=int(actor["user_id"]),
                action_type=AUDIT_ACTION_SOURCE_CONFIG_UPDATED,
                target_type="credential_source",
                target_id=str(config.get("source_id", 1)),
                subtree_scope=str(actor["login_id"]),
                success_flag=True,
                message=f"Updated credential source configuration to {source_mode}.",
                metadata={"source_reference": source_reference},
            )
            return config

    def preview_source(
        self,
        actor: dict[str, object],
        *,
        source_mode: str | None = None,
        local_path: str | None = None,
        remote_url: str | None = None,
    ) -> dict[str, object]:
        self._require_super_admin(actor)
        with self.db_manager.connection() as connection:
            config = self.source_repository.get_source_config(connection)

        chosen_mode = (source_mode or str(config.get("source_mode", ""))).strip().upper()
        chosen_path = (local_path if local_path is not None else str(config.get("local_path", ""))).strip()
        chosen_url = (remote_url if remote_url is not None else str(config.get("remote_url", ""))).strip()
        source_reference = validate_source_reference(chosen_mode, chosen_path, chosen_url)
        raw_bytes = self._load_source_bytes(chosen_mode, source_reference)
        checksum = hashlib.sha256(raw_bytes).hexdigest()
        preview = self._parse_source_preview(raw_bytes, chosen_mode, source_reference)
        preview["checksum"] = checksum
        preview["raw_bytes"] = raw_bytes
        preview["generated_at"] = current_timestamp()

        with self.db_manager.transaction() as connection:
            self.audit_repository.log(
                connection,
                actor_user_id=int(actor["user_id"]),
                action_type=AUDIT_ACTION_IMPORT_PREVIEW,
                target_type="credential_source",
                target_id=source_reference,
                subtree_scope=str(actor["login_id"]),
                success_flag=not preview["errors"],
                message="Previewed credential source.",
                metadata={
                    "source_mode": chosen_mode,
                    "checksum": checksum,
                    "accepted_row_count": preview["accepted_row_count"],
                    "rejected_row_count": preview["rejected_row_count"],
                },
            )
        return preview

    def commit_preview(self, actor: dict[str, object], preview: dict[str, object]) -> dict[str, object]:
        self._require_super_admin(actor)
        accepted_rows = [row for row in preview["rows"] if row["accepted"]]
        rejected_rows = [row for row in preview["rows"] if not row["accepted"]]
        raw_snapshot_path, checksum = self.csv_manager.store_raw_snapshot(
            preview["raw_bytes"],
            prefix="credential_source",
        )

        try:
            with self.db_manager.transaction() as connection:
                snapshot = self.source_repository.create_source_snapshot(
                    connection,
                    source_mode=str(preview["source_mode"]),
                    source_reference=str(preview["source_reference"]),
                    raw_snapshot_path=str(raw_snapshot_path),
                    checksum=checksum,
                    parsed_row_count=int(preview["parsed_row_count"]),
                    accepted_row_count=len(accepted_rows),
                    rejected_row_count=len(rejected_rows),
                    sync_status="SUCCESS" if not rejected_rows else "PARTIAL",
                    error_summary="; ".join(preview["errors"]),
                )

                created_or_found: dict[str, dict[str, object]] = {
                    user["login_id"]: user for user in self.user_repository.list_all_users(connection)
                }
                ordered_rows = sorted(
                    accepted_rows,
                    key=lambda item: (ROLE_ORDER.index(str(item["role"])), int(item["row_number"])),
                )

                for row in ordered_rows:
                    user = self._apply_row(connection, row, created_or_found)
                    created_or_found[str(user["login_id"])] = user
                    self.source_repository.add_source_row_mapping(
                        connection,
                        snapshot_id=int(snapshot["snapshot_id"]),
                        source_row_number=int(row["row_number"]),
                        source_login_id=str(row["login_id"]),
                        user_id=int(user["user_id"]),
                        action_taken=str(row["action"]),
                        validation_errors="",
                    )

                for row in rejected_rows:
                    self.source_repository.add_source_row_mapping(
                        connection,
                        snapshot_id=int(snapshot["snapshot_id"]),
                        source_row_number=int(row["row_number"]),
                        source_login_id=str(row.get("login_id", "")),
                        user_id=None,
                        action_taken="REJECTED",
                        validation_errors="; ".join(row["errors"]),
                    )

                self.source_repository.update_source_config(
                    connection,
                    source_mode=str(preview["source_mode"]),
                    local_path=str(preview.get("local_path", "")),
                    remote_url=str(preview.get("remote_url", "")),
                    last_sync_status="SUCCESS" if not rejected_rows else "PARTIAL",
                    last_error="; ".join(preview["errors"]),
                    last_checksum=checksum,
                    last_sync_at=current_timestamp(),
                )
                self.audit_repository.log(
                    connection,
                    actor_user_id=int(actor["user_id"]),
                    action_type=AUDIT_ACTION_IMPORT_COMMIT,
                    target_type="credential_source_snapshot",
                    target_id=str(snapshot["snapshot_id"]),
                    subtree_scope=str(actor["login_id"]),
                    success_flag=True,
                    message="Committed credential source import.",
                    metadata={
                        "accepted_row_count": len(accepted_rows),
                        "rejected_row_count": len(rejected_rows),
                        "checksum": checksum,
                        "raw_snapshot_path": str(raw_snapshot_path),
                    },
                )
                return {
                    "snapshot": snapshot,
                    "accepted_row_count": len(accepted_rows),
                    "rejected_row_count": len(rejected_rows),
                    "checksum": checksum,
                    "raw_snapshot_path": str(raw_snapshot_path),
                }
        except Exception:
            raw_snapshot_path.unlink(missing_ok=True)
            with self.db_manager.transaction() as connection:
                self.source_repository.update_source_config(
                    connection,
                    source_mode=str(preview["source_mode"]),
                    local_path=str(preview.get("local_path", "")),
                    remote_url=str(preview.get("remote_url", "")),
                    last_sync_status="FAILED",
                    last_error="Import failed. Review application log.",
                )
            raise

    def list_snapshots(self) -> list[dict[str, object]]:
        with self.db_manager.connection() as connection:
            return self.source_repository.list_source_snapshots(connection)

    def _require_super_admin(self, actor: dict[str, object]) -> None:
        if str(actor["role"]) != ROLE_SUPER_ADMIN:
            raise PermissionError("Only Super Admin may manage credential source sync.")

    def _load_source_bytes(self, source_mode: str, source_reference: str) -> bytes:
        if source_mode == "OFFLINE":
            return Path(source_reference).read_bytes()
        with urlopen(source_reference, timeout=10) as response:
            return response.read()

    def _parse_source_preview(self, raw_bytes: bytes, source_mode: str, source_reference: str) -> dict[str, object]:
        text_stream = io.StringIO(raw_bytes.decode("utf-8-sig"))
        reader = csv.DictReader(text_stream)
        fieldnames = set(reader.fieldnames or [])
        missing_columns = sorted(IMPORT_REQUIRED_COLUMNS - fieldnames)
        if missing_columns:
            raise ValueError(f"Credential source is missing required columns: {', '.join(missing_columns)}")

        unsupported = sorted(fieldnames - (IMPORT_REQUIRED_COLUMNS | IMPORT_OPTIONAL_COLUMNS))
        preview_rows: list[dict[str, Any]] = []
        errors: list[str] = []
        seen_logins: set[str] = set()

        with self.db_manager.connection() as connection:
            existing_users = {user["login_id"]: user for user in self.user_repository.list_all_users(connection)}

        for row_number, raw_row in enumerate(reader, start=2):
            normalized_row: dict[str, Any] = {
                "row_number": row_number,
                "errors": [],
                "accepted": True,
                "action": "CREATE",
            }
            login_id = normalize_login_id(str(raw_row.get("login_id", "")))
            if not login_id:
                normalized_row["errors"].append("login_id is required.")
            else:
                try:
                    login_id = validate_login_id(login_id)
                except ValueError as exc:
                    normalized_row["errors"].append(str(exc))
            normalized_row["login_id"] = login_id

            role = str(raw_row.get("role", "")).strip()
            try:
                role = validate_role(role)
            except ValueError as exc:
                normalized_row["errors"].append(str(exc))
            normalized_row["role"] = role

            display_name = str(raw_row.get("display_name", "")).strip()
            if not display_name:
                normalized_row["errors"].append("display_name is required.")
            normalized_row["display_name"] = display_name

            parent_login_id = normalize_login_id(str(raw_row.get("parent_login_id", "")))
            normalized_row["parent_login_id"] = parent_login_id
            password = str(raw_row.get("password", "")).strip()
            normalized_row["password"] = password
            normalized_row["deployed_location"] = str(raw_row.get("deployed_location", "")).strip()
            try:
                normalized_row["phone"] = validate_phone_number(str(raw_row.get("phone", "")).strip(), allow_empty=True)
            except ValueError as exc:
                normalized_row["errors"].append(str(exc))
                normalized_row["phone"] = str(raw_row.get("phone", "")).strip()

            active_flag = str(raw_row.get("active_flag", "1")).strip().lower()
            normalized_row["active_flag"] = active_flag not in {"0", "false", "no", "disabled"}

            if login_id in seen_logins:
                normalized_row["errors"].append("Duplicate login_id in source file.")
            elif login_id:
                seen_logins.add(login_id)

            if role == ROLE_SUPER_ADMIN:
                normalized_row["errors"].append("SUPER_ADMIN rows are not allowed in external credential source imports.")

            if role and role != ROLE_SUPER_ADMIN and not parent_login_id:
                normalized_row["errors"].append("parent_login_id is required for non-SUPER_ADMIN rows.")

            if role == "CANDIDATE":
                try:
                    normalized_row["referral_code"] = ensure_candidate_referral(
                        login_id,
                        str(raw_row.get("referral_code", "")).strip() or None,
                    )
                except ValueError as exc:
                    normalized_row["errors"].append(str(exc))
            else:
                normalized_row["referral_code"] = ""

            existing_user = existing_users.get(login_id)
            if existing_user is not None:
                normalized_row["action"] = "UPDATE"
                if str(existing_user["role"]) != role:
                    normalized_row["errors"].append("Existing user role does not match source role.")
            elif not password:
                normalized_row["errors"].append("New users require a password column value.")

            if parent_login_id:
                parent_role = None
                if parent_login_id in existing_users:
                    parent_role = str(existing_users[parent_login_id]["role"])
                else:
                    parent_preview = next(
                        (candidate for candidate in preview_rows if candidate.get("login_id") == parent_login_id and candidate["accepted"]),
                        None,
                    )
                    if parent_preview is not None:
                        parent_role = str(parent_preview["role"])
                if parent_role is None:
                    normalized_row["errors"].append("parent_login_id does not resolve to an existing or staged user.")
                elif role and role not in DIRECT_CHILD_ROLES.get(parent_role, ()):
                    normalized_row["errors"].append(f"Parent role {parent_role} cannot own child role {role}.")

            if unsupported and row_number == 2:
                errors.append(f"Unsupported source columns ignored: {', '.join(unsupported)}")

            normalized_row["accepted"] = not normalized_row["errors"]
            preview_rows.append(normalized_row)

        errors.extend(
            f"Row {row['row_number']}: {'; '.join(row['errors'])}"
            for row in preview_rows
            if row["errors"]
        )
        return {
            "source_mode": source_mode,
            "source_reference": source_reference,
            "local_path": source_reference if source_mode == "OFFLINE" else "",
            "remote_url": source_reference if source_mode == "ONLINE" else "",
            "parsed_row_count": len(preview_rows),
            "accepted_row_count": len([row for row in preview_rows if row["accepted"]]),
            "rejected_row_count": len([row for row in preview_rows if not row["accepted"]]),
            "rows": preview_rows,
            "errors": errors,
        }

    def _apply_row(
        self,
        connection: sqlite3.Connection,
        row: dict[str, Any],
        created_or_found: dict[str, dict[str, object]],
    ) -> dict[str, object]:
        existing_user = self.user_repository.get_user_by_login(connection, str(row["login_id"]))
        parent_user_id = None
        parent_login_id = str(row.get("parent_login_id", "")).strip()
        if parent_login_id:
            parent_user = created_or_found.get(parent_login_id) or self.user_repository.get_user_by_login(connection, parent_login_id)
            if parent_user is None:
                raise ValueError(f"Unable to resolve parent_login_id for row {row['row_number']}.")
            parent_user_id = int(parent_user["user_id"])

        if existing_user is None:
            return self.user_repository.create_user(
                connection,
                login_id=str(row["login_id"]),
                role=str(row["role"]),
                password_hash=hash_password(str(row["password"])),
                password_state=PASSWORD_STATE_RESET_REQUIRED,
                parent_user_id=parent_user_id,
                display_name=str(row["display_name"]),
                deployed_location=str(row["deployed_location"]),
                phone=str(row["phone"]),
                active_flag=bool(row["active_flag"]),
            )

        updated = self.user_repository.update_user(
            connection,
            int(existing_user["user_id"]),
            parent_user_id=parent_user_id,
            display_name=str(row["display_name"]),
            deployed_location=str(row["deployed_location"]),
            phone=str(row["phone"]),
            active_flag=bool(row["active_flag"]),
        )
        if str(row.get("password", "")).strip():
            self.user_repository.set_password(
                connection,
                int(existing_user["user_id"]),
                hash_password(str(row["password"])),
                PASSWORD_STATE_RESET_REQUIRED,
            )
            updated = self.user_repository.get_user(connection, int(existing_user["user_id"])) or updated
        return updated
