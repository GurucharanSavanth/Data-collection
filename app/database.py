from __future__ import annotations

import logging
import shutil
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from constants import APP_VERSION, DEFAULT_SOURCE_CONFIG
from utils import current_timestamp, current_timestamp_for_filename, ensure_dir


def row_to_dict(row: sqlite3.Row | None) -> dict[str, object] | None:
    if row is None:
        return None
    return {key: row[key] for key in row.keys()}


class DatabaseManager:
    def __init__(self, db_path: Path, backup_dir: Path, logger: logging.Logger) -> None:
        self.db_path = db_path
        self.backup_dir = backup_dir
        self.logger = logger

    def connect(self) -> sqlite3.Connection:
        ensure_dir(self.db_path.parent)
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA busy_timeout = 3000")
        return connection

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        connection = self.connect()
        try:
            yield connection
        finally:
            connection.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        ensure_dir(self.backup_dir)
        with self.transaction() as connection:
            self._ensure_meta_table(connection)
            current_version = self.get_schema_version(connection)
            if current_version < 1:
                self.logger.info("Applying database schema version 1")
                self._apply_migration_1(connection)
                self.set_schema_version(connection, 1)
            self._seed_default_meta(connection)
            self._seed_default_source_config(connection)

    def backup_database(self, prefix: str) -> Path:
        ensure_dir(self.backup_dir)
        target = self.backup_dir / f"{prefix}_{current_timestamp_for_filename()}{self.db_path.suffix or '.db'}"
        if self.db_path.exists():
            shutil.copy2(self.db_path, target)
        return target

    def _ensure_meta_table(self, connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS app_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )

    def get_schema_version(self, connection: sqlite3.Connection) -> int:
        row = connection.execute("SELECT value FROM app_meta WHERE key = 'schema_version'").fetchone()
        if row is None:
            return 0
        return int(row["value"])

    def set_schema_version(self, connection: sqlite3.Connection, version: int) -> None:
        connection.execute(
            """
            INSERT INTO app_meta(key, value)
            VALUES('schema_version', ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (str(version),),
        )

    def _seed_default_meta(self, connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            INSERT INTO app_meta(key, value)
            VALUES('app_version', ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (APP_VERSION,),
        )
        connection.execute(
            """
            INSERT INTO app_meta(key, value)
            VALUES('legacy_records_migrated', '0')
            ON CONFLICT(key) DO NOTHING
            """
        )
        connection.execute(
            """
            INSERT INTO app_meta(key, value)
            VALUES('bootstrap_completed', '0')
            ON CONFLICT(key) DO NOTHING
            """
        )

    def _seed_default_source_config(self, connection: sqlite3.Connection) -> None:
        existing = connection.execute("SELECT source_id FROM credential_source_config WHERE source_id = 1").fetchone()
        if existing is not None:
            return

        connection.execute(
            """
            INSERT INTO credential_source_config(
                source_id,
                source_mode,
                local_path,
                remote_url,
                is_active,
                last_sync_at,
                last_sync_status,
                last_checksum,
                last_error,
                created_at,
                updated_at
            )
            VALUES(1, :source_mode, :local_path, :remote_url, :is_active, :last_sync_at, :last_sync_status, :last_checksum, :last_error, :created_at, :updated_at)
            """,
            {
                **DEFAULT_SOURCE_CONFIG,
                "created_at": current_timestamp(),
                "updated_at": current_timestamp(),
            },
        )

    def _apply_migration_1(self, connection: sqlite3.Connection) -> None:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY AUTOINCREMENT,
                login_id TEXT NOT NULL UNIQUE,
                role TEXT NOT NULL CHECK(role IN ('SUPER_ADMIN', 'REGIONAL_MANAGER', 'ASSOCIATE_MANAGER', 'LOCAL_MANAGER', 'CANDIDATE')),
                password_hash TEXT NOT NULL,
                password_state TEXT NOT NULL CHECK(password_state IN ('ACTIVE', 'RESET_REQUIRED')),
                status TEXT NOT NULL DEFAULT 'ACTIVE' CHECK(status IN ('ACTIVE', 'DISABLED')),
                parent_user_id INTEGER NULL REFERENCES users(user_id) ON DELETE RESTRICT,
                active_flag INTEGER NOT NULL DEFAULT 1 CHECK(active_flag IN (0, 1)),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_users_parent_user_id ON users(parent_user_id);
            CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);

            CREATE TABLE IF NOT EXISTS user_profiles (
                user_id INTEGER PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
                display_name TEXT NOT NULL,
                deployed_location TEXT NOT NULL DEFAULT '',
                phone TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS records (
                record_id INTEGER PRIMARY KEY AUTOINCREMENT,
                public_id TEXT NOT NULL UNIQUE,
                candidate_user_id INTEGER NULL REFERENCES users(user_id) ON DELETE RESTRICT,
                application_number TEXT NOT NULL UNIQUE,
                title_display TEXT NOT NULL,
                name TEXT NOT NULL,
                phone_number TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('Open', 'Clone', 'In Progress', 'Forfeited')),
                short_note TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                created_by_user_id INTEGER NULL REFERENCES users(user_id) ON DELETE SET NULL,
                updated_by_user_id INTEGER NULL REFERENCES users(user_id) ON DELETE SET NULL,
                deleted_at TEXT NULL,
                deleted_by_user_id INTEGER NULL REFERENCES users(user_id) ON DELETE SET NULL,
                version_number INTEGER NOT NULL DEFAULT 1 CHECK(version_number >= 1)
            );

            CREATE INDEX IF NOT EXISTS idx_records_candidate_user_id ON records(candidate_user_id);
            CREATE INDEX IF NOT EXISTS idx_records_created_at ON records(created_at);

            CREATE TABLE IF NOT EXISTS record_versions (
                version_id INTEGER PRIMARY KEY AUTOINCREMENT,
                record_id INTEGER NOT NULL REFERENCES records(record_id) ON DELETE CASCADE,
                version_number INTEGER NOT NULL,
                snapshot_payload TEXT NOT NULL,
                changed_by_user_id INTEGER NULL REFERENCES users(user_id) ON DELETE SET NULL,
                changed_at TEXT NOT NULL,
                change_type TEXT NOT NULL,
                UNIQUE(record_id, version_number)
            );

            CREATE TABLE IF NOT EXISTS credential_source_config (
                source_id INTEGER PRIMARY KEY CHECK(source_id = 1),
                source_mode TEXT NOT NULL CHECK(source_mode IN ('OFFLINE', 'ONLINE')),
                local_path TEXT NOT NULL DEFAULT '',
                remote_url TEXT NOT NULL DEFAULT '',
                is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0, 1)),
                last_sync_at TEXT NOT NULL DEFAULT '',
                last_sync_status TEXT NOT NULL DEFAULT 'Never synced',
                last_checksum TEXT NOT NULL DEFAULT '',
                last_error TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS credential_source_snapshot (
                snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id INTEGER NOT NULL REFERENCES credential_source_config(source_id) ON DELETE CASCADE,
                source_mode TEXT NOT NULL,
                source_reference TEXT NOT NULL,
                imported_at TEXT NOT NULL,
                raw_snapshot_path TEXT NOT NULL,
                checksum TEXT NOT NULL,
                parsed_row_count INTEGER NOT NULL DEFAULT 0,
                accepted_row_count INTEGER NOT NULL DEFAULT 0,
                rejected_row_count INTEGER NOT NULL DEFAULT 0,
                sync_status TEXT NOT NULL,
                error_summary TEXT NOT NULL DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS source_row_mappings (
                mapping_id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_id INTEGER NOT NULL REFERENCES credential_source_snapshot(snapshot_id) ON DELETE CASCADE,
                source_row_number INTEGER NOT NULL,
                source_login_id TEXT NOT NULL,
                user_id INTEGER NULL REFERENCES users(user_id) ON DELETE SET NULL,
                action_taken TEXT NOT NULL,
                validation_errors TEXT NOT NULL DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS audit_log (
                audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
                actor_user_id INTEGER NULL REFERENCES users(user_id) ON DELETE SET NULL,
                action_type TEXT NOT NULL,
                target_type TEXT NOT NULL,
                target_id TEXT NOT NULL,
                subtree_scope TEXT NOT NULL DEFAULT '',
                success_flag INTEGER NOT NULL CHECK(success_flag IN (0, 1)),
                message TEXT NOT NULL,
                metadata TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_audit_log_created_at ON audit_log(created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_audit_log_actor ON audit_log(actor_user_id);

            CREATE TABLE IF NOT EXISTS backup_registry (
                backup_id INTEGER PRIMARY KEY AUTOINCREMENT,
                backup_type TEXT NOT NULL,
                target_type TEXT NOT NULL,
                target_id TEXT NOT NULL,
                artifact_path TEXT NOT NULL,
                artifact_hash TEXT NOT NULL,
                restore_test_status TEXT NOT NULL DEFAULT 'PENDING',
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_backup_registry_target ON backup_registry(target_type, target_id);
            """
        )
