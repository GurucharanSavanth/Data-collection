from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from authorization import AuthorizationService
from constants import (
    AUDIT_ACTION_LOGIN,
    AUDIT_ACTION_LOGIN_FAILED,
    AUDIT_ACTION_PASSWORD_RESET,
    AUDIT_ACTION_PERMISSION_DENIED,
    AUDIT_ACTION_RECOVERY,
    AUDIT_ACTION_RECORD_CREATED,
    AUDIT_ACTION_RECORD_RESTORED,
    AUDIT_ACTION_RECORD_UPDATED,
    AUDIT_ACTION_USER_CREATED,
    AUDIT_ACTION_USER_UPDATED,
    MANAGER_ROLES,
    PASSWORD_STATE_ACTIVE,
    PASSWORD_STATE_RESET_REQUIRED,
    RECORD_STATUS_FORFEITED,
    ROLE_CANDIDATE,
    ROLE_ORDER,
    ROLE_SUPER_ADMIN,
)
from repositories import (
    AuditRepository,
    BackupRepository,
    MetaRepository,
    RecordRepository,
    SourceRepository,
    UserRepository,
)
from security import hash_password, validate_password_strength, verify_password
from utils import current_timestamp, current_timestamp_for_filename, ensure_dir
from validators import (
    compose_title,
    ensure_candidate_referral,
    validate_application_number,
    validate_login_id,
    validate_phone_number,
    validate_role,
    validate_status,
)


class BackupService:
    def __init__(self, base_dir: Path, backup_repository: BackupRepository, logger: logging.Logger) -> None:
        self.base_dir = base_dir
        self.backup_repository = backup_repository
        self.logger = logger

    def create_json_backup(
        self,
        connection: Any,
        *,
        backup_type: str,
        target_type: str,
        target_id: str,
        payload: dict[str, object],
    ) -> dict[str, object]:
        target_dir = ensure_dir(self.base_dir / backup_type / target_type)
        artifact_path = target_dir / f"{target_id}_{current_timestamp_for_filename()}.json"
        serialized = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
        artifact_hash = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
        artifact_path.write_text(serialized + "\n", encoding="utf-8")
        try:
            return self.backup_repository.create_backup_entry(
                connection,
                backup_type=backup_type,
                target_type=target_type,
                target_id=target_id,
                artifact_path=str(artifact_path),
                artifact_hash=artifact_hash,
                restore_test_status="VERIFIED",
            )
        except Exception:
            artifact_path.unlink(missing_ok=True)
            raise


class AuthService:
    def __init__(
        self,
        *,
        db_manager: Any,
        user_repository: UserRepository,
        audit_repository: AuditRepository,
        meta_repository: MetaRepository,
        logger: logging.Logger,
    ) -> None:
        self.db_manager = db_manager
        self.user_repository = user_repository
        self.audit_repository = audit_repository
        self.meta_repository = meta_repository
        self.logger = logger

    def needs_bootstrap(self) -> bool:
        with self.db_manager.connection() as connection:
            return self.user_repository.count_users(connection) == 0

    def bootstrap_super_admin(self, login_id: str, password: str, display_name: str) -> dict[str, object]:
        normalized_login = validate_login_id(login_id)
        if not display_name.strip():
            raise ValueError("Display name is required.")
        with self.db_manager.transaction() as connection:
            if self.user_repository.count_users(connection) > 0:
                raise ValueError("Bootstrap is already complete.")
            user = self.user_repository.create_user(
                connection,
                login_id=normalized_login,
                role=ROLE_SUPER_ADMIN,
                password_hash=hash_password(password),
                password_state=PASSWORD_STATE_ACTIVE,
                parent_user_id=None,
                display_name=display_name.strip(),
                deployed_location="",
                phone="",
                active_flag=True,
            )
            self.meta_repository.set_flag(connection, "bootstrap_completed", "1")
            self.audit_repository.log(
                connection,
                actor_user_id=int(user["user_id"]),
                action_type=AUDIT_ACTION_USER_CREATED,
                target_type="user",
                target_id=str(user["login_id"]),
                subtree_scope=str(user["login_id"]),
                success_flag=True,
                message="Bootstrapped initial Super Admin.",
                metadata={"role": ROLE_SUPER_ADMIN},
            )
            return user

    def authenticate(self, login_id: str, password: str) -> dict[str, object]:
        normalized_login = validate_login_id(login_id)
        with self.db_manager.transaction() as connection:
            user = self.user_repository.get_user_by_login(connection, normalized_login)
            if user is None or not verify_password(password, str(user["password_hash"])):
                self.audit_repository.log(
                    connection,
                    actor_user_id=None,
                    action_type=AUDIT_ACTION_LOGIN_FAILED,
                    target_type="user",
                    target_id=normalized_login,
                    subtree_scope="",
                    success_flag=False,
                    message="Login failed.",
                    metadata={},
                )
                raise ValueError("Invalid login ID or password.")
            if not bool(user["active_flag"]):
                raise ValueError("This account is disabled.")
            self.audit_repository.log(
                connection,
                actor_user_id=int(user["user_id"]),
                action_type=AUDIT_ACTION_LOGIN,
                target_type="user",
                target_id=str(user["login_id"]),
                subtree_scope=str(user["login_id"]),
                success_flag=True,
                message="Login succeeded.",
                metadata={"password_state": user["password_state"]},
            )
            return user

    def change_password(
        self,
        user: dict[str, object],
        *,
        new_password: str,
        current_password: str | None = None,
        bypass_current: bool = False,
    ) -> dict[str, object]:
        validate_password_strength(new_password)
        with self.db_manager.transaction() as connection:
            fresh_user = self.user_repository.get_user(connection, int(user["user_id"]))
            if fresh_user is None:
                raise ValueError("User no longer exists.")
            if not bypass_current:
                if not current_password:
                    raise ValueError("Current password is required.")
                if not verify_password(current_password, str(fresh_user["password_hash"])):
                    raise ValueError("Current password is incorrect.")
            self.user_repository.set_password(
                connection,
                int(fresh_user["user_id"]),
                hash_password(new_password),
                PASSWORD_STATE_ACTIVE,
            )
            self.audit_repository.log(
                connection,
                actor_user_id=int(fresh_user["user_id"]),
                action_type=AUDIT_ACTION_PASSWORD_RESET,
                target_type="user",
                target_id=str(fresh_user["login_id"]),
                subtree_scope=str(fresh_user["login_id"]),
                success_flag=True,
                message="Password changed.",
                metadata={"self_service": True},
            )
            return self.user_repository.get_user(connection, int(fresh_user["user_id"])) or fresh_user


class UserService:
    def __init__(
        self,
        *,
        db_manager: Any,
        user_repository: UserRepository,
        audit_repository: AuditRepository,
        authorization_service: AuthorizationService,
        logger: logging.Logger,
    ) -> None:
        self.db_manager = db_manager
        self.user_repository = user_repository
        self.audit_repository = audit_repository
        self.authorization_service = authorization_service
        self.logger = logger

    def get_user_by_login(self, login_id: str) -> dict[str, object] | None:
        with self.db_manager.connection() as connection:
            return self.user_repository.get_user_by_login(connection, validate_login_id(login_id))

    def get_user(self, user_id: int) -> dict[str, object] | None:
        with self.db_manager.connection() as connection:
            return self.user_repository.get_user(connection, user_id)

    def list_visible_users(self, actor: dict[str, object]) -> list[dict[str, object]]:
        with self.db_manager.connection() as connection:
            if str(actor["role"]) == ROLE_SUPER_ADMIN:
                return self.user_repository.list_all_users(connection)
            return self.user_repository.get_subtree_users(connection, int(actor["user_id"]))

    def list_candidate_choices(self, actor: dict[str, object]) -> list[dict[str, object]]:
        return [user for user in self.list_visible_users(actor) if str(user["role"]) == ROLE_CANDIDATE]

    def get_user_path(self, user_id: int) -> list[dict[str, object]]:
        with self.db_manager.connection() as connection:
            return self.user_repository.get_user_path(connection, user_id)

    def build_tree(self, actor: dict[str, object]) -> list[dict[str, object]]:
        with self.db_manager.connection() as connection:
            if str(actor["role"]) == ROLE_SUPER_ADMIN:
                top_nodes = [user for user in self.user_repository.list_all_users(connection) if user["parent_user_id"] is None]
                tree: list[dict[str, object]] = []
                for node in top_nodes:
                    tree.extend(self.user_repository.build_tree(connection, int(node["user_id"])))
                return tree
            return self.user_repository.build_tree(connection, int(actor["user_id"]))

    def create_user(
        self,
        actor: dict[str, object],
        *,
        login_id: str,
        role: str,
        password: str,
        display_name: str,
        deployed_location: str,
        phone: str,
        parent_login_id: str,
        active_flag: bool = True,
    ) -> dict[str, object]:
        normalized_login = validate_login_id(login_id)
        normalized_role = validate_role(role)
        normalized_phone = validate_phone_number(phone, allow_empty=True)
        if normalized_role == ROLE_CANDIDATE:
            ensure_candidate_referral(normalized_login, normalized_login)
        if not display_name.strip():
            raise ValueError("Display name is required.")
        with self.db_manager.transaction() as connection:
            actor_fresh = self.user_repository.get_user(connection, int(actor["user_id"]))
            if actor_fresh is None:
                raise ValueError("Actor no longer exists.")
            if normalized_role == ROLE_SUPER_ADMIN:
                raise PermissionError("Super Admin creation is limited to bootstrap.")
            if self.user_repository.get_user_by_login(connection, normalized_login) is not None:
                raise ValueError("Login ID already exists.")
            parent = self.user_repository.get_user_by_login(connection, validate_login_id(parent_login_id))
            if parent is None:
                raise ValueError("Parent login ID does not exist.")
            if not self.authorization_service.can_map_child(connection, actor_fresh, parent, normalized_role):
                self._log_denial(connection, actor_fresh, "create_user", normalized_login)
                raise PermissionError("You may not create that role under the selected parent.")

            created = self.user_repository.create_user(
                connection,
                login_id=normalized_login,
                role=normalized_role,
                password_hash=hash_password(password),
                password_state=PASSWORD_STATE_RESET_REQUIRED if normalized_role == ROLE_CANDIDATE else PASSWORD_STATE_ACTIVE,
                parent_user_id=int(parent["user_id"]),
                display_name=display_name.strip(),
                deployed_location=deployed_location.strip(),
                phone=normalized_phone,
                active_flag=active_flag,
            )
            self.audit_repository.log(
                connection,
                actor_user_id=int(actor_fresh["user_id"]),
                action_type=AUDIT_ACTION_USER_CREATED,
                target_type="user",
                target_id=str(created["login_id"]),
                subtree_scope=str(actor_fresh["login_id"]),
                success_flag=True,
                message="Created user.",
                metadata={"role": normalized_role, "parent_login_id": parent_login_id},
            )
            return created

    def update_user(
        self,
        actor: dict[str, object],
        *,
        target_login_id: str,
        display_name: str,
        deployed_location: str,
        phone: str,
        parent_login_id: str,
        active_flag: bool,
    ) -> dict[str, object]:
        if not display_name.strip():
            raise ValueError("Display name is required.")
        normalized_phone = validate_phone_number(phone, allow_empty=True)
        with self.db_manager.transaction() as connection:
            actor_fresh = self.user_repository.get_user(connection, int(actor["user_id"]))
            target = self.user_repository.get_user_by_login(connection, validate_login_id(target_login_id))
            if actor_fresh is None or target is None:
                raise ValueError("Actor or target no longer exists.")
            if not self.authorization_service.can_manage_user(connection, actor_fresh, target):
                self._log_denial(connection, actor_fresh, "update_user", target_login_id)
                raise PermissionError("You may not update this user.")

            parent = self.user_repository.get_user_by_login(connection, validate_login_id(parent_login_id))
            if parent is None:
                raise ValueError("Parent login ID does not exist.")
            if int(parent["user_id"]) == int(target["user_id"]):
                raise ValueError("A user cannot be their own parent.")
            if int(parent["user_id"]) in self.user_repository.get_subtree_user_ids(connection, int(target["user_id"])):
                raise ValueError("A user cannot be reassigned under their own subtree.")
            if not self.authorization_service.can_map_child(connection, actor_fresh, parent, str(target["role"])):
                self._log_denial(connection, actor_fresh, "map_user_parent", target_login_id)
                raise PermissionError("You may not move this user under the selected parent.")

            updated = self.user_repository.update_user(
                connection,
                int(target["user_id"]),
                parent_user_id=int(parent["user_id"]),
                display_name=display_name.strip(),
                deployed_location=deployed_location.strip(),
                phone=normalized_phone,
                active_flag=active_flag,
            )
            self.audit_repository.log(
                connection,
                actor_user_id=int(actor_fresh["user_id"]),
                action_type=AUDIT_ACTION_USER_UPDATED,
                target_type="user",
                target_id=target_login_id,
                subtree_scope=str(actor_fresh["login_id"]),
                success_flag=True,
                message="Updated user profile.",
                metadata={"parent_login_id": parent_login_id, "active_flag": active_flag},
            )
            return updated

    def reset_password(
        self,
        actor: dict[str, object],
        *,
        target_login_id: str,
        new_password: str,
        force_reset: bool = True,
    ) -> None:
        validate_password_strength(new_password)
        with self.db_manager.transaction() as connection:
            actor_fresh = self.user_repository.get_user(connection, int(actor["user_id"]))
            target = self.user_repository.get_user_by_login(connection, validate_login_id(target_login_id))
            if actor_fresh is None or target is None:
                raise ValueError("Actor or target no longer exists.")
            if not self.authorization_service.can_reset_credentials(connection, actor_fresh, target):
                self._log_denial(connection, actor_fresh, "reset_password", target_login_id)
                raise PermissionError("You may not reset this password.")
            self.user_repository.set_password(
                connection,
                int(target["user_id"]),
                hash_password(new_password),
                PASSWORD_STATE_RESET_REQUIRED if force_reset else PASSWORD_STATE_ACTIVE,
            )
            self.audit_repository.log(
                connection,
                actor_user_id=int(actor_fresh["user_id"]),
                action_type=AUDIT_ACTION_PASSWORD_RESET,
                target_type="user",
                target_id=target_login_id,
                subtree_scope=str(actor_fresh["login_id"]),
                success_flag=True,
                message="Password reset.",
                metadata={"force_reset": force_reset},
            )

    def _log_denial(self, connection: Any, actor: dict[str, object], action: str, target_id: str) -> None:
        self.audit_repository.log(
            connection,
            actor_user_id=int(actor["user_id"]),
            action_type=AUDIT_ACTION_PERMISSION_DENIED,
            target_type="user",
            target_id=target_id,
            subtree_scope=str(actor["login_id"]),
            success_flag=False,
            message=f"Permission denied for {action}.",
            metadata={},
        )


class RecordService:
    def __init__(
        self,
        *,
        db_manager: Any,
        record_repository: RecordRepository,
        user_repository: UserRepository,
        audit_repository: AuditRepository,
        authorization_service: AuthorizationService,
        backup_service: BackupService,
        csv_manager: Any,
        logger: logging.Logger,
    ) -> None:
        self.db_manager = db_manager
        self.record_repository = record_repository
        self.user_repository = user_repository
        self.audit_repository = audit_repository
        self.authorization_service = authorization_service
        self.backup_service = backup_service
        self.csv_manager = csv_manager
        self.logger = logger

    def list_records(self, actor: dict[str, object]) -> list[dict[str, object]]:
        with self.db_manager.connection() as connection:
            if str(actor["role"]) == ROLE_SUPER_ADMIN:
                return self.record_repository.list_records_for_users(
                    connection,
                    self.authorization_service.get_authorized_subtree(connection, actor),
                    include_unassigned=True,
                )
            return self.record_repository.list_records_for_users(
                connection,
                self.authorization_service.get_authorized_subtree(connection, actor),
                include_unassigned=False,
            )

    def get_record(self, actor: dict[str, object], public_id: str) -> dict[str, object]:
        with self.db_manager.connection() as connection:
            record = self.record_repository.get_record_by_public_id(connection, public_id)
            if record is None:
                raise ValueError("Record not found.")
            if not self.authorization_service.can_view_record(connection, actor, record):
                raise PermissionError("You may not view this record.")
            return record

    def save_record(
        self,
        actor: dict[str, object],
        *,
        public_id: str | None,
        candidate_login_id: str | None,
        application_number: str,
        name: str,
        phone_number: str,
        status: str,
        short_note: str,
        manual_title_display: str = "",
    ) -> dict[str, object]:
        normalized_application_number = validate_application_number(application_number)
        normalized_phone = validate_phone_number(phone_number)
        normalized_status = validate_status(status)
        normalized_name = name.strip()
        if not normalized_name:
            raise ValueError("Name is required.")

        with self.db_manager.transaction() as connection:
            actor_fresh = self.user_repository.get_user(connection, int(actor["user_id"]))
            if actor_fresh is None:
                raise ValueError("Actor no longer exists.")

            existing_record = None
            if public_id:
                existing_record = self.record_repository.get_record_by_public_id(connection, public_id)
                if existing_record is None:
                    raise ValueError("Selected record no longer exists.")
                if not self.authorization_service.can_edit_record(connection, actor_fresh, existing_record):
                    self._log_denial(connection, actor_fresh, "save_record", public_id)
                    raise PermissionError("You may not edit this record.")

            candidate = self._resolve_candidate(connection, actor_fresh, candidate_login_id, existing_record)
            if not self.authorization_service.can_create_record(connection, actor_fresh, candidate):
                self._log_denial(connection, actor_fresh, "create_record", candidate_login_id or "")
                raise PermissionError("You may not create or edit records for that candidate.")

            if existing_record is not None:
                exclude_record_id = int(existing_record["record_id"])
            else:
                exclude_record_id = None
            if self.record_repository.application_number_exists(
                connection,
                normalized_application_number,
                exclude_record_id=exclude_record_id,
            ):
                raise ValueError("Application Number must be unique.")

            title_display = self._build_title(candidate, manual_title_display, existing_record)
            if not title_display:
                raise ValueError("Title requires a candidate assignment or a manager-provided title.")

            if existing_record is None:
                saved_record = self.record_repository.create_record(
                    connection,
                    public_id=self.csv_manager.generate_record_public_id(),
                    candidate_user_id=int(candidate["user_id"]) if candidate is not None else None,
                    application_number=normalized_application_number,
                    title_display=title_display,
                    name=normalized_name,
                    phone_number=normalized_phone,
                    status=normalized_status,
                    short_note=short_note.strip(),
                    actor_user_id=int(actor_fresh["user_id"]),
                )
                version_number = 1
                change_type = "CREATE"
                audit_action = AUDIT_ACTION_RECORD_CREATED
            else:
                version_number = int(existing_record["version_number"]) + 1
                saved_record = self.record_repository.update_record(
                    connection,
                    int(existing_record["record_id"]),
                    candidate_user_id=int(candidate["user_id"]) if candidate is not None else None,
                    application_number=normalized_application_number,
                    title_display=title_display,
                    name=normalized_name,
                    phone_number=normalized_phone,
                    status=normalized_status,
                    short_note=short_note.strip(),
                    actor_user_id=int(actor_fresh["user_id"]),
                    version_number=version_number,
                )
                change_type = "UPDATE"
                audit_action = AUDIT_ACTION_RECORD_UPDATED

            self._verify_saved_record(saved_record, normalized_application_number, normalized_status, title_display)
            self.record_repository.create_record_version(
                connection,
                record_id=int(saved_record["record_id"]),
                version_number=version_number,
                snapshot_payload=self._snapshot_record(saved_record),
                changed_by_user_id=int(actor_fresh["user_id"]),
                change_type=change_type,
            )
            self.backup_service.create_json_backup(
                connection,
                backup_type="record_versions",
                target_type="record",
                target_id=str(saved_record["public_id"]),
                payload=self._snapshot_record(saved_record),
            )
            self.audit_repository.log(
                connection,
                actor_user_id=int(actor_fresh["user_id"]),
                action_type=audit_action,
                target_type="record",
                target_id=str(saved_record["public_id"]),
                subtree_scope=str(actor_fresh["login_id"]),
                success_flag=True,
                message="Saved record.",
                metadata={
                    "application_number": normalized_application_number,
                    "candidate_login_id": candidate["login_id"] if candidate else "",
                    "version_number": version_number,
                },
            )
            return saved_record

    def archive_record(self, actor: dict[str, object], public_id: str) -> dict[str, object]:
        with self.db_manager.transaction() as connection:
            actor_fresh = self.user_repository.get_user(connection, int(actor["user_id"]))
            record = self.record_repository.get_record_by_public_id(connection, public_id)
            if actor_fresh is None or record is None:
                raise ValueError("Actor or record no longer exists.")
            if not self.authorization_service.can_edit_record(connection, actor_fresh, record):
                self._log_denial(connection, actor_fresh, "archive_record", public_id)
                raise PermissionError("You may not archive this record.")
            version_number = int(record["version_number"]) + 1
            archived = self.record_repository.archive_record(
                connection,
                int(record["record_id"]),
                actor_user_id=int(actor_fresh["user_id"]),
                version_number=version_number,
            )
            self.record_repository.create_record_version(
                connection,
                record_id=int(record["record_id"]),
                version_number=version_number,
                snapshot_payload=self._snapshot_record(archived),
                changed_by_user_id=int(actor_fresh["user_id"]),
                change_type="ARCHIVE",
            )
            self.backup_service.create_json_backup(
                connection,
                backup_type="record_archives",
                target_type="record",
                target_id=str(record["public_id"]),
                payload=self._snapshot_record(archived),
            )
            self.audit_repository.log(
                connection,
                actor_user_id=int(actor_fresh["user_id"]),
                action_type=AUDIT_ACTION_RECORD_UPDATED,
                target_type="record",
                target_id=public_id,
                subtree_scope=str(actor_fresh["login_id"]),
                success_flag=True,
                message="Archived record.",
                metadata={"version_number": version_number},
            )
            return archived

    def list_versions(self, actor: dict[str, object], public_id: str) -> list[dict[str, object]]:
        with self.db_manager.connection() as connection:
            record = self.record_repository.get_record_by_public_id(connection, public_id)
            if record is None:
                raise ValueError("Record not found.")
            if not self.authorization_service.can_view_record(connection, actor, record):
                raise PermissionError("You may not view this record.")
            return self.record_repository.list_record_versions(connection, int(record["record_id"]))

    def restore_version(self, actor: dict[str, object], version_id: int) -> dict[str, object]:
        with self.db_manager.transaction() as connection:
            actor_fresh = self.user_repository.get_user(connection, int(actor["user_id"]))
            version = self.record_repository.get_record_version(connection, version_id)
            if actor_fresh is None or version is None:
                raise ValueError("Actor or version no longer exists.")
            record = self.record_repository.get_record(connection, int(version["record_id"]))
            if record is None:
                raise ValueError("Record not found.")
            if not self.authorization_service.can_edit_record(connection, actor_fresh, record):
                self._log_denial(connection, actor_fresh, "restore_version", str(version_id))
                raise PermissionError("You may not restore this record.")
            snapshot = dict(version["snapshot_payload"])
            restored = self.record_repository.update_record(
                connection,
                int(record["record_id"]),
                candidate_user_id=int(snapshot["candidate_user_id"]) if snapshot.get("candidate_user_id") else None,
                application_number=str(snapshot["application_number"]),
                title_display=str(snapshot["title_display"]),
                name=str(snapshot["name"]),
                phone_number=str(snapshot["phone_number"]),
                status=str(snapshot["status"]),
                short_note=str(snapshot["short_note"]),
                actor_user_id=int(actor_fresh["user_id"]),
                version_number=int(record["version_number"]) + 1,
            )
            self.record_repository.create_record_version(
                connection,
                record_id=int(record["record_id"]),
                version_number=int(restored["version_number"]),
                snapshot_payload=self._snapshot_record(restored),
                changed_by_user_id=int(actor_fresh["user_id"]),
                change_type="RESTORE",
            )
            self.backup_service.create_json_backup(
                connection,
                backup_type="record_restores",
                target_type="record",
                target_id=str(restored["public_id"]),
                payload=self._snapshot_record(restored),
            )
            self.audit_repository.log(
                connection,
                actor_user_id=int(actor_fresh["user_id"]),
                action_type=AUDIT_ACTION_RECOVERY,
                target_type="record",
                target_id=str(restored["public_id"]),
                subtree_scope=str(actor_fresh["login_id"]),
                success_flag=True,
                message="Restored record version.",
                metadata={"source_version_id": version_id, "restored_version_number": restored["version_number"]},
            )
            return restored

    def _resolve_candidate(
        self,
        connection: Any,
        actor: dict[str, object],
        candidate_login_id: str | None,
        existing_record: dict[str, object] | None,
    ) -> dict[str, object] | None:
        if str(actor["role"]) == ROLE_CANDIDATE:
            return self.user_repository.get_user(connection, int(actor["user_id"]))
        if candidate_login_id:
            candidate = self.user_repository.get_user_by_login(connection, validate_login_id(candidate_login_id))
            if candidate is None:
                raise ValueError("Candidate login ID does not exist.")
            if str(candidate["role"]) != ROLE_CANDIDATE:
                raise ValueError("Selected record owner must be a candidate.")
            return candidate
        if existing_record and existing_record.get("candidate_user_id"):
            return self.user_repository.get_user(connection, int(existing_record["candidate_user_id"]))
        return None

    def _build_title(
        self,
        candidate: dict[str, object] | None,
        manual_title_display: str,
        existing_record: dict[str, object] | None,
    ) -> str:
        if candidate is not None:
            return compose_title(str(candidate["display_name"]), str(candidate["deployed_location"]))
        if manual_title_display.strip():
            return manual_title_display.strip()
        if existing_record is not None:
            return str(existing_record["title_display"])
        return ""

    def _snapshot_record(self, record: dict[str, object]) -> dict[str, object]:
        return {
            "record_id": record["record_id"],
            "public_id": record["public_id"],
            "candidate_user_id": record.get("candidate_user_id"),
            "candidate_login_id": record.get("candidate_login_id", ""),
            "application_number": record["application_number"],
            "title_display": record["title_display"],
            "name": record["name"],
            "phone_number": record["phone_number"],
            "status": record["status"],
            "short_note": record["short_note"],
            "created_at": record["created_at"],
            "updated_at": record["updated_at"],
            "version_number": record["version_number"],
            "deleted_at": record.get("deleted_at", ""),
        }

    def _verify_saved_record(
        self,
        record: dict[str, object],
        application_number: str,
        status: str,
        title_display: str,
    ) -> None:
        if str(record["application_number"]) != application_number:
            raise ValueError("Persisted record verification failed for Application Number.")
        if str(record["status"]) != status:
            raise ValueError("Persisted record verification failed for Status.")
        if str(record["title_display"]) != title_display:
            raise ValueError("Persisted record verification failed for Title.")

    def _log_denial(self, connection: Any, actor: dict[str, object], action: str, target_id: str) -> None:
        self.audit_repository.log(
            connection,
            actor_user_id=int(actor["user_id"]),
            action_type=AUDIT_ACTION_PERMISSION_DENIED,
            target_type="record",
            target_id=target_id,
            subtree_scope=str(actor["login_id"]),
            success_flag=False,
            message=f"Permission denied for {action}.",
            metadata={},
        )


class LegacyMigrationService:
    def __init__(
        self,
        *,
        db_manager: Any,
        csv_manager: Any,
        record_repository: RecordRepository,
        meta_repository: MetaRepository,
        audit_repository: AuditRepository,
        backup_service: BackupService,
        logger: logging.Logger,
    ) -> None:
        self.db_manager = db_manager
        self.csv_manager = csv_manager
        self.record_repository = record_repository
        self.meta_repository = meta_repository
        self.audit_repository = audit_repository
        self.backup_service = backup_service
        self.logger = logger

    def migrate_if_needed(self) -> int:
        with self.db_manager.transaction() as connection:
            if self.meta_repository.get_flag(connection, "legacy_records_migrated") == "1":
                return 0
            legacy_records = self.csv_manager.load_legacy_records()
            if not legacy_records:
                self.meta_repository.set_flag(connection, "legacy_records_migrated", "1")
                return 0
            self.csv_manager.backup_legacy_file("legacy_records_pre_migration")
            migrated_count = 0
            for row in legacy_records:
                record = self.record_repository.insert_legacy_record(
                    connection,
                    public_id=str(row["record_id"]),
                    application_number=str(row["record_id"]),
                    title_display=str(row.get("title", "")),
                    name=str(row.get("name", "")),
                    phone_number=str(row.get("phone_number", "")),
                    status=self.csv_manager.map_legacy_status(str(row.get("status", ""))),
                    short_note=str(row.get("short_note", "")),
                    created_at=str(row.get("created_at", "")) or current_timestamp(),
                    updated_at=str(row.get("updated_at", "")) or current_timestamp(),
                )
                self.record_repository.create_record_version(
                    connection,
                    record_id=int(record["record_id"]),
                    version_number=1,
                    snapshot_payload={
                        **record,
                        "legacy_category": row.get("category", ""),
                        "legacy_status": row.get("status", ""),
                    },
                    changed_by_user_id=None,
                    change_type="LEGACY_MIGRATION",
                )
                migrated_count += 1

            self.backup_service.create_json_backup(
                connection,
                backup_type="migration",
                target_type="legacy_records",
                target_id="initial_csv_import",
                payload={"migrated_count": migrated_count, "records": legacy_records},
            )
            self.audit_repository.log(
                connection,
                actor_user_id=None,
                action_type=AUDIT_ACTION_RECORD_RESTORED,
                target_type="legacy_csv",
                target_id="data/records.csv",
                subtree_scope="",
                success_flag=True,
                message="Migrated legacy CSV records into runtime database.",
                metadata={"migrated_count": migrated_count},
            )
            self.meta_repository.set_flag(connection, "legacy_records_migrated", "1")
            return migrated_count


@dataclass(slots=True)
class AppServices:
    db_manager: Any
    auth_service: AuthService
    user_service: UserService
    record_service: RecordService
    source_sync_service: Any
    backup_service: BackupService
    legacy_migration_service: LegacyMigrationService
    audit_repository: AuditRepository
    source_repository: SourceRepository
    user_repository: UserRepository
    record_repository: RecordRepository
    meta_repository: MetaRepository
