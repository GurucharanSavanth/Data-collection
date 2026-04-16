@echo off
setlocal EnableExtensions

title CSV Record Manager Bootstrap
cd /d "%~dp0"

set "ROOT_DIR=%~dp0"
if not "%ROOT_DIR:~-1%"=="\" set "ROOT_DIR=%ROOT_DIR%\"
set "BOOTSTRAP_SELF=%~f0"
set "PYTHON_EXE="
set "PYTHON_INSTALLER=%TEMP%\csv_record_manager_python_installer.exe"
set "PYTHON_TARGET_DIR="
set "PYTHON_INSTALL_URL="

echo ==================================================
echo CSV Record Manager Bootstrap
echo ==================================================
echo Root: "%ROOT_DIR%"
echo.

call :ConfigurePythonDownload

echo [1/7] Verifying PowerShell availability...
where powershell.exe >nul 2>&1
if errorlevel 1 call :Fatal "Windows PowerShell is required for bootstrap, download, and file generation."

echo [2/7] Locating Python...
call :LocatePython
if not defined PYTHON_EXE (
    echo Python was not found on this system.
    echo Attempting a silent current-user installation...
    call :InstallPython
    if errorlevel 1 call :Fatal "Python could not be installed automatically."
    call :RefreshEnvironment
    call :LocatePython
)
if not defined PYTHON_EXE call :Fatal "Python installation completed but python.exe is still not discoverable."

echo Using Python: "%PYTHON_EXE%"
echo [3/7] Verifying Python runtime...
"%PYTHON_EXE%" --version >nul 2>&1
if errorlevel 1 call :Fatal "Python was found but could not be executed."

echo [4/7] Verifying pip...
call :VerifyPip
if errorlevel 1 call :Fatal "pip could not be verified or initialized."

echo [5/7] Ensuring folder structure exists...
call :EnsureFolders
if errorlevel 1 call :Fatal "One or more required folders could not be created."

echo [6/7] Writing managed project files from embedded BAT payload...
call :WriteManagedFiles
if errorlevel 1 call :Fatal "Embedded project files could not be generated from the BAT payload."

echo [7/7] Runtime dependency audit...
"%PYTHON_EXE%" -c "import tkinter, csv, json, logging, pathlib, uuid, tempfile, re" >nul 2>&1
if errorlevel 1 call :Fatal "Python executed, but one or more required standard-library modules could not be imported."
echo No third-party packages are required. External package installation is skipped.

if /I "%RUN_APP_NO_LAUNCH%"=="1" (
    echo Launch suppressed because RUN_APP_NO_LAUNCH=1 was provided for validation.
    endlocal & exit /b 0
)

echo.
echo Launching Tkinter application...
"%PYTHON_EXE%" "%ROOT_DIR%app\main.py"
set "APP_EXIT=%ERRORLEVEL%"

if not "%APP_EXIT%"=="0" (
    echo.
    echo The Python application exited with code %APP_EXIT%.
    echo Review "%ROOT_DIR%session\logs\application.log" for technical details.
)

endlocal & exit /b %APP_EXIT%

:ConfigurePythonDownload
set "SYSTEM_ARCH=%PROCESSOR_ARCHITECTURE%"
if defined PROCESSOR_ARCHITEW6432 set "SYSTEM_ARCH=%PROCESSOR_ARCHITEW6432%"

if /I "%SYSTEM_ARCH%"=="ARM64" (
    set "PYTHON_INSTALL_URL=https://www.python.org/ftp/python/3.13.13/python-3.13.13-arm64.exe"
    set "PYTHON_TARGET_DIR=%LocalAppData%\Programs\Python\Python313-arm64"
) else if /I "%SYSTEM_ARCH%"=="AMD64" (
    set "PYTHON_INSTALL_URL=https://www.python.org/ftp/python/3.13.13/python-3.13.13-amd64.exe"
    set "PYTHON_TARGET_DIR=%LocalAppData%\Programs\Python\Python313"
) else (
    set "PYTHON_INSTALL_URL=https://www.python.org/ftp/python/3.13.13/python-3.13.13.exe"
    set "PYTHON_TARGET_DIR=%LocalAppData%\Programs\Python\Python313-32"
)
exit /b 0

:LocatePython
set "PYTHON_EXE="

for /f "delims=" %%I in ('where python.exe 2^>nul') do (
    call :TryPythonCandidate "%%~fI"
    if defined PYTHON_EXE exit /b 0
)

for /f "usebackq delims=" %%I in (`py -3 -c "import sys; print(sys.executable)" 2^>nul`) do (
    call :TryPythonCandidate "%%~fI"
    if defined PYTHON_EXE exit /b 0
)

if defined PYTHON_TARGET_DIR (
    call :TryPythonCandidate "%PYTHON_TARGET_DIR%\python.exe"
)
if defined PYTHON_EXE exit /b 0

for %%D in (
    "%LocalAppData%\Programs\Python"
    "%ProgramFiles%"
    "%ProgramFiles(x86)%"
) do (
    if exist "%%~fD" (
        for /f "delims=" %%P in ('dir /b /ad /o-n "%%~fD\Python*" 2^>nul') do (
            call :TryPythonCandidate "%%~fD\%%P\python.exe"
            if defined PYTHON_EXE exit /b 0
        )
    )
)

exit /b 0

:TryPythonCandidate
set "PYTHON_CANDIDATE=%~f1"
if not defined PYTHON_CANDIDATE exit /b 0
if not exist "%PYTHON_CANDIDATE%" exit /b 0

"%PYTHON_CANDIDATE%" --version >nul 2>&1
if errorlevel 1 exit /b 0

set "PYTHON_EXE=%PYTHON_CANDIDATE%"
exit /b 0

:InstallPython
where winget.exe >nul 2>&1
if not errorlevel 1 (
    echo Installing Python with winget...
    winget install python --silent --force --accept-source-agreements --accept-package-agreements --disable-interactivity
    if not errorlevel 1 (
        call :RefreshEnvironment
        call :LocatePython
        if defined PYTHON_EXE exit /b 0
        echo winget reported success, but Python is still not available in the current session.
    ) else (
        echo winget installation failed. Falling back to the official Python installer...
    )
) else (
    echo winget is not available. Falling back to the official Python installer...
)

if exist "%PYTHON_INSTALLER%" del /f /q "%PYTHON_INSTALLER%" >nul 2>&1

echo Downloading official Python installer:
echo   %PYTHON_INSTALL_URL%
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command ^
    "$ProgressPreference = 'SilentlyContinue';" ^
    "try {" ^
    "  Invoke-WebRequest -UseBasicParsing -Uri $env:PYTHON_INSTALL_URL -OutFile $env:PYTHON_INSTALLER;" ^
    "  exit 0" ^
    "} catch {" ^
    "  Write-Host ('Download failed: ' + $_.Exception.Message);" ^
    "  exit 1" ^
    "}"

if errorlevel 1 exit /b 1

echo Running official Python installer silently...
start /wait "" "%PYTHON_INSTALLER%" /quiet InstallAllUsers=0 PrependPath=1 Include_pip=1 Include_tcltk=1 Include_test=0 Include_doc=0 Include_dev=0 Shortcuts=0 SimpleInstall=1 TargetDir="%PYTHON_TARGET_DIR%"
call :RefreshEnvironment
call :LocatePython
if defined PYTHON_EXE exit /b 0

echo Official installer completed, but Python is still not available in the current session.
exit /b 1

:RefreshEnvironment
if defined PYTHON_TARGET_DIR if exist "%PYTHON_TARGET_DIR%\python.exe" (
    set "PATH=%PYTHON_TARGET_DIR%;%PYTHON_TARGET_DIR%\Scripts;%PATH%"
)

for /f "usebackq delims=" %%P in (`powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "[Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [Environment]::GetEnvironmentVariable('Path','User')"`) do (
    set "PATH=%%P"
)

if defined PYTHON_TARGET_DIR if exist "%PYTHON_TARGET_DIR%\python.exe" (
    set "PATH=%PYTHON_TARGET_DIR%;%PYTHON_TARGET_DIR%\Scripts;%PATH%"
)
exit /b 0

:VerifyPip
"%PYTHON_EXE%" -m pip --version >nul 2>&1
if not errorlevel 1 exit /b 0

echo pip was not immediately available. Running ensurepip...
"%PYTHON_EXE%" -m ensurepip --upgrade >nul 2>&1
if errorlevel 1 exit /b 1

"%PYTHON_EXE%" -m pip --version >nul 2>&1
if errorlevel 1 exit /b 1

exit /b 0

:EnsureFolders
for %%D in (
    "%ROOT_DIR%app"
    "%ROOT_DIR%data"
    "%ROOT_DIR%data\backups"
    "%ROOT_DIR%data\temp"
    "%ROOT_DIR%session"
    "%ROOT_DIR%session\logs"
    "%ROOT_DIR%session\invalid"
    "%ROOT_DIR%config"
    "%ROOT_DIR%config\invalid"
) do (
    if not exist "%%~fD" mkdir "%%~fD" >nul 2>&1
    if not exist "%%~fD" exit /b 1
)
exit /b 0

:WriteManagedFiles
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command ^
    "$ErrorActionPreference = 'Stop';" ^
    "$utf8 = New-Object System.Text.UTF8Encoding($false);" ^
    "$root = $env:ROOT_DIR;" ^
    "$self = $env:BOOTSTRAP_SELF;" ^
    "$text = Get-Content -LiteralPath $self -Raw;" ^
    "$pattern = '(?ms)^::FILE\|(?<mode>[^|]+)\|(?<path>[^\r\n]+)\r?\n(?<content>.*?)^::ENDFILE\r?$';" ^
    "$matches = [regex]::Matches($text, $pattern);" ^
    "if ($matches.Count -eq 0) { Write-Error 'No embedded payload sections were found.'; exit 1 }" ^
    "foreach ($match in $matches) {" ^
    "  $mode = $match.Groups['mode'].Value.Trim().ToLowerInvariant();" ^
    "  $relativePath = $match.Groups['path'].Value.Trim();" ^
    "  $content = $match.Groups['content'].Value;" ^
    "  $target = Join-Path $root $relativePath;" ^
    "  $parent = [System.IO.Path]::GetDirectoryName($target);" ^
    "  if ($parent -and -not (Test-Path -LiteralPath $parent)) { New-Item -ItemType Directory -Path $parent -Force | Out-Null }" ^
    "  if ($mode -eq 'create' -and (Test-Path -LiteralPath $target)) { Write-Host ('[preserve] ' + $relativePath); continue }" ^
    "  [System.IO.File]::WriteAllText($target, $content, $utf8);" ^
    "  Write-Host ('[write] ' + $relativePath);" ^
    "}" ^
    "exit 0"
if errorlevel 1 exit /b 1
exit /b 0

:Fatal
echo.
echo ERROR: %~1
echo.
echo Press any key to exit.
pause >nul
exit /b 1

::FILE|overwrite|app\utils.py
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
::ENDFILE
::FILE|overwrite|app\session_manager.py
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
::ENDFILE
::FILE|overwrite|app\csv_manager.py
from __future__ import annotations

import csv
import logging
import os
import tempfile
import uuid
from pathlib import Path
from typing import Any

from utils import CSV_ENCODING, backup_file, current_timestamp, ensure_dir


LEGACY_HEADERS = (
    "record_id",
    "title",
    "category",
    "status",
    "notes",
    "created_at",
    "updated_at",
)


class CSVManager:
    def __init__(
        self,
        csv_path: Path,
        backup_dir: Path,
        temp_dir: Path,
        headers: list[str],
        logger: logging.Logger,
    ) -> None:
        self.csv_path = csv_path
        self.backup_dir = backup_dir
        self.temp_dir = temp_dir
        self.headers = headers
        self.logger = logger
        self.ensure_storage()

    def ensure_storage(self) -> None:
        ensure_dir(self.csv_path.parent)
        ensure_dir(self.backup_dir)
        ensure_dir(self.temp_dir)

        if not self.csv_path.exists() or self.csv_path.stat().st_size == 0:
            self._write_header_only()
            return

        with self.csv_path.open("r", encoding=CSV_ENCODING, newline="") as handle:
            reader = csv.reader(handle)
            header = tuple(next(reader, []))

        if list(header) == self.headers:
            return

        if header == LEGACY_HEADERS:
            self.logger.info("Migrating legacy CSV schema in %s", self.csv_path)
            self._migrate_legacy_csv()
            return

        self.logger.warning("CSV header mismatch detected in %s", self.csv_path)
        backup_file(self.csv_path, self.backup_dir, "records_header_mismatch")
        self._write_header_only()

    def _write_header_only(self) -> None:
        with self.csv_path.open("w", encoding=CSV_ENCODING, newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=self.headers)
            writer.writeheader()

    def _normalize_record(self, record: dict[str, Any], allow_generated_id: bool = False) -> dict[str, str]:
        normalized = {column: str(record.get(column, "")).strip() for column in self.headers}
        if not normalized["record_id"]:
            if allow_generated_id:
                normalized["record_id"] = self.generate_record_id()
            else:
                raise ValueError("record_id is required")
        return normalized

    def _write_records_atomically(self, normalized_records: list[dict[str, str]], backup_reason: str, create_backup: bool) -> None:
        temp_handle, temp_name = tempfile.mkstemp(
            prefix="records_",
            suffix=".csv",
            dir=str(self.temp_dir),
            text=True,
        )
        temp_path = Path(temp_name)

        try:
            with os.fdopen(temp_handle, "w", encoding=CSV_ENCODING, newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=self.headers)
                writer.writeheader()
                writer.writerows(normalized_records)

            with temp_path.open("r", encoding=CSV_ENCODING, newline="") as verify_handle:
                reader = csv.DictReader(verify_handle)
                if reader.fieldnames != self.headers:
                    raise ValueError("Temporary CSV validation failed due to header mismatch")
                for row in reader:
                    if row is None or None in row:
                        raise ValueError("Temporary CSV validation failed due to malformed row")

            if create_backup and self.csv_path.exists():
                backup_file(self.csv_path, self.backup_dir, f"records_{backup_reason}")

            os.replace(temp_path, self.csv_path)
        except Exception:
            self.logger.exception("Failed to write CSV data")
            temp_path.unlink(missing_ok=True)
            raise

    def _migrate_legacy_csv(self) -> None:
        with self.csv_path.open("r", encoding=CSV_ENCODING, newline="") as handle:
            reader = csv.DictReader(handle)
            migrated_records = []
            for row in reader:
                migrated_records.append(
                    self._normalize_record(
                        {
                            "record_id": row.get("record_id", ""),
                            "title": row.get("title", ""),
                            "category": row.get("category", ""),
                            "name": "",
                            "phone_number": "",
                            "status": row.get("status", "Open"),
                            "short_note": row.get("notes", ""),
                            "created_at": row.get("created_at", ""),
                            "updated_at": row.get("updated_at", ""),
                        },
                        allow_generated_id=True,
                    )
                )

        self._write_records_atomically(migrated_records, backup_reason="schema_upgrade", create_backup=True)

    def load_records(self) -> list[dict[str, str]]:
        self.ensure_storage()
        records: list[dict[str, str]] = []

        with self.csv_path.open("r", encoding=CSV_ENCODING, newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames != self.headers:
                self.logger.warning("CSV headers invalid during load, resetting file")
                backup_file(self.csv_path, self.backup_dir, "records_invalid_headers")
                self._write_header_only()
                return []

            for index, row in enumerate(reader, start=2):
                if row is None or None in row:
                    self.logger.warning("Skipping malformed CSV row %s", index)
                    continue
                try:
                    normalized = self._normalize_record(row)
                    records.append(normalized)
                except Exception:
                    self.logger.exception("Failed to normalize CSV row %s", index)

        records.sort(key=lambda item: item.get("updated_at", ""), reverse=True)
        return records

    def save_records(self, records: list[dict[str, Any]], backup_reason: str) -> None:
        self.ensure_storage()
        normalized_records = [self._normalize_record(record) for record in records]
        self._write_records_atomically(normalized_records, backup_reason=backup_reason, create_backup=True)

    def generate_record_id(self) -> str:
        return f"REC-{uuid.uuid4().hex[:12].upper()}"

    def build_new_record(self, form_data: dict[str, str]) -> dict[str, str]:
        timestamp = current_timestamp()
        record = {
            "record_id": self.generate_record_id(),
            "title": form_data.get("title", "").strip(),
            "category": form_data.get("category", "").strip(),
            "name": form_data.get("name", "").strip(),
            "phone_number": form_data.get("phone_number", "").strip(),
            "status": form_data.get("status", "").strip(),
            "short_note": form_data.get("short_note", "").strip(),
            "created_at": timestamp,
            "updated_at": timestamp,
        }
        return self._normalize_record(record)

    def build_updated_record(self, record_id: str, form_data: dict[str, str], existing_record: dict[str, str]) -> dict[str, str]:
        updated = dict(existing_record)
        updated["record_id"] = record_id
        updated["title"] = form_data.get("title", "").strip()
        updated["category"] = form_data.get("category", "").strip()
        updated["name"] = form_data.get("name", "").strip()
        updated["phone_number"] = form_data.get("phone_number", "").strip()
        updated["status"] = form_data.get("status", "").strip()
        updated["short_note"] = form_data.get("short_note", "").strip()
        updated["created_at"] = existing_record.get("created_at", "") or current_timestamp()
        updated["updated_at"] = current_timestamp()
        return self._normalize_record(updated)

    def find_record(self, records: list[dict[str, str]], record_id: str) -> dict[str, str] | None:
        for record in records:
            if record.get("record_id") == record_id:
                return record
        return None

    def filter_records(self, records: list[dict[str, str]], search_text: str) -> list[dict[str, str]]:
        query = search_text.strip().lower()
        if not query:
            return list(records)

        filtered: list[dict[str, str]] = []
        for record in records:
            haystack = " ".join(
                [
                    record.get("record_id", ""),
                    record.get("title", ""),
                    record.get("category", ""),
                    record.get("name", ""),
                    record.get("phone_number", ""),
                    record.get("status", ""),
                    record.get("short_note", ""),
                ]
            ).lower()
            if query in haystack:
                filtered.append(record)
        return filtered

    def get_unique_values(self, records: list[dict[str, str]], field_name: str) -> list[str]:
        values = {record.get(field_name, "").strip() for record in records if record.get(field_name, "").strip()}
        return sorted(values, key=str.lower)
::ENDFILE
::FILE|overwrite|app\gui.py
from __future__ import annotations

import logging
import os
import re
from pathlib import Path
import tkinter as tk
from tkinter import END, LEFT, RIGHT, VERTICAL, W, messagebox, ttk
from typing import Any

from csv_manager import CSVManager
from session_manager import SessionManager
from utils import current_timestamp


class RecordManagerApp:
    def __init__(
        self,
        root: tk.Tk,
        settings: dict[str, Any],
        csv_manager: CSVManager,
        session_manager: SessionManager,
        logger: logging.Logger,
        csv_path: Path,
    ) -> None:
        self.root = root
        self.settings = settings
        self.csv_manager = csv_manager
        self.session_manager = session_manager
        self.logger = logger
        self.csv_path = csv_path

        self.status_values = settings.get("status_values", ["Open", "Close"])
        self.mode = "idle"
        self.current_record_id = ""
        self.records: list[dict[str, str]] = []
        self.filtered_records: list[dict[str, str]] = []
        self.pending_state_save_job: str | None = None

        self.app_state = self.session_manager.mark_startup()
        self.session_state = self.session_manager.load_session_state()
        self.session_state["last_opened_at"] = current_timestamp()

        self.root.title(settings.get("window_title", "Record Manager Dashboard"))
        self.root.geometry(self.session_state.get("window_geometry") or settings.get("default_window_size", "1280x800"))
        if self.session_state.get("window_state") in {"normal", "zoomed"}:
            self.root.state(self.session_state["window_state"])
        self.root.minsize(1080, 680)

        saved_form = self.session_state.get("form_values", {})
        short_note_value = saved_form.get("short_note", saved_form.get("notes", ""))

        self.search_var = tk.StringVar(value=self.session_state.get("search_text", ""))
        self.title_var = tk.StringVar(value=saved_form.get("title", ""))
        self.category_var = tk.StringVar(value=saved_form.get("category", ""))
        self.name_var = tk.StringVar(value=saved_form.get("name", ""))
        self.phone_var = tk.StringVar(value=saved_form.get("phone_number", ""))
        self.status_var = tk.StringVar(value=saved_form.get("status", self.status_values[0]))
        self.mode_var = tk.StringVar(value="Mode: idle")
        self.record_id_var = tk.StringVar(value="Selected Record ID: none")
        self.status_message_var = tk.StringVar(value="Ready.")

        self._build_layout()
        self._bind_events()
        self.refresh_records(initial_restore=True)
        self.apply_session_state(short_note_value)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def _build_layout(self) -> None:
        self.root.columnconfigure(0, weight=3)
        self.root.columnconfigure(1, weight=2)
        self.root.rowconfigure(1, weight=1)

        search_frame = ttk.Frame(self.root, padding=(12, 12, 12, 6))
        search_frame.grid(row=0, column=0, columnspan=2, sticky="ew")
        search_frame.columnconfigure(1, weight=1)

        ttk.Label(search_frame, text="Search / Filter").grid(row=0, column=0, sticky=W, padx=(0, 8))
        ttk.Entry(search_frame, textvariable=self.search_var).grid(row=0, column=1, sticky="ew")
        ttk.Button(search_frame, text="Clear Search", command=self.clear_search).grid(row=0, column=2, padx=(8, 0))
        ttk.Button(search_frame, text="Reload Data", command=self.refresh_records).grid(row=0, column=3, padx=(8, 0))

        table_frame = ttk.Frame(self.root, padding=(12, 6, 6, 6))
        table_frame.grid(row=1, column=0, sticky="nsew")
        table_frame.columnconfigure(0, weight=1)
        table_frame.rowconfigure(0, weight=1)

        columns = ("record_id", "name", "phone_number", "status", "short_note")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings", selectmode="browse")
        headings = {
            "record_id": "Record ID",
            "name": "Name",
            "phone_number": "Phone Number",
            "status": "Status",
            "short_note": "Short Note / Description",
        }
        widths = {
            "record_id": 175,
            "name": 190,
            "phone_number": 150,
            "status": 100,
            "short_note": 320,
        }
        for column in columns:
            self.tree.heading(column, text=headings[column])
            self.tree.column(column, width=widths[column], anchor=W, stretch=column == "short_note")
        self.tree.grid(row=0, column=0, sticky="nsew")

        scrollbar = ttk.Scrollbar(table_frame, orient=VERTICAL, command=self.tree.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scrollbar.set)

        form_frame = ttk.Frame(self.root, padding=(6, 6, 12, 6))
        form_frame.grid(row=1, column=1, sticky="nsew")
        form_frame.columnconfigure(1, weight=1)
        form_frame.rowconfigure(7, weight=1)

        ttk.Label(form_frame, text="Record Details", style="Heading.TLabel").grid(row=0, column=0, columnspan=2, sticky=W, pady=(0, 8))
        ttk.Label(form_frame, textvariable=self.record_id_var).grid(row=1, column=0, columnspan=2, sticky=W, pady=(0, 12))

        ttk.Label(form_frame, text="Title *").grid(row=2, column=0, sticky=W, padx=(0, 8), pady=4)
        self.title_combo = ttk.Combobox(form_frame, textvariable=self.title_var, state="normal")
        self.title_combo.grid(row=2, column=1, sticky="ew", pady=4)

        ttk.Label(form_frame, text="Category *").grid(row=3, column=0, sticky=W, padx=(0, 8), pady=4)
        self.category_combo = ttk.Combobox(form_frame, textvariable=self.category_var, state="normal")
        self.category_combo.grid(row=3, column=1, sticky="ew", pady=4)

        ttk.Label(form_frame, text="Name *").grid(row=4, column=0, sticky=W, padx=(0, 8), pady=4)
        ttk.Entry(form_frame, textvariable=self.name_var).grid(row=4, column=1, sticky="ew", pady=4)

        ttk.Label(form_frame, text="Phone Number *").grid(row=5, column=0, sticky=W, padx=(0, 8), pady=4)
        ttk.Entry(form_frame, textvariable=self.phone_var).grid(row=5, column=1, sticky="ew", pady=4)

        ttk.Label(form_frame, text="Status").grid(row=6, column=0, sticky=W, padx=(0, 8), pady=4)
        self.status_combo = ttk.Combobox(form_frame, textvariable=self.status_var, values=self.status_values, state="readonly")
        self.status_combo.grid(row=6, column=1, sticky="ew", pady=4)

        ttk.Label(form_frame, text="Short Note / Description").grid(row=7, column=0, sticky="nw", padx=(0, 8), pady=4)
        self.short_note_text = tk.Text(form_frame, height=10, wrap="word")
        self.short_note_text.grid(row=7, column=1, sticky="nsew", pady=4)

        button_frame = ttk.Frame(form_frame, padding=(0, 12, 0, 0))
        button_frame.grid(row=8, column=0, columnspan=2, sticky="ew")
        for index in range(3):
            button_frame.columnconfigure(index, weight=1)

        ttk.Button(button_frame, text="Prepare New", command=self.prepare_new_record).grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ttk.Button(button_frame, text="Save Record", command=self.save_record).grid(row=0, column=1, sticky="ew", padx=6)
        ttk.Button(button_frame, text="Delete Selected", command=self.delete_selected_record).grid(row=0, column=2, sticky="ew", padx=(6, 0))
        ttk.Button(button_frame, text="Clear Form", command=self.clear_form).grid(row=1, column=0, sticky="ew", padx=(0, 6), pady=(8, 0))
        ttk.Button(button_frame, text="Reset Filter", command=self.clear_search).grid(row=1, column=1, sticky="ew", padx=6, pady=(8, 0))
        ttk.Button(button_frame, text="Open Data Folder", command=self.open_data_folder).grid(row=1, column=2, sticky="ew", padx=(6, 0), pady=(8, 0))

        footer = ttk.Frame(self.root, padding=(12, 6, 12, 12))
        footer.grid(row=2, column=0, columnspan=2, sticky="ew")
        footer.columnconfigure(0, weight=1)

        ttk.Label(footer, textvariable=self.mode_var).pack(side=LEFT)
        ttk.Label(footer, textvariable=self.status_message_var).pack(side=RIGHT)

        style = ttk.Style()
        style.configure("Heading.TLabel", font=("Segoe UI", 11, "bold"))

    def _bind_events(self) -> None:
        self.tree.bind("<<TreeviewSelect>>", self.on_tree_selection)
        self.search_var.trace_add("write", self.on_search_changed)
        self.title_var.trace_add("write", self.on_form_changed)
        self.category_var.trace_add("write", self.on_form_changed)
        self.name_var.trace_add("write", self.on_form_changed)
        self.phone_var.trace_add("write", self.on_form_changed)
        self.status_var.trace_add("write", self.on_form_changed)
        self.short_note_text.bind("<KeyRelease>", lambda _event: self.on_form_changed())

    def refresh_records(self, initial_restore: bool = False) -> None:
        try:
            self.records = self.csv_manager.load_records()
            self._refresh_reference_values()
            self.apply_filter()
            if not initial_restore:
                self.set_status(f"Loaded {len(self.records)} record(s) from CSV.")
        except Exception as exc:
            self.logger.exception("Failed to refresh records")
            self.set_status("Failed to load records. See the log file for details.", error=True)
            messagebox.showerror("Load Error", f"The application could not load the CSV file.\n\n{exc}")

    def _refresh_reference_values(self) -> None:
        self.title_combo["values"] = self.csv_manager.get_unique_values(self.records, "title")
        self.category_combo["values"] = self.csv_manager.get_unique_values(self.records, "category")

    def apply_filter(self) -> None:
        query = self.search_var.get()
        self.filtered_records = self.csv_manager.filter_records(self.records, query)
        selected_id = self.current_record_id or self.session_state.get("selected_record_id", "")
        self.populate_tree(selected_id)
        self.schedule_state_save()

    def populate_tree(self, selected_record_id: str = "") -> None:
        self.tree.delete(*self.tree.get_children())
        tree_item_to_select = ""
        for record in self.filtered_records:
            item_id = self.tree.insert(
                "",
                END,
                values=(
                    record.get("record_id", ""),
                    record.get("name", ""),
                    record.get("phone_number", ""),
                    record.get("status", ""),
                    record.get("short_note", ""),
                ),
            )
            if record.get("record_id") == selected_record_id:
                tree_item_to_select = item_id

        if tree_item_to_select:
            self.tree.selection_set(tree_item_to_select)
            self.tree.focus(tree_item_to_select)
            self.tree.see(tree_item_to_select)

    def apply_session_state(self, short_note_value: str) -> None:
        self.mode = self.session_state.get("mode", "idle")
        self.set_mode(self.mode)
        self.short_note_text.delete("1.0", END)
        self.short_note_text.insert("1.0", short_note_value)

        selected_id = self.session_state.get("selected_record_id", "")
        if selected_id:
            record = self.csv_manager.find_record(self.records, selected_id)
            if record:
                self.current_record_id = selected_id
                self.load_record_into_form(record)
                self.populate_tree(selected_id)

        if self.app_state.get("unclean_previous_shutdown"):
            self.set_status(
                "The previous session did not shut down cleanly. Restored the last saved session state.",
                error=True,
            )
            messagebox.showwarning(
                "Recovered Previous Session",
                "The previous session appears to have closed unexpectedly.\n\n"
                "The application restored the last saved search and form state.",
            )
        else:
            self.set_status(f"Ready. {len(self.records)} record(s) available.")

    def load_record_into_form(self, record: dict[str, str]) -> None:
        self.current_record_id = record.get("record_id", "")
        self.record_id_var.set(f"Selected Record ID: {self.current_record_id}")
        self.title_var.set(record.get("title", ""))
        self.category_var.set(record.get("category", ""))
        self.name_var.set(record.get("name", ""))
        self.phone_var.set(record.get("phone_number", ""))
        self.status_var.set(record.get("status", self.status_values[0]))
        self.short_note_text.delete("1.0", END)
        self.short_note_text.insert("1.0", record.get("short_note", ""))
        self.set_mode("edit")
        self.schedule_state_save()

    def collect_form_data(self) -> dict[str, str]:
        return {
            "record_id": self.current_record_id,
            "title": self.title_var.get().strip(),
            "category": self.category_var.get().strip(),
            "name": self.name_var.get().strip(),
            "phone_number": self.phone_var.get().strip(),
            "status": self.status_var.get().strip() or self.status_values[0],
            "short_note": self.short_note_text.get("1.0", END).strip(),
        }

    def validate_form_data(self, data: dict[str, str]) -> None:
        if not data["title"]:
            raise ValueError("Title is required.")
        if not data["category"]:
            raise ValueError("Category is required.")
        if not data["name"]:
            raise ValueError("Name is required.")
        if not data["phone_number"]:
            raise ValueError("Phone number is required.")
        if data["status"] not in self.status_values:
            raise ValueError("Status must be Open or Close.")

        digits_only = re.sub(r"\D", "", data["phone_number"])
        if len(digits_only) < 7 or len(digits_only) > 15:
            raise ValueError("Phone number must contain between 7 and 15 digits.")
        if not re.fullmatch(r"[0-9+\-\s()]+", data["phone_number"]):
            raise ValueError("Phone number contains unsupported characters.")

    def prepare_new_record(self) -> None:
        self.clear_form()
        self.set_mode("add")
        self.set_status("Form is ready for a new record.")

    def clear_form(self) -> None:
        self.current_record_id = ""
        self.record_id_var.set("Selected Record ID: new record (ID assigned on save)")
        self.title_var.set("")
        self.category_var.set("")
        self.name_var.set("")
        self.phone_var.set("")
        self.status_var.set(self.status_values[0])
        self.short_note_text.delete("1.0", END)
        self.tree.selection_remove(self.tree.selection())
        self.set_mode("idle")
        self.schedule_state_save()

    def clear_search(self) -> None:
        self.search_var.set("")
        self.apply_filter()

    def save_record(self) -> None:
        form_data = self.collect_form_data()
        try:
            self.validate_form_data(form_data)
            records = self.csv_manager.load_records()

            if self.current_record_id:
                existing = self.csv_manager.find_record(records, self.current_record_id)
                if not existing:
                    raise ValueError("The selected record no longer exists on disk.")
                updated_record = self.csv_manager.build_updated_record(self.current_record_id, form_data, existing)
                updated_records = [
                    updated_record if item.get("record_id") == self.current_record_id else item
                    for item in records
                ]
                action = "updated"
            else:
                new_record = self.csv_manager.build_new_record(form_data)
                self.current_record_id = new_record["record_id"]
                updated_records = records + [new_record]
                action = "created"

            self.csv_manager.save_records(updated_records, backup_reason=action)
            self.records = self.csv_manager.load_records()
            self._refresh_reference_values()
            self.filtered_records = self.csv_manager.filter_records(self.records, self.search_var.get())
            self.populate_tree(self.current_record_id)
            self.record_id_var.set(f"Selected Record ID: {self.current_record_id}")
            self.session_manager.record_successful_save(len(self.records))
            self.set_mode("edit")
            self.set_status(f"Record {self.current_record_id} {action} successfully.")
            self.schedule_state_save()
        except ValueError as exc:
            messagebox.showwarning("Validation Error", str(exc))
            self.set_status(str(exc), error=True)
        except Exception as exc:
            self.logger.exception("Failed to save record")
            self.session_manager.record_error(str(exc))
            messagebox.showerror(
                "Save Error",
                "The application could not save the record.\n\n"
                "Your original CSV file was left untouched if the save did not validate.\n\n"
                f"Technical message: {exc}",
            )
            self.set_status("Failed to save record. See the log file for details.", error=True)

    def delete_selected_record(self) -> None:
        record_id = self.current_record_id
        if not record_id:
            messagebox.showinfo("Delete Record", "Select a record before attempting to delete it.")
            return

        if not messagebox.askyesno(
            "Confirm Delete",
            f"Delete record {record_id}?\n\nA CSV backup will be created before the file is replaced.",
        ):
            return

        try:
            updated_records = [record for record in self.csv_manager.load_records() if record.get("record_id") != record_id]
            self.csv_manager.save_records(updated_records, backup_reason="delete")
            self.records = self.csv_manager.load_records()
            self._refresh_reference_values()
            self.current_record_id = ""
            self.clear_form()
            self.apply_filter()
            self.session_manager.record_successful_save(len(self.records))
            self.set_status(f"Record {record_id} deleted.")
        except Exception as exc:
            self.logger.exception("Failed to delete record")
            self.session_manager.record_error(str(exc))
            messagebox.showerror("Delete Error", f"The record could not be deleted.\n\n{exc}")
            self.set_status("Failed to delete record. See the log file for details.", error=True)

    def on_tree_selection(self, _event: tk.Event) -> None:
        selection = self.tree.selection()
        if not selection:
            return
        values = self.tree.item(selection[0], "values")
        if not values:
            return
        record_id = values[0]
        record = self.csv_manager.find_record(self.records, record_id)
        if record:
            self.load_record_into_form(record)
            self.set_status(f"Loaded record {record_id} into the form.")

    def on_search_changed(self, *_args: Any) -> None:
        self.apply_filter()

    def on_form_changed(self, *_args: Any) -> None:
        self.schedule_state_save()

    def schedule_state_save(self) -> None:
        if self.pending_state_save_job:
            self.root.after_cancel(self.pending_state_save_job)
        self.pending_state_save_job = self.root.after(500, self.persist_session_state)

    def persist_session_state(self) -> None:
        self.pending_state_save_job = None
        try:
            if self.root.state() == "zoomed":
                geometry = self.session_state.get("window_geometry", self.root.winfo_geometry())
            else:
                geometry = self.root.winfo_geometry()

            state = {
                "window_geometry": geometry,
                "window_state": self.root.state(),
                "search_text": self.search_var.get(),
                "selected_record_id": self.current_record_id,
                "mode": self.mode,
                "last_opened_at": self.session_state.get("last_opened_at", ""),
                "form_values": self.collect_form_data(),
            }
            self.session_state = state
            self.session_manager.save_session_state(state)
        except Exception:
            self.logger.exception("Failed to persist session state")

    def build_shutdown_session_state(self) -> dict[str, Any]:
        geometry = self.session_state.get("window_geometry", "")
        if self.root.state() != "zoomed":
            geometry = self.root.winfo_geometry()

        return {
            "window_geometry": geometry,
            "window_state": self.root.state(),
            "search_text": self.search_var.get(),
            "selected_record_id": self.current_record_id,
            "mode": self.mode,
            "last_opened_at": self.session_state.get("last_opened_at", ""),
            "form_values": self.collect_form_data(),
        }

    def on_close(self) -> None:
        try:
            shutdown_state = self.build_shutdown_session_state()
            self.session_manager.mark_clean_shutdown(shutdown_state)
        except Exception:
            self.logger.exception("Failed during clean shutdown")
        finally:
            self.root.destroy()

    def open_data_folder(self) -> None:
        try:
            self.csv_path.parent.mkdir(parents=True, exist_ok=True)
            os.startfile(str(self.csv_path.parent))
        except Exception as exc:
            self.logger.exception("Failed to open data folder")
            messagebox.showerror("Open Folder Error", f"Could not open the data folder.\n\n{exc}")

    def set_mode(self, mode: str) -> None:
        self.mode = mode
        self.mode_var.set(f"Mode: {mode}")
        self.schedule_state_save()

    def set_status(self, message: str, error: bool = False) -> None:
        prefix = "Status: "
        self.status_message_var.set(f"{prefix}{message}")
::ENDFILE
::FILE|overwrite|app\main.py
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
::ENDFILE
::FILE|create|data\records.csv
record_id,title,category,name,phone_number,status,short_note,created_at,updated_at
::ENDFILE
::FILE|create|session\session_state.json
{
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
    "short_note": ""
  }
}
::ENDFILE
::FILE|create|session\app_state.json
{
  "app_version": "1.1.0",
  "first_run_completed": false,
  "clean_shutdown": true,
  "unclean_previous_shutdown": false,
  "last_startup_at": "",
  "last_shutdown_at": "",
  "last_successful_save": "",
  "record_count": 0,
  "last_error": ""
}
::ENDFILE
::FILE|create|config\settings.json
{
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
    "updated_at"
  ],
  "status_values": [
    "Open",
    "Close"
  ]
}
::ENDFILE
::FILE|overwrite|README.md
# Record Manager Dashboard

This project is designed to be bootstrapped and launched from a single Windows batch file, `run_app.bat`.

## What it does

- Installs Python silently for the current Windows user when Python is missing.
- Verifies `python` and `pip`.
- Recreates the managed application files from the BAT payload.
- Preserves user-owned files such as CSV data and session JSON files.
- Launches a Tkinter desktop application for managing contact-style records stored in `data/records.csv`.

## Storage layout

- `data/records.csv`: Primary editable record store.
- `data/backups/`: Backup copies created before CSV replacement.
- `data/temp/`: Temporary files used during atomic CSV writes.
- `session/session_state.json`: Restored UI/session state.
- `session/app_state.json`: Operational state, clean-shutdown marker, and last-save metadata.
- `session/logs/application.log`: Technical error log.

## Record fields

- `record_id`
- `title`
- `category`
- `name`
- `phone_number`
- `status`
- `short_note`
- `created_at`
- `updated_at`

## UI behavior

- The dashboard table shows `Record ID`, `Name`, `Phone Number`, `Status`, and `Short Note / Description`.
- `Title` and `Category` use editable dropdowns: existing values are offered automatically, but new values can still be typed.
- The right-side form supports `Title`, `Category`, `Name`, `Phone Number`, `Status`, and `Short Note / Description`.

## Rerun safety

Running `run_app.bat` repeatedly does not delete existing CSV or session files. Managed code files are refreshed from the BAT payload; user data files are only created when missing.
::ENDFILE
