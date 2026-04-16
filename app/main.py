from __future__ import annotations

import logging
import sys
from pathlib import Path
import tkinter as tk
from tkinter import messagebox

from csv_manager import CSVManager
from gui import RecordManagerApp
from session_manager import SessionManager
from utils import APP_ENCODING, ensure_dir, format_exception, safe_json_load, safe_json_write


DEFAULT_SETTINGS = {
    "app_name": "Record Manager Dashboard",
    "app_version": "1.1.0",
    "window_title": "Record Manager Dashboard",
    "default_window_size": "1280x800",
    "csv_headers": [
        "record_id",
        "title",
        "category",
        "name",
        "phone_number",
        "status",
        "short_note",
        "created_at",
        "updated_at",
    ],
    "status_values": ["Open", "Close"],
}


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
    normalized["csv_headers"] = list(DEFAULT_SETTINGS["csv_headers"])
    normalized["status_values"] = list(DEFAULT_SETTINGS["status_values"])

    if loaded_settings != normalized:
        logger.info("Normalizing settings to application schema version %s", DEFAULT_SETTINGS["app_version"])
        safe_json_write(settings_path, normalized)

    return normalized


def resolve_project_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def main() -> None:
    project_root = resolve_project_root()
    data_dir = ensure_dir(project_root / "data")
    backup_dir = ensure_dir(data_dir / "backups")
    temp_dir = ensure_dir(data_dir / "temp")
    session_dir = ensure_dir(project_root / "session")
    log_dir = ensure_dir(session_dir / "logs")
    ensure_dir(session_dir / "invalid")
    config_dir = ensure_dir(project_root / "config")

    logger = configure_logging(log_dir)
    settings_path = config_dir / "settings.json"
    settings = safe_json_load(settings_path, DEFAULT_SETTINGS, logger=logger, invalid_backup_dir=config_dir / "invalid")
    settings = normalize_settings(settings_path, settings, logger)

    session_manager = SessionManager(
        session_path=session_dir / "session_state.json",
        app_state_path=session_dir / "app_state.json",
        logger=logger,
    )
    csv_manager = CSVManager(
        csv_path=data_dir / "records.csv",
        backup_dir=backup_dir,
        temp_dir=temp_dir,
        headers=settings["csv_headers"],
        logger=logger,
    )

    def global_exception_handler(exc_type, exc_value, exc_traceback) -> None:
        logger.error("Unhandled exception", exc_info=(exc_type, exc_value, exc_traceback))
        session_manager.record_error(str(exc_value))
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(
            "Unexpected Error",
            "An unexpected error occurred.\n\n"
            "The technical details were written to session/logs/application.log.\n\n"
            f"{exc_value}",
        )
        root.destroy()

    sys.excepthook = global_exception_handler

    logger.info("Starting application from %s", project_root)
    root = tk.Tk()
    RecordManagerApp(
        root=root,
        settings=settings,
        csv_manager=csv_manager,
        session_manager=session_manager,
        logger=logger,
        csv_path=data_dir / "records.csv",
    )

    try:
        root.mainloop()
    except Exception:
        logger.error("Fatal UI error\n%s", format_exception())
        session_manager.record_error("Fatal UI error")
        raise


if __name__ == "__main__":
    main()
