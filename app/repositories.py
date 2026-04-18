from __future__ import annotations

import json
import sqlite3
from typing import Any

from database import row_to_dict
from utils import current_timestamp


def rows_to_dicts(rows: list[sqlite3.Row]) -> list[dict[str, object]]:
    return [{key: row[key] for key in row.keys()} for row in rows]


class MetaRepository:
    def get_flag(self, connection: sqlite3.Connection, key: str, default: str = "0") -> str:
        row = connection.execute("SELECT value FROM app_meta WHERE key = ?", (key,)).fetchone()
        if row is None:
            return default
        return str(row["value"])

    def set_flag(self, connection: sqlite3.Connection, key: str, value: str) -> None:
        connection.execute(
            """
            INSERT INTO app_meta(key, value)
            VALUES(?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, value),
        )


class UserRepository:
    def count_users(self, connection: sqlite3.Connection) -> int:
        row = connection.execute("SELECT COUNT(*) AS count FROM users").fetchone()
        return int(row["count"])

    def create_user(
        self,
        connection: sqlite3.Connection,
        *,
        login_id: str,
        role: str,
        password_hash: str,
        password_state: str,
        parent_user_id: int | None,
        display_name: str,
        deployed_location: str,
        phone: str,
        active_flag: bool = True,
    ) -> dict[str, object]:
        timestamp = current_timestamp()
        cursor = connection.execute(
            """
            INSERT INTO users(
                login_id,
                role,
                password_hash,
                password_state,
                status,
                parent_user_id,
                active_flag,
                created_at,
                updated_at
            )
            VALUES(?, ?, ?, ?, 'ACTIVE', ?, ?, ?, ?)
            """,
            (
                login_id,
                role,
                password_hash,
                password_state,
                parent_user_id,
                1 if active_flag else 0,
                timestamp,
                timestamp,
            ),
        )
        user_id = int(cursor.lastrowid)
        connection.execute(
            """
            INSERT INTO user_profiles(
                user_id,
                display_name,
                deployed_location,
                phone,
                created_at,
                updated_at
            )
            VALUES(?, ?, ?, ?, ?, ?)
            """,
            (user_id, display_name, deployed_location, phone, timestamp, timestamp),
        )
        return self.get_user(connection, user_id)

    def update_user(
        self,
        connection: sqlite3.Connection,
        user_id: int,
        *,
        parent_user_id: int | None,
        display_name: str,
        deployed_location: str,
        phone: str,
        active_flag: bool,
    ) -> dict[str, object]:
        timestamp = current_timestamp()
        connection.execute(
            """
            UPDATE users
            SET parent_user_id = ?, active_flag = ?, updated_at = ?, status = CASE WHEN ? = 1 THEN 'ACTIVE' ELSE 'DISABLED' END
            WHERE user_id = ?
            """,
            (parent_user_id, 1 if active_flag else 0, timestamp, 1 if active_flag else 0, user_id),
        )
        connection.execute(
            """
            UPDATE user_profiles
            SET display_name = ?, deployed_location = ?, phone = ?, updated_at = ?
            WHERE user_id = ?
            """,
            (display_name, deployed_location, phone, timestamp, user_id),
        )
        return self.get_user(connection, user_id)

    def set_password(
        self,
        connection: sqlite3.Connection,
        user_id: int,
        password_hash: str,
        password_state: str,
    ) -> None:
        connection.execute(
            """
            UPDATE users
            SET password_hash = ?, password_state = ?, updated_at = ?
            WHERE user_id = ?
            """,
            (password_hash, password_state, current_timestamp(), user_id),
        )

    def get_user_by_login(self, connection: sqlite3.Connection, login_id: str) -> dict[str, object] | None:
        row = connection.execute(
            """
            SELECT
                u.*,
                p.display_name,
                p.deployed_location,
                p.phone
            FROM users u
            INNER JOIN user_profiles p ON p.user_id = u.user_id
            WHERE u.login_id = ?
            """,
            (login_id,),
        ).fetchone()
        return row_to_dict(row)

    def get_user(self, connection: sqlite3.Connection, user_id: int) -> dict[str, object] | None:
        row = connection.execute(
            """
            SELECT
                u.*,
                p.display_name,
                p.deployed_location,
                p.phone
            FROM users u
            INNER JOIN user_profiles p ON p.user_id = u.user_id
            WHERE u.user_id = ?
            """,
            (user_id,),
        ).fetchone()
        return row_to_dict(row)

    def list_all_users(self, connection: sqlite3.Connection) -> list[dict[str, object]]:
        rows = connection.execute(
            """
            SELECT
                u.*,
                p.display_name,
                p.deployed_location,
                p.phone
            FROM users u
            INNER JOIN user_profiles p ON p.user_id = u.user_id
            ORDER BY p.display_name COLLATE NOCASE, u.login_id COLLATE NOCASE
            """
        ).fetchall()
        return rows_to_dicts(rows)

    def get_subtree_user_ids(self, connection: sqlite3.Connection, root_user_id: int) -> list[int]:
        rows = connection.execute(
            """
            WITH RECURSIVE subtree(user_id) AS (
                SELECT user_id FROM users WHERE user_id = ?
                UNION ALL
                SELECT child.user_id
                FROM users child
                INNER JOIN subtree parent ON parent.user_id = child.parent_user_id
            )
            SELECT user_id FROM subtree
            """,
            (root_user_id,),
        ).fetchall()
        return [int(row["user_id"]) for row in rows]

    def get_subtree_users(self, connection: sqlite3.Connection, root_user_id: int) -> list[dict[str, object]]:
        rows = connection.execute(
            """
            WITH RECURSIVE subtree(user_id, depth) AS (
                SELECT user_id, 0 FROM users WHERE user_id = ?
                UNION ALL
                SELECT child.user_id, subtree.depth + 1
                FROM users child
                INNER JOIN subtree ON subtree.user_id = child.parent_user_id
            )
            SELECT
                subtree.depth,
                u.*,
                p.display_name,
                p.deployed_location,
                p.phone
            FROM subtree
            INNER JOIN users u ON u.user_id = subtree.user_id
            INNER JOIN user_profiles p ON p.user_id = u.user_id
            ORDER BY subtree.depth ASC, p.display_name COLLATE NOCASE, u.login_id COLLATE NOCASE
            """,
            (root_user_id,),
        ).fetchall()
        return rows_to_dicts(rows)

    def get_user_path(self, connection: sqlite3.Connection, user_id: int) -> list[dict[str, object]]:
        rows = connection.execute(
            """
            WITH RECURSIVE path(user_id, parent_user_id, login_id, role, depth) AS (
                SELECT user_id, parent_user_id, login_id, role, 0
                FROM users
                WHERE user_id = ?
                UNION ALL
                SELECT u.user_id, u.parent_user_id, u.login_id, u.role, path.depth + 1
                FROM users u
                INNER JOIN path ON path.parent_user_id = u.user_id
            )
            SELECT path.user_id, path.parent_user_id, path.login_id, path.role, p.display_name, p.deployed_location, p.phone, path.depth
            FROM path
            INNER JOIN user_profiles p ON p.user_id = path.user_id
            ORDER BY path.depth DESC
            """,
            (user_id,),
        ).fetchall()
        return rows_to_dicts(rows)

    def list_children(self, connection: sqlite3.Connection, parent_user_id: int) -> list[dict[str, object]]:
        rows = connection.execute(
            """
            SELECT
                u.*,
                p.display_name,
                p.deployed_location,
                p.phone
            FROM users u
            INNER JOIN user_profiles p ON p.user_id = u.user_id
            WHERE u.parent_user_id = ?
            ORDER BY p.display_name COLLATE NOCASE
            """,
            (parent_user_id,),
        ).fetchall()
        return rows_to_dicts(rows)

    def build_tree(self, connection: sqlite3.Connection, root_user_id: int) -> list[dict[str, object]]:
        subtree_users = self.get_subtree_users(connection, root_user_id)
        records_by_user = {
            int(row["candidate_user_id"]): int(row["record_count"])
            for row in connection.execute(
                """
                SELECT candidate_user_id, COUNT(*) AS record_count
                FROM records
                WHERE deleted_at IS NULL AND candidate_user_id IS NOT NULL
                GROUP BY candidate_user_id
                """
            ).fetchall()
        }

        nodes: dict[int, dict[str, object]] = {}
        roots: list[dict[str, object]] = []
        for user in subtree_users:
            user_id = int(user["user_id"])
            node = {
                "user_id": user_id,
                "login_id": str(user["login_id"]),
                "role": str(user["role"]),
                "display_name": str(user["display_name"]),
                "deployed_location": str(user["deployed_location"]),
                "phone": str(user["phone"]),
                "parent_user_id": user["parent_user_id"],
                "depth": int(user["depth"]),
                "record_count": records_by_user.get(user_id, 0),
                "children": [],
            }
            nodes[user_id] = node

        for node in nodes.values():
            parent_id = node["parent_user_id"]
            if parent_id is None or int(parent_id) not in nodes:
                roots.append(node)
                continue
            nodes[int(parent_id)]["children"].append(node)

        return roots


class RecordRepository:
    def insert_legacy_record(
        self,
        connection: sqlite3.Connection,
        *,
        public_id: str,
        application_number: str,
        title_display: str,
        name: str,
        phone_number: str,
        status: str,
        short_note: str,
        created_at: str,
        updated_at: str,
    ) -> dict[str, object]:
        cursor = connection.execute(
            """
            INSERT INTO records(
                public_id,
                candidate_user_id,
                application_number,
                title_display,
                name,
                phone_number,
                status,
                short_note,
                created_at,
                updated_at,
                created_by_user_id,
                updated_by_user_id,
                version_number
            )
            VALUES(?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, 1)
            """,
            (
                public_id,
                application_number,
                title_display,
                name,
                phone_number,
                status,
                short_note,
                created_at,
                updated_at,
            ),
        )
        return self.get_record(connection, int(cursor.lastrowid))

    def create_record(
        self,
        connection: sqlite3.Connection,
        *,
        public_id: str,
        candidate_user_id: int | None,
        application_number: str,
        title_display: str,
        name: str,
        phone_number: str,
        status: str,
        short_note: str,
        actor_user_id: int | None,
    ) -> dict[str, object]:
        timestamp = current_timestamp()
        cursor = connection.execute(
            """
            INSERT INTO records(
                public_id,
                candidate_user_id,
                application_number,
                title_display,
                name,
                phone_number,
                status,
                short_note,
                created_at,
                updated_at,
                created_by_user_id,
                updated_by_user_id,
                version_number
            )
            VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            """,
            (
                public_id,
                candidate_user_id,
                application_number,
                title_display,
                name,
                phone_number,
                status,
                short_note,
                timestamp,
                timestamp,
                actor_user_id,
                actor_user_id,
            ),
        )
        return self.get_record(connection, int(cursor.lastrowid))

    def update_record(
        self,
        connection: sqlite3.Connection,
        record_id: int,
        *,
        candidate_user_id: int | None,
        application_number: str,
        title_display: str,
        name: str,
        phone_number: str,
        status: str,
        short_note: str,
        actor_user_id: int | None,
        version_number: int,
    ) -> dict[str, object]:
        connection.execute(
            """
            UPDATE records
            SET candidate_user_id = ?,
                application_number = ?,
                title_display = ?,
                name = ?,
                phone_number = ?,
                status = ?,
                short_note = ?,
                updated_at = ?,
                updated_by_user_id = ?,
                version_number = ?
            WHERE record_id = ?
            """,
            (
                candidate_user_id,
                application_number,
                title_display,
                name,
                phone_number,
                status,
                short_note,
                current_timestamp(),
                actor_user_id,
                version_number,
                record_id,
            ),
        )
        return self.get_record(connection, record_id)

    def archive_record(
        self,
        connection: sqlite3.Connection,
        record_id: int,
        *,
        actor_user_id: int | None,
        version_number: int,
    ) -> dict[str, object]:
        connection.execute(
            """
            UPDATE records
            SET deleted_at = ?, deleted_by_user_id = ?, updated_at = ?, updated_by_user_id = ?, version_number = ?
            WHERE record_id = ?
            """,
            (
                current_timestamp(),
                actor_user_id,
                current_timestamp(),
                actor_user_id,
                version_number,
                record_id,
            ),
        )
        return self.get_record(connection, record_id)

    def get_record(self, connection: sqlite3.Connection, record_id: int) -> dict[str, object] | None:
        row = connection.execute(
            """
            SELECT
                r.*,
                candidate.login_id AS candidate_login_id,
                candidate_profile.display_name AS candidate_display_name,
                candidate_profile.deployed_location AS candidate_deployed_location
            FROM records r
            LEFT JOIN users candidate ON candidate.user_id = r.candidate_user_id
            LEFT JOIN user_profiles candidate_profile ON candidate_profile.user_id = candidate.user_id
            WHERE r.record_id = ?
            """,
            (record_id,),
        ).fetchone()
        return row_to_dict(row)

    def get_record_by_public_id(self, connection: sqlite3.Connection, public_id: str) -> dict[str, object] | None:
        row = connection.execute(
            """
            SELECT
                r.*,
                candidate.login_id AS candidate_login_id,
                candidate_profile.display_name AS candidate_display_name,
                candidate_profile.deployed_location AS candidate_deployed_location
            FROM records r
            LEFT JOIN users candidate ON candidate.user_id = r.candidate_user_id
            LEFT JOIN user_profiles candidate_profile ON candidate_profile.user_id = candidate.user_id
            WHERE r.public_id = ?
            """,
            (public_id,),
        ).fetchone()
        return row_to_dict(row)

    def list_records_for_users(
        self,
        connection: sqlite3.Connection,
        user_ids: list[int],
        *,
        include_unassigned: bool = False,
    ) -> list[dict[str, object]]:
        if not user_ids and not include_unassigned:
            return []

        placeholders = ", ".join("?" for _ in user_ids) if user_ids else "NULL"
        where_parts = [f"r.candidate_user_id IN ({placeholders})"] if user_ids else []
        params: list[object] = list(user_ids)
        if include_unassigned:
            where_parts.append("r.candidate_user_id IS NULL")
        where_clause = " OR ".join(where_parts)
        rows = connection.execute(
            f"""
            SELECT
                r.*,
                candidate.login_id AS candidate_login_id,
                candidate_profile.display_name AS candidate_display_name,
                candidate_profile.deployed_location AS candidate_deployed_location
            FROM records r
            LEFT JOIN users candidate ON candidate.user_id = r.candidate_user_id
            LEFT JOIN user_profiles candidate_profile ON candidate_profile.user_id = candidate.user_id
            WHERE r.deleted_at IS NULL
              AND ({where_clause})
            ORDER BY r.updated_at DESC, r.record_id DESC
            """,
            params,
        ).fetchall()
        return rows_to_dicts(rows)

    def list_all_records(self, connection: sqlite3.Connection) -> list[dict[str, object]]:
        rows = connection.execute(
            """
            SELECT
                r.*,
                candidate.login_id AS candidate_login_id,
                candidate_profile.display_name AS candidate_display_name,
                candidate_profile.deployed_location AS candidate_deployed_location
            FROM records r
            LEFT JOIN users candidate ON candidate.user_id = r.candidate_user_id
            LEFT JOIN user_profiles candidate_profile ON candidate_profile.user_id = candidate.user_id
            WHERE r.deleted_at IS NULL
            ORDER BY r.updated_at DESC, r.record_id DESC
            """
        ).fetchall()
        return rows_to_dicts(rows)

    def application_number_exists(
        self,
        connection: sqlite3.Connection,
        application_number: str,
        exclude_record_id: int | None = None,
    ) -> bool:
        if exclude_record_id is None:
            row = connection.execute(
                "SELECT record_id FROM records WHERE application_number = ? LIMIT 1",
                (application_number,),
            ).fetchone()
        else:
            row = connection.execute(
                "SELECT record_id FROM records WHERE application_number = ? AND record_id != ? LIMIT 1",
                (application_number, exclude_record_id),
            ).fetchone()
        return row is not None

    def create_record_version(
        self,
        connection: sqlite3.Connection,
        *,
        record_id: int,
        version_number: int,
        snapshot_payload: dict[str, object],
        changed_by_user_id: int | None,
        change_type: str,
    ) -> dict[str, object]:
        cursor = connection.execute(
            """
            INSERT INTO record_versions(
                record_id,
                version_number,
                snapshot_payload,
                changed_by_user_id,
                changed_at,
                change_type
            )
            VALUES(?, ?, ?, ?, ?, ?)
            """,
            (
                record_id,
                version_number,
                json.dumps(snapshot_payload, ensure_ascii=False, sort_keys=True),
                changed_by_user_id,
                current_timestamp(),
                change_type,
            ),
        )
        row = connection.execute(
            "SELECT * FROM record_versions WHERE version_id = ?",
            (int(cursor.lastrowid),),
        ).fetchone()
        return row_to_dict(row)

    def list_record_versions(self, connection: sqlite3.Connection, record_id: int) -> list[dict[str, object]]:
        rows = connection.execute(
            """
            SELECT version_id, record_id, version_number, snapshot_payload, changed_by_user_id, changed_at, change_type
            FROM record_versions
            WHERE record_id = ?
            ORDER BY version_number DESC
            """,
            (record_id,),
        ).fetchall()
        results = []
        for row in rows:
            item = row_to_dict(row) or {}
            item["snapshot_payload"] = json.loads(str(item["snapshot_payload"]))
            results.append(item)
        return results

    def get_record_version(self, connection: sqlite3.Connection, version_id: int) -> dict[str, object] | None:
        row = connection.execute(
            "SELECT * FROM record_versions WHERE version_id = ?",
            (version_id,),
        ).fetchone()
        item = row_to_dict(row)
        if item is not None:
            item["snapshot_payload"] = json.loads(str(item["snapshot_payload"]))
        return item


class SourceRepository:
    def get_source_config(self, connection: sqlite3.Connection) -> dict[str, object]:
        row = connection.execute("SELECT * FROM credential_source_config WHERE source_id = 1").fetchone()
        return row_to_dict(row) or {}

    def update_source_config(
        self,
        connection: sqlite3.Connection,
        *,
        source_mode: str,
        local_path: str,
        remote_url: str,
        last_sync_status: str | None = None,
        last_error: str | None = None,
        last_checksum: str | None = None,
        last_sync_at: str | None = None,
    ) -> dict[str, object]:
        existing = self.get_source_config(connection)
        connection.execute(
            """
            UPDATE credential_source_config
            SET source_mode = ?,
                local_path = ?,
                remote_url = ?,
                last_sync_status = ?,
                last_error = ?,
                last_checksum = ?,
                last_sync_at = ?,
                updated_at = ?
            WHERE source_id = 1
            """,
            (
                source_mode,
                local_path,
                remote_url,
                last_sync_status if last_sync_status is not None else existing.get("last_sync_status", ""),
                last_error if last_error is not None else existing.get("last_error", ""),
                last_checksum if last_checksum is not None else existing.get("last_checksum", ""),
                last_sync_at if last_sync_at is not None else existing.get("last_sync_at", ""),
                current_timestamp(),
            ),
        )
        return self.get_source_config(connection)

    def create_source_snapshot(
        self,
        connection: sqlite3.Connection,
        *,
        source_mode: str,
        source_reference: str,
        raw_snapshot_path: str,
        checksum: str,
        parsed_row_count: int,
        accepted_row_count: int,
        rejected_row_count: int,
        sync_status: str,
        error_summary: str,
    ) -> dict[str, object]:
        cursor = connection.execute(
            """
            INSERT INTO credential_source_snapshot(
                source_id,
                source_mode,
                source_reference,
                imported_at,
                raw_snapshot_path,
                checksum,
                parsed_row_count,
                accepted_row_count,
                rejected_row_count,
                sync_status,
                error_summary
            )
            VALUES(1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                source_mode,
                source_reference,
                current_timestamp(),
                raw_snapshot_path,
                checksum,
                parsed_row_count,
                accepted_row_count,
                rejected_row_count,
                sync_status,
                error_summary,
            ),
        )
        row = connection.execute(
            "SELECT * FROM credential_source_snapshot WHERE snapshot_id = ?",
            (int(cursor.lastrowid),),
        ).fetchone()
        return row_to_dict(row) or {}

    def add_source_row_mapping(
        self,
        connection: sqlite3.Connection,
        *,
        snapshot_id: int,
        source_row_number: int,
        source_login_id: str,
        user_id: int | None,
        action_taken: str,
        validation_errors: str,
    ) -> None:
        connection.execute(
            """
            INSERT INTO source_row_mappings(
                snapshot_id,
                source_row_number,
                source_login_id,
                user_id,
                action_taken,
                validation_errors
            )
            VALUES(?, ?, ?, ?, ?, ?)
            """,
            (
                snapshot_id,
                source_row_number,
                source_login_id,
                user_id,
                action_taken,
                validation_errors,
            ),
        )

    def list_source_snapshots(self, connection: sqlite3.Connection, limit: int = 25) -> list[dict[str, object]]:
        rows = connection.execute(
            """
            SELECT *
            FROM credential_source_snapshot
            ORDER BY imported_at DESC, snapshot_id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return rows_to_dicts(rows)


class AuditRepository:
    def log(
        self,
        connection: sqlite3.Connection,
        *,
        actor_user_id: int | None,
        action_type: str,
        target_type: str,
        target_id: str,
        subtree_scope: str,
        success_flag: bool,
        message: str,
        metadata: dict[str, object] | None = None,
    ) -> None:
        connection.execute(
            """
            INSERT INTO audit_log(
                actor_user_id,
                action_type,
                target_type,
                target_id,
                subtree_scope,
                success_flag,
                message,
                metadata,
                created_at
            )
            VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                actor_user_id,
                action_type,
                target_type,
                target_id,
                subtree_scope,
                1 if success_flag else 0,
                message,
                json.dumps(metadata or {}, ensure_ascii=False, sort_keys=True),
                current_timestamp(),
            ),
        )

    def list_recent(self, connection: sqlite3.Connection, limit: int = 100) -> list[dict[str, object]]:
        rows = connection.execute(
            """
            SELECT
                audit_id,
                actor_user_id,
                action_type,
                target_type,
                target_id,
                subtree_scope,
                success_flag,
                message,
                metadata,
                created_at
            FROM audit_log
            ORDER BY created_at DESC, audit_id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        results = []
        for row in rows:
            item = row_to_dict(row) or {}
            item["metadata"] = json.loads(str(item["metadata"]))
            results.append(item)
        return results


class BackupRepository:
    def create_backup_entry(
        self,
        connection: sqlite3.Connection,
        *,
        backup_type: str,
        target_type: str,
        target_id: str,
        artifact_path: str,
        artifact_hash: str,
        restore_test_status: str = "PENDING",
    ) -> dict[str, object]:
        cursor = connection.execute(
            """
            INSERT INTO backup_registry(
                backup_type,
                target_type,
                target_id,
                artifact_path,
                artifact_hash,
                restore_test_status,
                created_at
            )
            VALUES(?, ?, ?, ?, ?, ?, ?)
            """,
            (
                backup_type,
                target_type,
                target_id,
                artifact_path,
                artifact_hash,
                restore_test_status,
                current_timestamp(),
            ),
        )
        row = connection.execute(
            "SELECT * FROM backup_registry WHERE backup_id = ?",
            (int(cursor.lastrowid),),
        ).fetchone()
        return row_to_dict(row) or {}

    def list_backups(self, connection: sqlite3.Connection, limit: int = 100) -> list[dict[str, object]]:
        rows = connection.execute(
            """
            SELECT *
            FROM backup_registry
            ORDER BY created_at DESC, backup_id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return rows_to_dicts(rows)
