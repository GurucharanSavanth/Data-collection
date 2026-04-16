from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
import traceback
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any


APP_ENCODING = "utf-8"
CSV_ENCODING = "utf-8-sig"


def current_timestamp() -> str:
    return datetime.now().replace(microsecond=0).isoformat(sep=" ")


def current_timestamp_for_filename() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def deep_merge(defaults: dict[str, Any], incoming: dict[str, Any] | None) -> dict[str, Any]:
    result = deepcopy(defaults)
    if not isinstance(incoming, dict):
        return result

    for key, value in incoming.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def ensure_parent(path: Path) -> None:
    ensure_dir(path.parent)


def backup_file(source: Path, backup_dir: Path, prefix: str) -> Path | None:
    if not source.exists():
        return None

    ensure_dir(backup_dir)
    backup_name = f"{prefix}_{current_timestamp_for_filename()}{source.suffix}"
    backup_path = backup_dir / backup_name
    shutil.copy2(source, backup_path)
    return backup_path


def safe_json_load(
    path: Path,
    default: dict[str, Any],
    logger: logging.Logger | None = None,
    invalid_backup_dir: Path | None = None,
) -> dict[str, Any]:
    if not path.exists():
        return deepcopy(default)

    try:
        with path.open("r", encoding=APP_ENCODING) as handle:
            payload = json.load(handle)
        return deep_merge(default, payload if isinstance(payload, dict) else {})
    except Exception:
        if logger:
            logger.exception("Failed to load JSON from %s", path)
        if invalid_backup_dir is not None:
            try:
                backup_file(path, invalid_backup_dir, f"{path.stem}_invalid")
            except Exception:
                if logger:
                    logger.exception("Failed to back up malformed JSON file %s", path)
        return deepcopy(default)


def safe_json_write(path: Path, payload: dict[str, Any]) -> None:
    ensure_parent(path)
    temp_handle, temp_name = tempfile.mkstemp(
        prefix=f"{path.stem}_",
        suffix=".tmp",
        dir=str(path.parent),
        text=True,
    )
    temp_path = Path(temp_name)

    try:
        with os.fdopen(temp_handle, "w", encoding=APP_ENCODING) as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
            handle.write("\n")

        with temp_path.open("r", encoding=APP_ENCODING) as verify_handle:
            json.load(verify_handle)

        os.replace(temp_path, path)
    except Exception:
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)
        raise


def format_exception() -> str:
    return traceback.format_exc()
