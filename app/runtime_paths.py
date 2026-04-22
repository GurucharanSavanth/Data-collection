from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

from utils import ensure_dir


APP_STORAGE_DIRNAME = "RecordManagerDashboard"
STORAGE_OVERRIDE_ENV = "RECORD_MANAGER_DATA_DIR"
PORTABLE_MODE_ENV = "RECORD_MANAGER_PORTABLE"

MIGRATED_FILES = (
    "data/records.csv",
    "data/candidates.json",
    "data/record_versions.json",
    "config/settings.json",
    "session/session_state.json",
    "session/app_state.json",
)

MIGRATED_DIRS = (
    "data/backups",
    "session/logs",
    "session/invalid",
    "config/invalid",
)


@dataclass(frozen=True)
class AppPaths:
    resource_root: Path
    install_root: Path
    storage_root: Path
    data_dir: Path
    backup_dir: Path
    temp_dir: Path
    session_dir: Path
    log_dir: Path
    session_invalid_dir: Path
    config_dir: Path
    config_invalid_dir: Path

    @property
    def required_directories(self) -> tuple[Path, ...]:
        return (
            self.storage_root,
            self.data_dir,
            self.backup_dir,
            self.temp_dir,
            self.session_dir,
            self.log_dir,
            self.session_invalid_dir,
            self.config_dir,
            self.config_invalid_dir,
        )


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def resolve_resource_root() -> Path:
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    return Path(__file__).resolve().parent.parent


def resolve_install_root() -> Path:
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def resolve_storage_root(storage_root_override: Path | None = None) -> Path:
    if storage_root_override is not None:
        return storage_root_override.expanduser().resolve()

    override_value = os.environ.get(STORAGE_OVERRIDE_ENV, "").strip()
    if override_value:
        return Path(override_value).expanduser().resolve()

    install_root = resolve_install_root()
    if not is_frozen():
        return install_root

    if os.environ.get(PORTABLE_MODE_ENV, "").strip() == "1":
        return install_root

    local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
    if local_app_data:
        return Path(local_app_data).expanduser().resolve() / APP_STORAGE_DIRNAME

    return Path.home() / "AppData" / "Local" / APP_STORAGE_DIRNAME


def build_app_paths(storage_root_override: Path | None = None) -> AppPaths:
    install_root = resolve_install_root()
    storage_root = resolve_storage_root(storage_root_override)
    return AppPaths(
        resource_root=resolve_resource_root(),
        install_root=install_root,
        storage_root=storage_root,
        data_dir=storage_root / "data",
        backup_dir=storage_root / "data" / "backups",
        temp_dir=storage_root / "data" / "temp",
        session_dir=storage_root / "session",
        log_dir=storage_root / "session" / "logs",
        session_invalid_dir=storage_root / "session" / "invalid",
        config_dir=storage_root / "config",
        config_invalid_dir=storage_root / "config" / "invalid",
    )


def _copy_file_if_missing(source: Path, destination: Path) -> bool:
    if not source.exists() or destination.exists():
        return False
    ensure_dir(destination.parent)
    shutil.copy2(source, destination)
    return True


def _copy_tree_if_missing(source: Path, destination: Path) -> int:
    if not source.exists() or not source.is_dir():
        return 0

    copied_count = 0
    for child in source.rglob("*"):
        if child.is_dir():
            continue
        target = destination / child.relative_to(source)
        if target.exists():
            continue
        ensure_dir(target.parent)
        shutil.copy2(child, target)
        copied_count += 1
    return copied_count


def prepare_storage(paths: AppPaths, *, allow_legacy_migration: bool) -> list[str]:
    for directory in paths.required_directories:
        ensure_dir(directory)

    migration_events: list[str] = []
    if not allow_legacy_migration or not is_frozen():
        return migration_events

    legacy_root = paths.install_root
    if legacy_root == paths.storage_root or not legacy_root.exists():
        return migration_events

    for relative_path in MIGRATED_FILES:
        source = legacy_root / relative_path
        destination = paths.storage_root / relative_path
        if _copy_file_if_missing(source, destination):
            migration_events.append(f"migrated file: {relative_path}")

    for relative_path in MIGRATED_DIRS:
        copied_count = _copy_tree_if_missing(legacy_root / relative_path, paths.storage_root / relative_path)
        if copied_count:
            migration_events.append(f"migrated {copied_count} file(s): {relative_path}")

    return migration_events
