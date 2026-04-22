from __future__ import annotations

import argparse
import logging
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
import tkinter as tk
from tkinter import messagebox
from typing import Any

from candidate_manager import CandidateManager
from csv_manager import CSVManager
from gui import RecordManagerApp
from runtime_paths import AppPaths, build_app_paths, prepare_storage
from self_test import run_self_test
from session_manager import SessionManager
from utils import APP_ENCODING, format_exception, safe_json_load, safe_json_write
from version_history_manager import VersionHistoryManager


DEFAULT_SETTINGS = {
    "app_name": "Record Manager Dashboard",
    "app_version": "2.0.0",
    "window_title": "Record Manager Dashboard",
    "default_window_size": "1280x800",
    "csv_headers": [
        "record_id",
        "title",
        "application_number",
        "referral_number",
        "candidate_id",
        "name",
        "phone_number",
        "status",
        "short_note",
        "archived_at",
        "created_at",
        "updated_at",
    ],
    "status_values": ["Open", "Clone", "In Progress", "Forfeited"],
}


@dataclass(frozen=True)
class AppContext:
    paths: AppPaths
    logger: logging.Logger
    settings: dict[str, Any]
    session_manager: SessionManager
    csv_manager: CSVManager
    candidate_manager: CandidateManager
    version_history_manager: VersionHistoryManager


def configure_logging(log_dir: Path) -> logging.Logger:
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "application.log"

    logger = logging.getLogger("record_manager_dashboard")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")

    file_handler = logging.FileHandler(log_path, encoding=APP_ENCODING)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger


def normalize_settings(settings_path: Path, loaded_settings: dict[str, object], logger: logging.Logger) -> dict[str, Any]:
    normalized = dict(DEFAULT_SETTINGS)
    normalized["app_name"] = str(loaded_settings.get("app_name", DEFAULT_SETTINGS["app_name"]))
    normalized["window_title"] = str(loaded_settings.get("window_title", DEFAULT_SETTINGS["window_title"]))
    normalized["default_window_size"] = str(loaded_settings.get("default_window_size", DEFAULT_SETTINGS["default_window_size"]))
    normalized["csv_headers"] = list(DEFAULT_SETTINGS["csv_headers"])
    normalized["status_values"] = list(DEFAULT_SETTINGS["status_values"])

    if not settings_path.exists() or loaded_settings != normalized:
        logger.info("Normalizing settings to application schema version %s", DEFAULT_SETTINGS["app_version"])
        safe_json_write(settings_path, normalized)

    return normalized


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Record Manager Dashboard")
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run non-interactive record/candidate persistence validation and exit.",
    )
    parser.add_argument(
        "--startup-smoke",
        action="store_true",
        help="Build the Tk interface, process one update cycle, then exit.",
    )
    parser.add_argument(
        "--storage-root",
        help="Override writable storage root. Useful for validation or portable runs.",
    )
    parser.add_argument(
        "--report",
        help="Write JSON status output to this path for automated validation.",
    )
    return parser


def initialize_context(
    storage_root_override: Path | None = None,
    *,
    allow_legacy_migration: bool,
) -> AppContext:
    paths = build_app_paths(storage_root_override)
    migration_events = prepare_storage(paths, allow_legacy_migration=allow_legacy_migration)

    logger = configure_logging(paths.log_dir)
    logger.info("Install root: %s", paths.install_root)
    logger.info("Resource root: %s", paths.resource_root)
    logger.info("Storage root: %s", paths.storage_root)
    for event in migration_events:
        logger.info(event)

    settings_path = paths.config_dir / "settings.json"
    settings = safe_json_load(
        settings_path,
        DEFAULT_SETTINGS,
        logger=logger,
        invalid_backup_dir=paths.config_invalid_dir,
    )
    settings = normalize_settings(settings_path, settings, logger)

    return AppContext(
        paths=paths,
        logger=logger,
        settings=settings,
        session_manager=SessionManager(
            session_path=paths.session_dir / "session_state.json",
            app_state_path=paths.session_dir / "app_state.json",
            logger=logger,
        ),
        csv_manager=CSVManager(
            csv_path=paths.data_dir / "records.csv",
            backup_dir=paths.backup_dir,
            temp_dir=paths.temp_dir,
            headers=list(settings["csv_headers"]),
            logger=logger,
        ),
        candidate_manager=CandidateManager(
            candidate_path=paths.data_dir / "candidates.json",
            logger=logger,
        ),
        version_history_manager=VersionHistoryManager(
            history_path=paths.data_dir / "record_versions.json",
            logger=logger,
        ),
    )


def write_report(report_path: Path | None, payload: dict[str, Any]) -> None:
    if report_path is None:
        return
    safe_json_write(report_path, payload)


def run_startup_smoke(context: AppContext) -> dict[str, Any]:
    context.logger.info("Starting startup smoke.")
    root = tk.Tk()
    root.withdraw()
    try:
        app = RecordManagerApp(
            root=root,
            settings=context.settings,
            csv_manager=context.csv_manager,
            candidate_manager=context.candidate_manager,
            session_manager=context.session_manager,
            version_history_manager=context.version_history_manager,
            logger=context.logger,
            csv_path=context.paths.data_dir / "records.csv",
        )
        root.update_idletasks()
        root.update()
        app.on_close()
        return {
            "status": "ok",
            "mode": "startup_smoke",
            "storage_root": str(context.paths.storage_root),
            "window_title": str(context.settings.get("window_title", "")),
        }
    finally:
        try:
            if root.winfo_exists():
                root.destroy()
        except tk.TclError:
            pass


def run_gui(context: AppContext) -> None:
    context.logger.info("Starting application from storage root %s", context.paths.storage_root)
    root = tk.Tk()

    def report_to_user(exc_value: BaseException) -> None:
        try:
            messagebox.showerror(
                "Unexpected Error",
                "An unexpected error occurred.\n\n"
                "The technical details were written to session/logs/application.log.\n\n"
                f"{exc_value}",
                parent=root,
            )
        except Exception:
            context.logger.exception("Failed to display error dialog")

    def global_exception_handler(exc_type, exc_value, exc_traceback) -> None:
        context.logger.error("Unhandled exception", exc_info=(exc_type, exc_value, exc_traceback))
        try:
            context.session_manager.record_error(str(exc_value))
        except Exception:
            context.logger.exception("Failed to record error state from excepthook")
        if root.winfo_exists():
            report_to_user(exc_value)

    def tk_callback_exception(exc_type, exc_value, exc_traceback) -> None:
        context.logger.error("Unhandled Tk callback exception", exc_info=(exc_type, exc_value, exc_traceback))
        try:
            context.session_manager.record_error(str(exc_value))
        except Exception:
            context.logger.exception("Failed to record Tk callback error state")
        report_to_user(exc_value)

    sys.excepthook = global_exception_handler
    root.report_callback_exception = tk_callback_exception

    RecordManagerApp(
        root=root,
        settings=context.settings,
        csv_manager=context.csv_manager,
        candidate_manager=context.candidate_manager,
        session_manager=context.session_manager,
        version_history_manager=context.version_history_manager,
        logger=context.logger,
        csv_path=context.paths.data_dir / "records.csv",
    )

    try:
        root.mainloop()
    except Exception:
        context.logger.error("Fatal UI error\n%s", format_exception())
        context.session_manager.record_error("Fatal UI error")
        raise


def main(argv: list[str] | None = None) -> int:
    parser = build_argument_parser()
    args = parser.parse_args(argv)

    temp_storage_root: Path | None = None
    storage_root_override = Path(args.storage_root).expanduser() if args.storage_root else None
    allow_legacy_migration = storage_root_override is None

    if (args.self_test or args.startup_smoke) and storage_root_override is None:
        temp_storage_root = Path(tempfile.mkdtemp(prefix="record_manager_validation_"))
        storage_root_override = temp_storage_root
        allow_legacy_migration = False

    context = initialize_context(
        storage_root_override=storage_root_override,
        allow_legacy_migration=allow_legacy_migration,
    )
    report_path = Path(args.report).expanduser() if args.report else None

    try:
        if args.self_test:
            report = run_self_test(
                storage_root=context.paths.storage_root,
                csv_manager=context.csv_manager,
                candidate_manager=context.candidate_manager,
                session_manager=context.session_manager,
                version_history_manager=context.version_history_manager,
                logger=context.logger,
            )
            write_report(report_path, {"status": "ok", "mode": "self_test", **report})
            return 0

        if args.startup_smoke:
            write_report(report_path, run_startup_smoke(context))
            return 0

        run_gui(context)
        return 0
    except Exception as exc:
        context.logger.exception("Application execution failed")
        try:
            context.session_manager.record_error(str(exc))
        except Exception:
            context.logger.exception("Failed to persist terminal application error")
        write_report(
            report_path,
            {
                "status": "error",
                "message": str(exc),
                "storage_root": str(context.paths.storage_root),
            },
        )
        raise
    finally:
        if temp_storage_root is not None:
            shutil.rmtree(temp_storage_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
