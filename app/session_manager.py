from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from utils import current_timestamp, deep_merge, safe_json_load, safe_json_write


SESSION_DEFAULTS: dict[str, Any] = {
    "window_geometry": "",
    "window_state": "normal",
    "search_text": "",
    "selected_record_id": "",
    "mode": "idle",
    "last_opened_at": "",
    "form_values": {
        "record_id": "",
        "title": "",
        "category": "",
        "name": "",
        "phone_number": "",
        "status": "Open",
        "short_note": "",
    },
}


APP_STATE_DEFAULTS: dict[str, Any] = {
    "app_version": "1.1.0",
    "first_run_completed": False,
    "clean_shutdown": True,
    "unclean_previous_shutdown": False,
    "last_startup_at": "",
    "last_shutdown_at": "",
    "last_successful_save": "",
    "record_count": 0,
    "last_error": "",
}


class SessionManager:
    def __init__(self, session_path: Path, app_state_path: Path, logger: logging.Logger) -> None:
        self.session_path = session_path
        self.app_state_path = app_state_path
        self.logger = logger
        self.session_default = SESSION_DEFAULTS
        self.app_state_default = APP_STATE_DEFAULTS

    def load_session_state(self) -> dict[str, Any]:
        return safe_json_load(
            self.session_path,
            self.session_default,
            logger=self.logger,
            invalid_backup_dir=self.session_path.parent / "invalid",
        )

    def load_app_state(self) -> dict[str, Any]:
        return safe_json_load(
            self.app_state_path,
            self.app_state_default,
            logger=self.logger,
            invalid_backup_dir=self.app_state_path.parent / "invalid",
        )

    def save_session_state(self, session_state: dict[str, Any]) -> None:
        payload = deep_merge(self.session_default, session_state)
        safe_json_write(self.session_path, payload)

    def save_app_state(self, app_state: dict[str, Any]) -> None:
        payload = deep_merge(self.app_state_default, app_state)
        safe_json_write(self.app_state_path, payload)

    def mark_startup(self) -> dict[str, Any]:
        app_state = self.load_app_state()
        app_state["unclean_previous_shutdown"] = not bool(app_state.get("clean_shutdown", True))
        app_state["clean_shutdown"] = False
        app_state["last_startup_at"] = current_timestamp()
        self.save_app_state(app_state)
        return app_state

    def mark_clean_shutdown(self, last_session_state: dict[str, Any]) -> None:
        self.save_session_state(last_session_state)
        app_state = self.load_app_state()
        app_state["clean_shutdown"] = True
        app_state["unclean_previous_shutdown"] = False
        app_state["last_shutdown_at"] = current_timestamp()
        app_state["first_run_completed"] = True
        self.save_app_state(app_state)

    def record_successful_save(self, record_count: int) -> None:
        app_state = self.load_app_state()
        app_state["last_successful_save"] = current_timestamp()
        app_state["record_count"] = record_count
        app_state["first_run_completed"] = True
        self.save_app_state(app_state)

    def record_error(self, message: str) -> None:
        try:
            app_state = self.load_app_state()
            app_state["last_error"] = message
            self.save_app_state(app_state)
        except Exception:
            self.logger.exception("Failed to persist application error state")
