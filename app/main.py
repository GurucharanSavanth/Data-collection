from __future__ import annotations

import logging
import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox

from authorization import AuthorizationService
from constants import APP_VERSION, DB_FILENAME
from csv_manager import CSVManager
from database import DatabaseManager
from gui import RecordManagerApp
from repositories import AuditRepository, BackupRepository, MetaRepository, RecordRepository, SourceRepository, UserRepository
from services import AppServices, AuthService, BackupService, LegacyMigrationService, RecordService, UserService
from session_manager import SessionManager
from source_sync import SourceSyncService
from utils import APP_ENCODING, ensure_dir, format_exception, safe_json_load, safe_json_write


DEFAULT_SETTINGS = {
    "app_name": "Record Manager Dashboard",
    "app_version": APP_VERSION,
    "window_title": "Record Manager Dashboard",
    "default_window_size": "1360x860",
}


def resolve_project_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def configure_logging(log_dir: Path) -> logging.Logger:
    ensure_dir(log_dir)
    log_path = log_dir / "application.log"

    logger = logging.getLogger("record_manager_dashboard")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    file_handler = logging.FileHandler(log_path, encoding=APP_ENCODING)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    return logger


def normalize_settings(settings_path: Path, loaded_settings: dict[str, object], logger: logging.Logger) -> dict[str, object]:
    normalized = dict(DEFAULT_SETTINGS)
    normalized["app_name"] = str(loaded_settings.get("app_name", DEFAULT_SETTINGS["app_name"]))
    normalized["window_title"] = str(loaded_settings.get("window_title", DEFAULT_SETTINGS["window_title"]))
    normalized["default_window_size"] = str(loaded_settings.get("default_window_size", DEFAULT_SETTINGS["default_window_size"]))

    if loaded_settings != normalized:
        logger.info("Normalizing settings to application schema version %s", APP_VERSION)
        safe_json_write(settings_path, normalized)
    return normalized


def build_app_services(project_root: Path, logger: logging.Logger) -> tuple[AppServices, Path]:
    data_dir = ensure_dir(project_root / "data")
    backup_dir = ensure_dir(data_dir / "backups")
    snapshot_dir = ensure_dir(data_dir / "snapshots")
    runtime_backup_dir = ensure_dir(backup_dir / "runtime")
    db_backup_dir = ensure_dir(backup_dir / "db")

    db_manager = DatabaseManager(data_dir / DB_FILENAME, backup_dir=db_backup_dir, logger=logger)
    db_manager.initialize()

    csv_manager = CSVManager(
        csv_path=data_dir / "records.csv",
        backup_dir=backup_dir,
        snapshot_dir=snapshot_dir,
        logger=logger,
    )
    user_repository = UserRepository()
    record_repository = RecordRepository()
    source_repository = SourceRepository()
    audit_repository = AuditRepository()
    backup_repository = BackupRepository()
    meta_repository = MetaRepository()

    authorization_service = AuthorizationService(user_repository)
    backup_service = BackupService(runtime_backup_dir, backup_repository, logger)
    legacy_migration_service = LegacyMigrationService(
        db_manager=db_manager,
        csv_manager=csv_manager,
        record_repository=record_repository,
        meta_repository=meta_repository,
        audit_repository=audit_repository,
        backup_service=backup_service,
        logger=logger,
    )
    auth_service = AuthService(
        db_manager=db_manager,
        user_repository=user_repository,
        audit_repository=audit_repository,
        meta_repository=meta_repository,
        logger=logger,
    )
    user_service = UserService(
        db_manager=db_manager,
        user_repository=user_repository,
        audit_repository=audit_repository,
        authorization_service=authorization_service,
        logger=logger,
    )
    record_service = RecordService(
        db_manager=db_manager,
        record_repository=record_repository,
        user_repository=user_repository,
        audit_repository=audit_repository,
        authorization_service=authorization_service,
        backup_service=backup_service,
        csv_manager=csv_manager,
        logger=logger,
    )
    source_sync_service = SourceSyncService(
        db_manager=db_manager,
        user_repository=user_repository,
        source_repository=source_repository,
        audit_repository=audit_repository,
        csv_manager=csv_manager,
        logger=logger,
    )
    services = AppServices(
        db_manager=db_manager,
        auth_service=auth_service,
        user_service=user_service,
        record_service=record_service,
        source_sync_service=source_sync_service,
        backup_service=backup_service,
        legacy_migration_service=legacy_migration_service,
        audit_repository=audit_repository,
        source_repository=source_repository,
        user_repository=user_repository,
        record_repository=record_repository,
        meta_repository=meta_repository,
    )
    return services, data_dir


def main() -> None:
    project_root = resolve_project_root()
    session_dir = ensure_dir(project_root / "session")
    log_dir = ensure_dir(session_dir / "logs")
    ensure_dir(session_dir / "invalid")
    config_dir = ensure_dir(project_root / "config")
    ensure_dir(config_dir / "invalid")

    logger = configure_logging(log_dir)
    settings_path = config_dir / "settings.json"
    settings = safe_json_load(settings_path, DEFAULT_SETTINGS, logger=logger, invalid_backup_dir=config_dir / "invalid")
    settings = normalize_settings(settings_path, settings, logger)

    session_manager = SessionManager(
        session_path=session_dir / "session_state.json",
        app_state_path=session_dir / "app_state.json",
        logger=logger,
    )
    app_state = session_manager.mark_startup()

    services, data_dir = build_app_services(project_root, logger)
    migrated_count = services.legacy_migration_service.migrate_if_needed()
    if migrated_count:
        logger.info("Migrated %s legacy CSV records into SQLite runtime store.", migrated_count)

    def global_exception_handler(exc_type, exc_value, exc_traceback) -> None:
        logger.error("Unhandled exception", exc_info=(exc_type, exc_value, exc_traceback))
        session_manager.record_error(str(exc_value))
        try:
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror(
                "Unexpected Error",
                "An unexpected error occurred.\n\n"
                "See session/logs/application.log for technical details.\n\n"
                f"{exc_value}",
            )
            root.destroy()
        except Exception:
            logger.error("Failed to show fatal error dialog.\n%s", format_exception())

    sys.excepthook = global_exception_handler

    logger.info("Starting application from %s", project_root)
    root = tk.Tk()
    RecordManagerApp(
        root=root,
        settings=settings,
        services=services,
        session_manager=session_manager,
        logger=logger,
        data_dir=data_dir,
        app_state=app_state,
    )

    try:
        root.mainloop()
    except Exception:
        logger.error("Fatal UI error\n%s", format_exception())
        session_manager.record_error("Fatal UI error")
        raise


if __name__ == "__main__":
    main()
