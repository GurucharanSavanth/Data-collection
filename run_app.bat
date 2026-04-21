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
    "selected_candidate": "None",
    "selected_candidate_id": "",
    "view_mode": "Active",
    "selected_record_id": "",
    "mode": "idle",
    "last_opened_at": "",
    "form_values": {
        "record_id": "",
        "title": "",
        "application_number": "",
        "candidate_id": "",
        "name": "",
        "phone_number": "",
        "status": "Open",
        "short_note": "",
    },
}


APP_STATE_DEFAULTS: dict[str, Any] = {
    "app_version": "2.0.0",
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
import re
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

PRE_CANDIDATE_HEADERS = (
    "record_id",
    "title",
    "application_number",
    "referral_number",
    "name",
    "phone_number",
    "status",
    "short_note",
    "archived_at",
    "created_at",
    "updated_at",
)

TRANSITION_HEADERS = (
    "record_id",
    "title",
    "category",
    "name",
    "phone_number",
    "status",
    "short_note",
    "created_at",
    "updated_at",
)

EXPORT_HEADERS = (
    "record_id",
    "title",
    "application_number",
    "referral_number",
    "candidate_id",
    "name",
    "phone_number",
    "status",
    "short_note",
    "created_at",
    "updated_at",
)

CSV_INJECTION_TRIGGERS = ("=", "+", "-", "@", "\t", "\r")


def _sanitize_export_cell(value: Any) -> str:
    text = "" if value is None else str(value)
    if text and text[0] in CSV_INJECTION_TRIGGERS:
        return "'" + text
    return text


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

        if header == PRE_CANDIDATE_HEADERS:
            self.logger.info("Migrating pre-candidate CSV schema in %s", self.csv_path)
            self._migrate_pre_candidate_csv()
            return

        if header == TRANSITION_HEADERS:
            self.logger.info("Migrating transition CSV schema in %s", self.csv_path)
            self._migrate_transition_csv()
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
        if not normalized.get("referral_number"):
            normalized["referral_number"] = self.generate_referral_number(normalized["record_id"])
        normalized["name"] = " ".join(normalized.get("name", "").split())
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

    def _migrate_pre_candidate_csv(self) -> None:
        with self.csv_path.open("r", encoding=CSV_ENCODING, newline="") as handle:
            reader = csv.DictReader(handle)
            migrated_records = []
            for row in reader:
                migrated_records.append(
                    self._normalize_record(
                        {
                            "record_id": row.get("record_id", ""),
                            "title": row.get("title", ""),
                            "application_number": row.get("application_number", ""),
                            "referral_number": row.get("referral_number", ""),
                            "candidate_id": "",
                            "name": row.get("name", ""),
                            "phone_number": row.get("phone_number", ""),
                            "status": row.get("status", "Open"),
                            "short_note": row.get("short_note", ""),
                            "archived_at": row.get("archived_at", ""),
                            "created_at": row.get("created_at", ""),
                            "updated_at": row.get("updated_at", ""),
                        },
                        allow_generated_id=True,
                    )
                )

        self._write_records_atomically(migrated_records, backup_reason="schema_upgrade", create_backup=True)

    def _migrate_transition_csv(self) -> None:
        with self.csv_path.open("r", encoding=CSV_ENCODING, newline="") as handle:
            reader = csv.DictReader(handle)
            migrated_records = []
            for row in reader:
                migrated_records.append(
                    self._normalize_record(
                        {
                            "record_id": row.get("record_id", ""),
                            "title": row.get("title", ""),
                            "application_number": row.get("category", ""),
                            "referral_number": self.generate_referral_number(row.get("record_id", "")),
                            "candidate_id": "",
                            "name": row.get("name", ""),
                            "phone_number": row.get("phone_number", ""),
                            "status": row.get("status", "Open"),
                            "short_note": row.get("short_note", ""),
                            "archived_at": "",
                            "created_at": row.get("created_at", ""),
                            "updated_at": row.get("updated_at", ""),
                        },
                        allow_generated_id=True,
                    )
                )

        self._write_records_atomically(migrated_records, backup_reason="schema_upgrade", create_backup=True)

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
                            "application_number": row.get("category", ""),
                            "referral_number": self.generate_referral_number(row.get("record_id", "")),
                            "candidate_id": "",
                            "name": "",
                            "phone_number": "",
                            "status": row.get("status", "Open"),
                            "short_note": row.get("notes", ""),
                            "archived_at": "",
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
                    records.append(self._normalize_record(row))
                except Exception:
                    self.logger.exception("Failed to normalize CSV row %s", index)

        records.sort(key=lambda item: item.get("updated_at", ""), reverse=True)
        return records

    def save_records(self, records: list[dict[str, Any]], backup_reason: str) -> None:
        self.ensure_storage()
        normalized_records = [self._normalize_record(record) for record in records]
        self._write_records_atomically(normalized_records, backup_reason=backup_reason, create_backup=True)

    def export_records(self, records: list[dict[str, str]], destination: Path) -> None:
        ensure_dir(destination.parent)
        temp_handle, temp_name = tempfile.mkstemp(
            prefix="export_",
            suffix=".csv",
            dir=str(destination.parent),
            text=True,
        )
        temp_path = Path(temp_name)
        try:
            with os.fdopen(temp_handle, "w", encoding=CSV_ENCODING, newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=EXPORT_HEADERS)
                writer.writeheader()
                for record in records:
                    writer.writerow(
                        {column: _sanitize_export_cell(record.get(column, "")) for column in EXPORT_HEADERS}
                    )
            os.replace(temp_path, destination)
        except Exception:
            self.logger.exception("Failed to export CSV")
            temp_path.unlink(missing_ok=True)
            raise

    def generate_record_id(self) -> str:
        return f"REC-{uuid.uuid4().hex[:12].upper()}"

    def generate_referral_number(self, record_id: str) -> str:
        clean_record_id = re.sub(r"[^A-Z0-9]", "", record_id.upper())
        token = clean_record_id[-8:] if clean_record_id else uuid.uuid4().hex[:8].upper()
        return f"REF-{token}"

    def build_new_record(self, form_data: dict[str, str]) -> dict[str, str]:
        timestamp = current_timestamp()
        record_id = self.generate_record_id()
        record = {
            "record_id": record_id,
            "title": form_data.get("title", "").strip(),
            "application_number": form_data.get("application_number", "").strip(),
            "referral_number": self.generate_referral_number(record_id),
            "candidate_id": form_data.get("candidate_id", "").strip(),
            "name": form_data.get("name", "").strip(),
            "phone_number": form_data.get("phone_number", "").strip(),
            "status": form_data.get("status", "").strip(),
            "short_note": form_data.get("short_note", "").strip(),
            "archived_at": "",
            "created_at": timestamp,
            "updated_at": timestamp,
        }
        return self._normalize_record(record)

    def build_updated_record(self, record_id: str, form_data: dict[str, str], existing_record: dict[str, str]) -> dict[str, str]:
        updated = dict(existing_record)
        updated["record_id"] = record_id
        updated["title"] = form_data.get("title", "").strip()
        updated["application_number"] = form_data.get("application_number", "").strip()
        updated["candidate_id"] = form_data.get("candidate_id", "").strip()
        updated["name"] = form_data.get("name", "").strip()
        updated["phone_number"] = form_data.get("phone_number", "").strip()
        updated["status"] = form_data.get("status", "").strip()
        updated["short_note"] = form_data.get("short_note", "").strip()
        updated["created_at"] = existing_record.get("created_at", "") or current_timestamp()
        updated["updated_at"] = current_timestamp()
        return self._normalize_record(updated)

    def build_archived_record(self, existing_record: dict[str, str], archived_at: str | None = None) -> dict[str, str]:
        archived = dict(existing_record)
        timestamp = archived_at or current_timestamp()
        archived["archived_at"] = timestamp
        archived["updated_at"] = timestamp
        return self._normalize_record(archived)

    def build_unarchived_record(self, existing_record: dict[str, str]) -> dict[str, str]:
        restored = dict(existing_record)
        restored["archived_at"] = ""
        restored["updated_at"] = current_timestamp()
        return self._normalize_record(restored)

    def build_restored_record(self, record_id: str, snapshot: dict[str, str]) -> dict[str, str]:
        restored = dict(snapshot)
        restored["record_id"] = record_id
        restored["archived_at"] = snapshot.get("archived_at", "")
        restored["created_at"] = snapshot.get("created_at", "") or current_timestamp()
        restored["updated_at"] = current_timestamp()
        return self._normalize_record(restored)

    def find_record(self, records: list[dict[str, str]], record_id: str) -> dict[str, str] | None:
        target_id = str(record_id).strip()
        for record in records:
            if record.get("record_id", "") == target_id:
                return record
        return None

    def filter_records(self, records: list[dict[str, str]], candidate_id: str, view_mode: str = "Active") -> list[dict[str, str]]:
        normalized_candidate_id = str(candidate_id).strip()
        if not normalized_candidate_id:
            return []

        normalized_view_mode = str(view_mode).strip().lower() or "active"
        filtered: list[dict[str, str]] = []
        for record in records:
            if record.get("candidate_id", "").strip() != normalized_candidate_id:
                continue
            is_archived = bool(record.get("archived_at", "").strip())
            if normalized_view_mode == "archived" and not is_archived:
                continue
            if normalized_view_mode == "active" and is_archived:
                continue
            filtered.append(record)
        filtered.sort(key=lambda item: item.get("updated_at", ""), reverse=True)
        return filtered

    def get_archived_records(self, records: list[dict[str, str]], candidate_id: str = "") -> list[dict[str, str]]:
        normalized_candidate_id = str(candidate_id).strip()
        archived_records = [
            record
            for record in records
            if record.get("archived_at", "").strip()
            and (not normalized_candidate_id or record.get("candidate_id", "").strip() == normalized_candidate_id)
        ]
        archived_records.sort(key=lambda item: item.get("archived_at", ""), reverse=True)
        return archived_records
::ENDFILE
::FILE|overwrite|app\gui.py
from __future__ import annotations

import logging
import re
from pathlib import Path
import tkinter as tk
from tkinter import END, VERTICAL, filedialog, messagebox, simpledialog, ttk
from typing import Any

from candidate_manager import CandidateManager
from csv_manager import CSVManager
from session_manager import SessionManager
from version_history_manager import VersionHistoryManager


class RecordManagerApp:
    def __init__(
        self,
        root: tk.Tk,
        settings: dict[str, Any],
        csv_manager: CSVManager,
        candidate_manager: CandidateManager,
        session_manager: SessionManager,
        version_history_manager: VersionHistoryManager,
        logger: logging.Logger,
        csv_path: Path,
    ) -> None:
        self.root = root
        self.settings = settings
        self.csv_manager = csv_manager
        self.candidate_manager = candidate_manager
        self.session_manager = session_manager
        self.version_history_manager = version_history_manager
        self.logger = logger
        self.csv_path = csv_path

        self.status_values = list(settings.get("status_values", ["Open", "Clone", "In Progress", "Forfeited"]))
        self.mode = "idle"
        self.current_record_id = ""
        self.selected_candidate_id = ""
        self.records: list[dict[str, str]] = []
        self.filtered_records: list[dict[str, str]] = []
        self.candidates: list[dict[str, str]] = []
        self.candidate_id_by_label: dict[str, str] = {}
        self.candidate_label_by_id: dict[str, str] = {}
        self.pending_state_save_job: str | None = None
        self.candidate_updates_suspended = False
        self.view_mode_updates_suspended = False
        self.sash_positioned = False
        self._form_loading = False
        self._form_dirty = False
        self._save_in_progress = False
        self._previous_candidate_label = "None"

        self.app_state = self.session_manager.mark_startup()
        self.session_state = self.session_manager.load_session_state()
        self.session_state["last_opened_at"] = self.session_state.get("last_opened_at", "")

        saved_form = self.session_state.get("form_values", {})

        self.candidate_var = tk.StringVar(value=self.session_state.get("selected_candidate", "None"))
        self.view_mode_var = tk.StringVar(value=self.session_state.get("view_mode", "Active"))
        self.title_var = tk.StringVar(value=saved_form.get("title", ""))
        self.application_number_var = tk.StringVar(value=saved_form.get("application_number", ""))
        self.name_var = tk.StringVar(value=saved_form.get("name", ""))
        self.phone_var = tk.StringVar(value=saved_form.get("phone_number", ""))
        self.status_var = tk.StringVar(value=saved_form.get("status", self.status_values[0]))
        self.created_at_var = tk.StringVar(value="-")
        self.updated_at_var = tk.StringVar(value="-")
        self.footer_status_var = tk.StringVar(value="Logged out.")
        self.version_label_var = tk.StringVar(value=f"Version {settings.get('app_version', '2.0.0')}")

        self.root.title(settings.get("window_title", "Record Manager Dashboard"))
        self.root.geometry(self.session_state.get("window_geometry") or settings.get("default_window_size", "1280x800"))
        if self.session_state.get("window_state") in {"normal", "zoomed"}:
            self.root.state(self.session_state["window_state"])
        self.root.minsize(1180, 700)

        self._build_layout()
        self._bind_events()
        self.reload_data(initial_restore=True)
        self.apply_session_state()
        self.root.after_idle(self._position_body_sash)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def _build_layout(self) -> None:
        self.default_bg = self.root.cget("bg")

        style = ttk.Style(self.root)
        for theme_name in ("winnative", "vista", "xpnative", "default"):
            if theme_name in style.theme_names():
                style.theme_use(theme_name)
                break
        style.configure("RecordTree.Treeview", rowheight=22, font=("Segoe UI", 8))
        style.configure("RecordTree.Treeview.Heading", font=("Segoe UI", 8))
        style.configure("Archived.RecordTree.Treeview", rowheight=22, font=("Segoe UI", 8), foreground="#5A5A5A")
        style.configure("VersionTree.Treeview", rowheight=22, font=("Segoe UI", 8))
        style.configure("VersionTree.Treeview.Heading", font=("Segoe UI", 8))
        style.map("RecordTree.Treeview", background=[("selected", "#0A64AD")], foreground=[("selected", "#FFFFFF")])
        style.map("VersionTree.Treeview", background=[("selected", "#0A64AD")], foreground=[("selected", "#FFFFFF")])

        self.root.rowconfigure(1, weight=1)
        self.root.columnconfigure(0, weight=1)

        header_frame = tk.Frame(self.root, bg=self.default_bg, padx=8, pady=6)
        header_frame.grid(row=0, column=0, sticky="ew")
        header_frame.columnconfigure(1, weight=1)

        tk.Label(
            header_frame,
            text="Candidate Name",
            bg=self.default_bg,
            font=("Segoe UI", 10, "bold"),
        ).grid(row=0, column=0, sticky="w")
        tk.Label(
            header_frame,
            text="Candidate context: select a candidate",
            bg=self.default_bg,
            font=("Segoe UI", 8),
        ).grid(row=0, column=1, sticky="w", padx=(6, 0))

        tk.Label(header_frame, text="Candidate", bg=self.default_bg, font=("Segoe UI", 8)).grid(
            row=1,
            column=0,
            sticky="w",
            pady=(6, 0),
        )
        self.candidate_combo = ttk.Combobox(header_frame, textvariable=self.candidate_var, state="readonly")
        self.candidate_combo.grid(row=1, column=1, sticky="ew", pady=(6, 0))

        self.candidate_menu = tk.Menu(self.root, tearoff=0)
        self.candidate_menu.add_command(label="New Candidate...", command=self.create_candidate_from_dialog)
        self.candidate_menu.add_command(label="Edit Selected Candidate...", command=self.edit_selected_candidate)
        self.candidate_menu.add_command(label="Remove Selected Candidate", command=self.archive_selected_candidate)
        self.candidate_menu.add_command(label="Unarchive Candidate...", command=self.open_unarchive_candidate_dialog)

        candidate_button_frame = tk.Frame(header_frame, bg=self.default_bg)
        candidate_button_frame.grid(row=1, column=2, sticky="e", padx=(8, 0), pady=(6, 0))

        self.add_candidate_button = tk.Button(
            candidate_button_frame,
            text="Add",
            width=7,
            command=self.create_candidate_from_dialog,
        )
        self.add_candidate_button.grid(row=0, column=0, padx=(0, 4))

        self.edit_candidate_button = tk.Button(
            candidate_button_frame,
            text="Edit",
            width=7,
            command=self.edit_selected_candidate,
        )
        self.edit_candidate_button.grid(row=0, column=1, padx=(0, 4))

        self.remove_candidate_button = tk.Button(
            candidate_button_frame,
            text="Remove",
            width=8,
            command=self.archive_selected_candidate,
        )
        self.remove_candidate_button.grid(row=0, column=2)

        self.restore_candidate_button = tk.Button(
            candidate_button_frame,
            text="Unarchive",
            width=9,
            command=self.open_unarchive_candidate_dialog,
        )
        self.restore_candidate_button.grid(row=0, column=3, padx=(4, 0))

        tk.Label(header_frame, text="View", bg=self.default_bg, font=("Segoe UI", 8)).grid(
            row=2,
            column=0,
            sticky="w",
            pady=(6, 0),
        )
        self.view_mode_combo = ttk.Combobox(
            header_frame,
            textvariable=self.view_mode_var,
            values=("Active", "Archived", "All"),
            state="readonly",
            width=14,
        )
        self.view_mode_combo.grid(row=2, column=1, sticky="w", pady=(6, 0))

        self.body_pane = tk.PanedWindow(
            self.root,
            orient=tk.HORIZONTAL,
            sashrelief=tk.RAISED,
            sashwidth=5,
            bd=0,
            bg=self.default_bg,
        )
        self.body_pane.grid(row=1, column=0, sticky="nsew", padx=8, pady=(2, 0))

        left_frame = tk.Frame(self.body_pane, bg=self.default_bg, bd=1, relief=tk.SUNKEN)
        left_frame.rowconfigure(0, weight=1)
        left_frame.columnconfigure(0, weight=1)

        table_columns = (
            "record_id",
            "application_number",
            "referral_number",
            "name",
            "status",
            "created_at",
            "updated_at",
        )
        self.tree = ttk.Treeview(
            left_frame,
            columns=table_columns,
            show="headings",
            selectmode="browse",
            style="RecordTree.Treeview",
        )
        headings = {
            "record_id": "Record ID",
            "application_number": "Application Number",
            "referral_number": "Referral Number",
            "name": "Name",
            "status": "Status",
            "created_at": "Created At",
            "updated_at": "Updated At",
        }
        widths = {
            "record_id": 122,
            "application_number": 156,
            "referral_number": 122,
            "name": 150,
            "status": 92,
            "created_at": 118,
            "updated_at": 118,
        }
        for column in table_columns:
            self.tree.heading(column, text=headings[column])
            self.tree.column(column, width=widths[column], anchor="w", stretch=False)
        self.tree.grid(row=0, column=0, sticky="nsew")
        self.tree.tag_configure("archived", foreground="#5A5A5A")

        table_scrollbar = tk.Scrollbar(left_frame, orient=VERTICAL, command=self.tree.yview)
        table_scrollbar.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=table_scrollbar.set)

        right_frame = tk.Frame(self.body_pane, bg=self.default_bg, padx=12, pady=6)
        right_frame.columnconfigure(0, weight=1)
        right_frame.rowconfigure(4, weight=1)

        tk.Label(
            right_frame,
            text="Record Details",
            bg=self.default_bg,
            font=("Segoe UI", 10, "bold"),
        ).grid(row=0, column=0, sticky="w", pady=(0, 8))

        details_frame = tk.Frame(right_frame, bg=self.default_bg)
        details_frame.grid(row=1, column=0, sticky="nsew")
        details_frame.columnconfigure(1, weight=1)
        details_frame.rowconfigure(7, weight=1)

        label_width = 18
        entry_width = 28

        self._make_form_label(details_frame, "Title", 0, width=label_width)
        tk.Entry(details_frame, textvariable=self.title_var, width=entry_width, relief=tk.SUNKEN, bd=1).grid(
            row=0,
            column=1,
            sticky="ew",
            pady=2,
        )

        self._make_form_label(details_frame, "Application Number", 1, width=label_width)
        tk.Entry(
            details_frame,
            textvariable=self.application_number_var,
            width=entry_width,
            relief=tk.SUNKEN,
            bd=1,
        ).grid(row=1, column=1, sticky="ew", pady=2)

        self._make_form_label(details_frame, "Name", 2, width=label_width)
        tk.Entry(details_frame, textvariable=self.name_var, width=entry_width, relief=tk.SUNKEN, bd=1).grid(
            row=2,
            column=1,
            sticky="ew",
            pady=2,
        )

        self._make_form_label(details_frame, "Phone Number", 3, width=label_width)
        tk.Entry(details_frame, textvariable=self.phone_var, width=entry_width, relief=tk.SUNKEN, bd=1).grid(
            row=3,
            column=1,
            sticky="ew",
            pady=2,
        )

        self._make_form_label(details_frame, "Status", 4, width=label_width)
        self.status_combo = ttk.Combobox(
            details_frame,
            textvariable=self.status_var,
            values=self.status_values,
            state="readonly",
        )
        self.status_combo.grid(row=4, column=1, sticky="ew", pady=2)

        self._make_form_label(details_frame, "Created At", 5, width=label_width)
        tk.Label(details_frame, textvariable=self.created_at_var, bg=self.default_bg, anchor="w").grid(
            row=5,
            column=1,
            sticky="w",
            pady=2,
        )

        self._make_form_label(details_frame, "Updated At", 6, width=label_width)
        tk.Label(details_frame, textvariable=self.updated_at_var, bg=self.default_bg, anchor="w").grid(
            row=6,
            column=1,
            sticky="w",
            pady=2,
        )

        self._make_form_label(details_frame, "Short Notes / Description", 7, width=label_width, sticky="nw")
        self.short_note_text = tk.Text(details_frame, height=11, wrap="word", relief=tk.SUNKEN, bd=1)
        self.short_note_text.grid(row=7, column=1, sticky="nsew", pady=(2, 6))

        button_frame = tk.Frame(right_frame, bg=self.default_bg)
        button_frame.grid(row=2, column=0, sticky="ew", pady=(6, 10))
        for column_index in range(5):
            button_frame.columnconfigure(column_index, weight=1)

        tk.Button(button_frame, text="New Record Report", command=self.prepare_new_record).grid(
            row=0,
            column=0,
            sticky="ew",
            padx=(0, 6),
        )
        self.save_record_button = tk.Button(button_frame, text="Save Record", command=self.save_record)
        self.save_record_button.grid(
            row=0,
            column=1,
            sticky="ew",
            padx=6,
        )
        self.archive_record_button = tk.Button(button_frame, text="Archive Record", command=self.archive_selected_record_entry)
        self.archive_record_button.grid(
            row=0,
            column=2,
            sticky="ew",
            padx=6,
        )
        self.restore_record_button = tk.Button(
            button_frame,
            text="Unarchive Record...",
            command=self.open_unarchive_record_dialog,
        )
        self.restore_record_button.grid(
            row=0,
            column=3,
            sticky="ew",
            padx=6,
        )
        tk.Button(button_frame, text="Export CSV", command=self.export_current_records).grid(
            row=0,
            column=4,
            sticky="ew",
            padx=(6, 0),
        )

        tk.Label(
            right_frame,
            text="Version History",
            bg=self.default_bg,
            font=("Segoe UI", 8),
        ).grid(row=3, column=0, sticky="w", pady=(0, 2))

        history_frame = tk.Frame(right_frame, bg=self.default_bg, bd=1, relief=tk.SUNKEN)
        history_frame.grid(row=4, column=0, sticky="nsew")
        history_frame.rowconfigure(0, weight=1)
        history_frame.columnconfigure(0, weight=1)

        self.version_tree = ttk.Treeview(
            history_frame,
            columns=("version", "change", "changed_at"),
            show="headings",
            selectmode="browse",
            height=6,
            style="VersionTree.Treeview",
        )
        self.version_tree.heading("version", text="Version")
        self.version_tree.heading("change", text="Change")
        self.version_tree.heading("changed_at", text="Changed At")
        self.version_tree.column("version", width=120, anchor="center", stretch=False)
        self.version_tree.column("change", width=170, anchor="w", stretch=False)
        self.version_tree.column("changed_at", width=210, anchor="w", stretch=True)
        self.version_tree.grid(row=0, column=0, sticky="nsew")

        tk.Button(right_frame, text="Restore Selected Version", command=self.restore_selected_version).grid(
            row=5,
            column=0,
            sticky="ew",
            pady=(8, 0),
        )

        self.body_pane.add(left_frame, minsize=620)
        self.body_pane.add(right_frame, minsize=430)

        footer_frame = tk.Frame(self.root, bg=self.default_bg, bd=1, relief=tk.SUNKEN)
        footer_frame.grid(row=2, column=0, sticky="ew", padx=0, pady=(6, 0))
        footer_frame.columnconfigure(0, weight=1)

        tk.Label(footer_frame, textvariable=self.footer_status_var, bg=self.default_bg, anchor="w").grid(
            row=0,
            column=0,
            sticky="w",
            padx=4,
            pady=2,
        )
        tk.Label(footer_frame, textvariable=self.version_label_var, bg=self.default_bg, anchor="e").grid(
            row=0,
            column=1,
            sticky="e",
            padx=4,
            pady=2,
        )

    def _make_form_label(self, parent: tk.Widget, text: str, row: int, width: int, sticky: str = "w") -> None:
        tk.Label(parent, text=text, bg=self.default_bg, width=width, anchor=sticky).grid(
            row=row,
            column=0,
            sticky=sticky,
            padx=(0, 8),
            pady=2,
        )

    def _bind_events(self) -> None:
        self.tree.bind("<<TreeviewSelect>>", self.on_tree_selection)
        self.candidate_var.trace_add("write", self.on_candidate_changed)
        self.view_mode_var.trace_add("write", self.on_view_mode_changed)
        self.candidate_combo.bind("<Button-3>", self.show_candidate_menu)
        self.candidate_combo.bind("<Shift-F10>", self.show_candidate_menu)
        self.candidate_combo.bind("<Insert>", lambda _event: self.create_candidate_from_dialog())
        self.candidate_combo.bind("<F2>", lambda _event: self.edit_selected_candidate())
        self.candidate_combo.bind("<Delete>", lambda _event: self.archive_selected_candidate())
        self.title_var.trace_add("write", self.on_form_changed)
        self.application_number_var.trace_add("write", self.on_form_changed)
        self.name_var.trace_add("write", self.on_form_changed)
        self.phone_var.trace_add("write", self.on_form_changed)
        self.status_var.trace_add("write", self.on_form_changed)
        self.short_note_text.bind("<KeyRelease>", lambda _event: self.on_form_changed())
        self.root.bind("<Configure>", self.on_window_configure)
        self.root.bind_all("<Control-s>", lambda _event: self._invoke_save_shortcut())
        self.root.bind_all("<Control-S>", lambda _event: self._invoke_save_shortcut())

    def _position_body_sash(self) -> None:
        if self.sash_positioned:
            return
        total_width = self.body_pane.winfo_width()
        if total_width <= 1:
            self.root.after(50, self._position_body_sash)
            return
        try:
            self.body_pane.sash_place(0, int(total_width * 0.575), 0)
            self.sash_positioned = True
        except tk.TclError:
            self.root.after(50, self._position_body_sash)

    def reload_data(
        self,
        *,
        selected_candidate_id: str = "",
        selected_record_id: str = "",
        select_first: bool = False,
        initial_restore: bool = False,
    ) -> None:
        records = self.csv_manager.load_records()
        candidates, reconciled_records, records_changed = self.candidate_manager.ensure_candidates_for_records(records)
        if records_changed:
            self.csv_manager.save_records(reconciled_records, backup_reason="candidate_link_migration")
            records = self.csv_manager.load_records()
            candidates, _, _ = self.candidate_manager.ensure_candidates_for_records(records)

        self.records = records
        self.candidates = candidates
        self.version_history_manager.ensure_baseline(self.records)
        self.refresh_candidate_options(preferred_candidate_id=selected_candidate_id or self.selected_candidate_id)
        self.apply_candidate_filter(selected_record_id=selected_record_id, select_first=select_first)
        if not initial_restore:
            self.set_status(f"Loaded {len(self.filtered_records)} visible record(s).")

    def refresh_candidate_options(self, preferred_candidate_id: str = "") -> None:
        labels, self.candidate_id_by_label, self.candidate_label_by_id = self.candidate_manager.build_dropdown_options(
            self.candidates,
            view_mode=self.view_mode_var.get(),
        )
        self.candidate_combo["values"] = ["None"] + labels
        self.set_selected_candidate(preferred_candidate_id)

    def set_selected_candidate(self, candidate_id: str) -> None:
        normalized_candidate_id = str(candidate_id).strip()
        if normalized_candidate_id and normalized_candidate_id not in self.candidate_label_by_id:
            normalized_candidate_id = ""
        self.selected_candidate_id = normalized_candidate_id
        label = self.candidate_label_by_id.get(normalized_candidate_id, "None")
        self.candidate_updates_suspended = True
        try:
            self.candidate_var.set(label)
        finally:
            self.candidate_updates_suspended = False
        self._previous_candidate_label = label
        self._sync_candidate_menu_state()

    def get_selected_candidate(self) -> dict[str, str] | None:
        if not self.selected_candidate_id:
            return None
        return self.candidate_manager.find_candidate(self.candidates, self.selected_candidate_id)

    def _sync_candidate_menu_state(self) -> None:
        selected_candidate = self.get_selected_candidate()
        has_candidate = bool(selected_candidate)
        has_archived_candidates = bool(self.candidate_manager.get_archived_candidates(self.candidates))
        has_archived_records = bool(self.csv_manager.get_archived_records(self.records, self.selected_candidate_id))
        selected_candidate_archived = bool(selected_candidate and selected_candidate.get("archived_at", "").strip())
        selected_record = self.csv_manager.find_record(self.records, self.current_record_id) if self.current_record_id else None
        selected_record_archived = bool(selected_record and selected_record.get("archived_at", "").strip())
        self.candidate_menu.entryconfigure(
            "Edit Selected Candidate...",
            state="normal" if has_candidate and not selected_candidate_archived else "disabled",
        )
        self.candidate_menu.entryconfigure(
            "Remove Selected Candidate",
            state="normal" if has_candidate and not selected_candidate_archived else "disabled",
        )
        self.candidate_menu.entryconfigure("Unarchive Candidate...", state="normal" if has_archived_candidates else "disabled")
        self.edit_candidate_button.configure(state="normal" if has_candidate and not selected_candidate_archived else "disabled")
        self.remove_candidate_button.configure(state="normal" if has_candidate and not selected_candidate_archived else "disabled")
        self.restore_candidate_button.configure(state="normal" if has_archived_candidates else "disabled")
        self.restore_record_button.configure(state="normal" if has_archived_records else "disabled")
        self.archive_record_button.configure(state="normal" if self.current_record_id and not selected_record_archived else "disabled")
        self.save_record_button.configure(state="normal" if not selected_record_archived else "disabled")

    def show_candidate_menu(self, event: tk.Event) -> str:
        self._sync_candidate_menu_state()
        x_root = getattr(event, "x_root", self.candidate_combo.winfo_rootx())
        y_root = getattr(event, "y_root", self.candidate_combo.winfo_rooty() + self.candidate_combo.winfo_height())
        self.candidate_menu.tk_popup(x_root, y_root)
        self.candidate_menu.grab_release()
        return "break"

    def _prompt_tree_selection(
        self,
        *,
        title: str,
        heading: str,
        columns: list[tuple[str, str, int, str]],
        rows: list[tuple[str, tuple[str, ...]]],
        confirm_label: str,
    ) -> str:
        dialog = tk.Toplevel(self.root)
        dialog.title(title)
        dialog.transient(self.root)
        dialog.resizable(True, True)
        dialog.geometry("760x360")
        dialog.minsize(620, 280)
        dialog.configure(bg=self.default_bg)
        dialog.columnconfigure(0, weight=1)
        dialog.rowconfigure(1, weight=1)

        tk.Label(dialog, text=heading, bg=self.default_bg, anchor="w").grid(
            row=0,
            column=0,
            sticky="ew",
            padx=10,
            pady=(10, 6),
        )

        tree_frame = tk.Frame(dialog, bg=self.default_bg, bd=1, relief=tk.SUNKEN)
        tree_frame.grid(row=1, column=0, sticky="nsew", padx=10)
        tree_frame.columnconfigure(0, weight=1)
        tree_frame.rowconfigure(0, weight=1)

        column_ids = [column_id for column_id, _label, _width, _anchor in columns]
        tree = ttk.Treeview(tree_frame, columns=column_ids, show="headings", selectmode="browse", style="VersionTree.Treeview")
        for column_id, label, width, anchor in columns:
            tree.heading(column_id, text=label)
            tree.column(column_id, width=width, anchor=anchor, stretch=True)
        tree.grid(row=0, column=0, sticky="nsew")

        scrollbar = tk.Scrollbar(tree_frame, orient=VERTICAL, command=tree.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        tree.configure(yscrollcommand=scrollbar.set)

        for row_id, values in rows:
            tree.insert("", END, iid=row_id, values=values)

        button_frame = tk.Frame(dialog, bg=self.default_bg)
        button_frame.grid(row=2, column=0, sticky="e", padx=10, pady=10)

        selection_holder = {"value": ""}

        def confirm_selection() -> None:
            selection = tree.selection()
            if not selection:
                messagebox.showinfo(title, "Select an archived item first.", parent=dialog)
                return
            selection_holder["value"] = str(selection[0])
            dialog.destroy()

        def cancel_selection() -> None:
            dialog.destroy()

        tk.Button(button_frame, text=confirm_label, width=12, command=confirm_selection).grid(row=0, column=0, padx=(0, 6))
        tk.Button(button_frame, text="Cancel", width=10, command=cancel_selection).grid(row=0, column=1)

        tree.bind("<Double-1>", lambda _event: confirm_selection())
        tree.bind("<Return>", lambda _event: confirm_selection())
        if rows:
            first_item = rows[0][0]
            tree.selection_set(first_item)
            tree.focus(first_item)
        dialog.grab_set()
        dialog.wait_window()
        return selection_holder["value"]

    def apply_session_state(self) -> None:
        saved_form = self.session_state.get("form_values", {})
        self.mode = self.session_state.get("mode", "idle")
        saved_view_mode = str(self.session_state.get("view_mode", "Active")).strip() or "Active"
        if saved_view_mode not in {"Active", "Archived", "All"}:
            saved_view_mode = "Active"
        self.view_mode_updates_suspended = True
        try:
            self.view_mode_var.set(saved_view_mode)
        finally:
            self.view_mode_updates_suspended = False
        self.refresh_candidate_options(preferred_candidate_id=self.selected_candidate_id)
        self._form_loading = True
        try:
            self.title_var.set(saved_form.get("title", ""))
            self.application_number_var.set(saved_form.get("application_number", ""))
            self.name_var.set(saved_form.get("name", ""))
            self.phone_var.set(saved_form.get("phone_number", ""))
            saved_status = str(saved_form.get("status", self.status_values[0]))
            if saved_status not in self.status_values:
                saved_status = self.status_values[0]
            self.status_var.set(saved_status)
            self.short_note_text.delete("1.0", END)
            self.short_note_text.insert("1.0", saved_form.get("short_note", ""))
        finally:
            self._form_loading = False
        self._form_dirty = False

        saved_candidate_id = str(self.session_state.get("selected_candidate_id", "")).strip()
        if not saved_candidate_id:
            saved_label = str(self.session_state.get("selected_candidate", "")).strip()
            if saved_label and saved_label != "None":
                matches = self.candidate_manager.find_candidates_by_name(self.candidates, saved_label, active_only=True)
                if len(matches) == 1:
                    saved_candidate_id = matches[0].get("candidate_id", "")

        self.set_selected_candidate(saved_candidate_id)

        selected_record_id = str(self.session_state.get("selected_record_id", "")).strip()
        if selected_record_id:
            record = self.csv_manager.find_record(self.records, selected_record_id)
            if record is not None and not record.get("archived_at", "").strip():
                self.set_selected_candidate(record.get("candidate_id", ""))
                self.apply_candidate_filter(selected_record_id=selected_record_id, select_first=False)
                self.load_record_into_form(record)
            else:
                self.apply_candidate_filter(selected_record_id="", select_first=False)
        else:
            self.apply_candidate_filter(selected_record_id="", select_first=False)

        if self.app_state.get("unclean_previous_shutdown"):
            self.set_status("Recovered previous session state.", error=True)
            messagebox.showwarning(
                "Recovered Previous Session",
                "Previous session appears to have closed unexpectedly.\n\n"
                "Application restored last saved candidate selection and form state.",
            )

    def apply_candidate_filter(self, selected_record_id: str = "", select_first: bool = False) -> None:
        self.filtered_records = self.csv_manager.filter_records(
            self.records,
            self.selected_candidate_id,
            self.view_mode_var.get(),
        )
        selected_record = self.populate_tree(selected_record_id=selected_record_id, select_first=select_first)
        if selected_record is not None:
            self.load_record_into_form(selected_record)
        else:
            self.prepare_form_for_candidate(self.get_selected_candidate())
        self.schedule_state_save()

    def populate_tree(self, selected_record_id: str = "", select_first: bool = False) -> dict[str, str] | None:
        self.tree.delete(*self.tree.get_children())
        first_item = ""
        first_record: dict[str, str] | None = None
        selected_item = ""
        selected_record: dict[str, str] | None = None

        for record in self.filtered_records:
            item_tags = ("archived",) if record.get("archived_at", "").strip() else ()
            item_id = self.tree.insert(
                "",
                END,
                values=(
                    record.get("record_id", ""),
                    record.get("application_number", ""),
                    record.get("referral_number", ""),
                    record.get("name", ""),
                    f"{record.get('status', '')} (Archived)" if record.get("archived_at", "").strip() else record.get("status", ""),
                    record.get("created_at", ""),
                    record.get("updated_at", ""),
                ),
                tags=item_tags,
            )
            if not first_item:
                first_item = item_id
                first_record = record
            if record.get("record_id", "") == selected_record_id:
                selected_item = item_id
                selected_record = record

        if selected_item:
            self.tree.selection_set(selected_item)
            self.tree.focus(selected_item)
            self.tree.see(selected_item)
            return selected_record

        if select_first and first_item and first_record is not None:
            self.tree.selection_set(first_item)
            self.tree.focus(first_item)
            self.tree.see(first_item)
            return first_record

        return None

    def prepare_form_for_candidate(self, candidate: dict[str, str] | None) -> None:
        self._form_loading = True
        try:
            self.current_record_id = ""
            self.title_var.set("")
            self.application_number_var.set("")
            self.phone_var.set("")
            self.status_var.set(self.status_values[0])
            self.created_at_var.set("-")
            self.updated_at_var.set("-")
            self.short_note_text.delete("1.0", END)
            self.name_var.set(candidate.get("display_name", "") if candidate else "")
            self.populate_version_history("")
            self.tree.selection_remove(self.tree.selection())
        finally:
            self._form_loading = False
        self._form_dirty = False
        self.set_mode("idle")

    def load_record_into_form(self, record: dict[str, str]) -> None:
        self._form_loading = True
        try:
            candidate_id = record.get("candidate_id", "")
            if candidate_id and candidate_id != self.selected_candidate_id:
                self.set_selected_candidate(candidate_id)
            self.current_record_id = record.get("record_id", "")
            self.title_var.set(record.get("title", ""))
            self.application_number_var.set(record.get("application_number", ""))
            self.name_var.set(record.get("name", ""))
            self.phone_var.set(record.get("phone_number", ""))
            status_value = record.get("status", "") or self.status_values[0]
            if status_value not in self.status_values:
                status_value = self.status_values[0]
            self.status_var.set(status_value)
            self.created_at_var.set(record.get("created_at", "") or "-")
            self.updated_at_var.set(record.get("updated_at", "") or "-")
            self.short_note_text.delete("1.0", END)
            self.short_note_text.insert("1.0", record.get("short_note", ""))
            self.populate_version_history(self.current_record_id)
        finally:
            self._form_loading = False
        self._form_dirty = False
        self.set_mode("edit")

    def collect_form_data(self) -> dict[str, str]:
        return {
            "record_id": self.current_record_id,
            "title": self.title_var.get().strip(),
            "application_number": self.application_number_var.get().strip(),
            "candidate_id": self.selected_candidate_id,
            "name": self.name_var.get().strip(),
            "phone_number": self.phone_var.get().strip(),
            "status": self.status_var.get().strip() or self.status_values[0],
            "short_note": self.short_note_text.get("1.0", END).strip(),
        }

    def validate_form_data(self, data: dict[str, str]) -> None:
        if not data["title"]:
            raise ValueError("Title is required.")
        if not self.candidate_manager.normalize_display_name(data["name"]):
            raise ValueError("Candidate name is required.")
        if data["status"] not in self.status_values:
            raise ValueError("Status must be one of configured values.")
        if data["phone_number"]:
            digits_only = "".join(character for character in data["phone_number"] if character.isdigit())
            if len(digits_only) < 7 or len(digits_only) > 15:
                raise ValueError("Phone number must contain between 7 and 15 digits.")

    def _clone_records(self, records: list[dict[str, str]]) -> list[dict[str, str]]:
        return [dict(record) for record in records]

    def _clone_candidates(self, candidates: list[dict[str, str]]) -> list[dict[str, str]]:
        return [dict(candidate) for candidate in candidates]

    def _persist_candidate_and_record_changes(
        self,
        updated_candidates: list[dict[str, str]],
        *,
        updated_records: list[dict[str, str]] | None = None,
        previous_records: list[dict[str, str]] | None = None,
        backup_reason: str = "updated",
    ) -> None:
        if updated_records is None:
            self.candidate_manager.save_candidates(updated_candidates)
            return

        rollback_records = self._clone_records(previous_records or self.records)
        self.csv_manager.save_records(updated_records, backup_reason=backup_reason)
        try:
            self.candidate_manager.save_candidates(updated_candidates)
        except Exception:
            self.logger.exception("Candidate persistence failed; rolling back records.")
            self.csv_manager.save_records(rollback_records, backup_reason=f"{backup_reason}_rollback")
            raise

    def _confirm_duplicate_candidate_name(self, display_name: str, action_label: str) -> bool:
        return messagebox.askyesno(
            "Duplicate Candidate Name",
            f"Active candidate with name '{display_name}' already exists.\n\nCreate duplicate candidate for {action_label}?",
        )

    def create_candidate_from_dialog(self) -> None:
        proposed_name = simpledialog.askstring(
            "New Candidate",
            "Candidate Name:",
            parent=self.root,
        )
        if proposed_name is None:
            return

        normalized_name = self.candidate_manager.normalize_display_name(proposed_name)
        if not normalized_name:
            messagebox.showwarning("New Candidate", "Candidate name cannot be blank.")
            return

        updated_candidates = self._clone_candidates(self.candidates)
        if self.candidate_manager.find_candidates_by_name(updated_candidates, normalized_name, active_only=True):
            if not self._confirm_duplicate_candidate_name(normalized_name, "new candidate"):
                return

        new_candidate = self.candidate_manager.create_candidate(updated_candidates, normalized_name)
        try:
            self._persist_candidate_and_record_changes(updated_candidates)
            self.reload_data(selected_candidate_id=new_candidate.get("candidate_id", ""), selected_record_id="", select_first=False)
            self.prepare_form_for_candidate(self.get_selected_candidate())
            self.set_status(f"Candidate '{new_candidate.get('display_name', '')}' created.")
        except Exception as exc:
            self.logger.exception("Failed to create candidate")
            self.session_manager.record_error(str(exc))
            self.set_status("Failed to create candidate.", error=True)
            messagebox.showerror("Candidate Error", f"Candidate could not be created.\n\n{exc}")

    def edit_selected_candidate(self) -> None:
        candidate = self.get_selected_candidate()
        if candidate is None:
            messagebox.showinfo("Edit Candidate", "Select candidate before editing.")
            return
        if candidate.get("archived_at", "").strip():
            messagebox.showinfo("Edit Candidate", "Unarchive candidate before editing.")
            return

        proposed_name = simpledialog.askstring(
            "Edit Candidate",
            "Candidate Name:",
            initialvalue=candidate.get("display_name", ""),
            parent=self.root,
        )
        if proposed_name is None:
            return

        normalized_name = self.candidate_manager.normalize_display_name(proposed_name)
        if not normalized_name:
            messagebox.showwarning("Edit Candidate", "Candidate name cannot be blank.")
            return
        if normalized_name == candidate.get("display_name", ""):
            return

        updated_candidates = self._clone_candidates(self.candidates)
        duplicate_matches = self.candidate_manager.find_candidates_by_name(
            updated_candidates,
            normalized_name,
            active_only=True,
            exclude_candidate_id=candidate.get("candidate_id", ""),
        )
        if duplicate_matches and not self._confirm_duplicate_candidate_name(normalized_name, "candidate rename"):
            return

        previous_records = self._clone_records(self.records)
        try:
            renamed_candidate = self.candidate_manager.rename_candidate(updated_candidates, candidate.get("candidate_id", ""), normalized_name)
            updated_records, affected_records = self.candidate_manager.sync_records_to_candidate(
                self._clone_records(self.records),
                renamed_candidate,
            )
            self._persist_candidate_and_record_changes(
                updated_candidates,
                updated_records=updated_records,
                previous_records=previous_records,
                backup_reason="candidate_renamed",
            )
            for affected_record in affected_records:
                self.version_history_manager.add_version(
                    affected_record.get("record_id", ""),
                    "CANDIDATE_EDIT",
                    affected_record,
                    changed_at=renamed_candidate.get("updated_at", ""),
                )
            self.reload_data(
                selected_candidate_id=renamed_candidate.get("candidate_id", ""),
                selected_record_id=self.current_record_id,
                select_first=bool(self.current_record_id),
            )
            self.set_status(f"Candidate renamed to '{renamed_candidate.get('display_name', '')}'.")
        except Exception as exc:
            self.logger.exception("Failed to edit candidate")
            self.session_manager.record_error(str(exc))
            self.set_status("Failed to edit candidate.", error=True)
            messagebox.showerror("Candidate Error", f"Candidate could not be updated.\n\n{exc}")

    def archive_selected_candidate(self) -> None:
        candidate = self.get_selected_candidate()
        if candidate is None:
            messagebox.showinfo("Archive Candidate", "Select candidate before archiving.")
            return
        if candidate.get("archived_at", "").strip():
            messagebox.showinfo("Archive Candidate", "Selected candidate is already archived.")
            return

        linked_records = [
            record
            for record in self.records
            if record.get("candidate_id", "") == candidate.get("candidate_id", "") and not record.get("archived_at", "").strip()
        ]
        record_count = len(linked_records)
        if not messagebox.askyesno(
            "Confirm Archive Candidate",
            f"Archive candidate '{candidate.get('display_name', '')}'?\n\nLinked active records: {record_count}\nAll linked active records will also be archived.",
        ):
            return

        updated_candidates = self._clone_candidates(self.candidates)
        previous_records = self._clone_records(self.records)
        try:
            archived_candidate = self.candidate_manager.archive_candidate(updated_candidates, candidate.get("candidate_id", ""))
            archive_timestamp = archived_candidate.get("archived_at", "")
            updated_records, affected_records = self.candidate_manager.sync_records_to_candidate(
                self._clone_records(self.records),
                archived_candidate,
                archive_records=True,
                archive_timestamp=archive_timestamp,
            )
            self._persist_candidate_and_record_changes(
                updated_candidates,
                updated_records=updated_records,
                previous_records=previous_records,
                backup_reason="candidate_archived",
            )
            for affected_record in affected_records:
                self.version_history_manager.add_version(
                    affected_record.get("record_id", ""),
                    "CANDIDATE_ARCHIVE",
                    affected_record,
                    changed_at=archive_timestamp,
                )
            self.current_record_id = ""
            self.reload_data(selected_candidate_id="", selected_record_id="", select_first=False)
            self.set_status(f"Candidate '{candidate.get('display_name', '')}' archived.")
        except Exception as exc:
            self.logger.exception("Failed to archive candidate")
            self.session_manager.record_error(str(exc))
            self.set_status("Failed to archive candidate.", error=True)
            messagebox.showerror("Candidate Error", f"Candidate could not be archived.\n\n{exc}")

    def open_unarchive_candidate_dialog(self) -> None:
        archived_candidates = self.candidate_manager.get_archived_candidates(self.candidates)
        if not archived_candidates:
            messagebox.showinfo("Unarchive Candidate", "No archived candidates are available.")
            return

        rows = [
            (
                candidate.get("candidate_id", ""),
                (
                    candidate.get("display_name", ""),
                    candidate.get("archived_at", ""),
                    candidate.get("candidate_id", ""),
                ),
            )
            for candidate in archived_candidates
        ]
        candidate_id = self._prompt_tree_selection(
            title="Unarchive Candidate",
            heading="Select archived candidate to restore.",
            columns=[
                ("display_name", "Candidate", 250, "w"),
                ("archived_at", "Archived At", 180, "w"),
                ("candidate_id", "Candidate ID", 180, "w"),
            ],
            rows=rows,
            confirm_label="Unarchive",
        )
        if not candidate_id:
            return

        candidate = self.candidate_manager.find_candidate(self.candidates, candidate_id)
        if candidate is None:
            messagebox.showwarning("Unarchive Candidate", "Selected archived candidate could not be found.")
            return

        if not messagebox.askyesno(
            "Confirm Unarchive Candidate",
            f"Unarchive candidate '{candidate.get('display_name', '')}'?",
        ):
            return

        try:
            updated_candidates = self._clone_candidates(self.candidates)
            restored_candidate = self.candidate_manager.restore_candidate(updated_candidates, candidate_id)
            self.candidate_manager.save_candidates(updated_candidates)
            self.reload_data(
                selected_candidate_id=restored_candidate.get("candidate_id", ""),
                selected_record_id="",
                select_first=False,
            )
            self.set_status(f"Candidate '{restored_candidate.get('display_name', '')}' unarchived.")
        except Exception as exc:
            self.logger.exception("Failed to unarchive candidate")
            self.session_manager.record_error(str(exc))
            self.set_status("Failed to unarchive candidate.", error=True)
            messagebox.showerror("Candidate Error", f"Candidate could not be unarchived.\n\n{exc}")

    def prepare_new_record(self) -> None:
        if self._form_dirty and not self._confirm_discard_unsaved_changes("New Record Report"):
            return
        self.prepare_form_for_candidate(self.get_selected_candidate())
        self._form_dirty = False
        self.set_mode("add")
        self.set_status("Ready to capture new record report.")
        self.schedule_state_save()

    def save_record(self) -> None:
        if self._save_in_progress:
            return
        self._save_in_progress = True
        original_record_id = self.current_record_id
        save_button_state = str(self.save_record_button.cget("state"))
        try:
            self.save_record_button.configure(state="disabled")
        except tk.TclError:
            pass
        try:
            self._save_record_inner(original_record_id)
        finally:
            self._save_in_progress = False
            try:
                self.save_record_button.configure(state=save_button_state)
            except tk.TclError:
                pass
            self._sync_candidate_menu_state()

    def _save_record_inner(self, original_record_id: str) -> None:
        form_data = self.collect_form_data()
        try:
            self.validate_form_data(form_data)

            previous_records = self.csv_manager.load_records()
            updated_records = self._clone_records(previous_records)
            updated_candidates = self._clone_candidates(self.candidates)

            existing_record = self.csv_manager.find_record(updated_records, self.current_record_id) if self.current_record_id else None
            if existing_record is not None and existing_record.get("archived_at", "").strip():
                raise ValueError("Unarchive record before editing.")
            current_candidate_id = self.selected_candidate_id or (existing_record.get("candidate_id", "") if existing_record else "")
            selected_candidate = self.candidate_manager.find_candidate(updated_candidates, current_candidate_id) if current_candidate_id else None

            extra_version_entries: list[tuple[str, str, dict[str, str], str]] = []
            normalized_name = self.candidate_manager.normalize_display_name(form_data.get("name", ""))

            if selected_candidate is not None:
                if normalized_name != selected_candidate.get("display_name", ""):
                    duplicate_matches = self.candidate_manager.find_candidates_by_name(
                        updated_candidates,
                        normalized_name,
                        active_only=True,
                        exclude_candidate_id=selected_candidate.get("candidate_id", ""),
                    )
                    if duplicate_matches and not self._confirm_duplicate_candidate_name(normalized_name, "record save"):
                        return
                    selected_candidate = self.candidate_manager.rename_candidate(
                        updated_candidates,
                        selected_candidate.get("candidate_id", ""),
                        normalized_name,
                    )
                    updated_records, affected_records = self.candidate_manager.sync_records_to_candidate(
                        updated_records,
                        selected_candidate,
                    )
                    for affected_record in affected_records:
                        if affected_record.get("record_id", "") != self.current_record_id:
                            extra_version_entries.append(
                                (
                                    affected_record.get("record_id", ""),
                                    "CANDIDATE_EDIT",
                                    affected_record,
                                    selected_candidate.get("updated_at", ""),
                                )
                            )
            else:
                active_name_matches = self.candidate_manager.find_candidates_by_name(
                    updated_candidates,
                    normalized_name,
                    active_only=True,
                )
                if len(active_name_matches) == 1:
                    selected_candidate = active_name_matches[0]
                elif len(active_name_matches) > 1:
                    raise ValueError("Multiple active candidates use this name. Select candidate from dropdown or use candidate menu.")
                else:
                    selected_candidate = self.candidate_manager.create_candidate(updated_candidates, normalized_name)

            if selected_candidate is None:
                raise ValueError("Candidate selection failed.")

            form_data["candidate_id"] = selected_candidate.get("candidate_id", "")
            form_data["name"] = selected_candidate.get("display_name", "")

            if existing_record is not None:
                saved_record = self.csv_manager.build_updated_record(original_record_id, form_data, existing_record)
                target_record_id = original_record_id
                updated_records = [
                    saved_record if record.get("record_id", "") == target_record_id else record
                    for record in updated_records
                ]
                version_change = "UPDATE"
                backup_reason = "updated"
            else:
                saved_record = self.csv_manager.build_new_record(form_data)
                target_record_id = saved_record.get("record_id", "")
                updated_records.append(saved_record)
                version_change = "CREATE"
                backup_reason = "created"

            candidate_changes_required = updated_candidates != self.candidates
            if candidate_changes_required:
                self._persist_candidate_and_record_changes(
                    updated_candidates,
                    updated_records=updated_records,
                    previous_records=previous_records,
                    backup_reason=backup_reason,
                )
            else:
                self.csv_manager.save_records(updated_records, backup_reason=backup_reason)

            self.current_record_id = target_record_id
            self.version_history_manager.add_version(
                target_record_id,
                version_change,
                saved_record,
                changed_at=saved_record.get("updated_at", ""),
            )
            for record_id, change, snapshot, changed_at in extra_version_entries:
                self.version_history_manager.add_version(record_id, change, snapshot, changed_at=changed_at)

            self._form_dirty = False
            self.reload_data(
                selected_candidate_id=selected_candidate.get("candidate_id", ""),
                selected_record_id=target_record_id,
                select_first=True,
            )
            self.session_manager.record_successful_save(
                len([record for record in self.records if not record.get("archived_at", "").strip()])
            )
            self.set_status(f"Record {target_record_id} saved.")
        except ValueError as exc:
            self.set_status(str(exc), error=True)
            messagebox.showwarning("Validation Error", str(exc))
        except Exception as exc:
            self.logger.exception("Failed to save record")
            self.session_manager.record_error(str(exc))
            self.set_status("Failed to save record.", error=True)
            messagebox.showerror(
                "Save Error",
                "Application could not save record.\n\n"
                "Technical message:\n"
                f"{exc}",
            )

    def archive_selected_record_entry(self) -> None:
        if not self.current_record_id:
            messagebox.showinfo("Archive Record", "Select record before archiving.")
            return

        record = self.csv_manager.find_record(self.records, self.current_record_id)
        if record is None:
            messagebox.showwarning("Archive Record", "Selected record could not be found.")
            return
        if record.get("archived_at", "").strip():
            messagebox.showinfo("Archive Record", "Selected record is already archived.")
            return

        if self._form_dirty and not self._confirm_discard_unsaved_changes("Archive Record"):
            return

        if not messagebox.askyesno(
            "Confirm Archive",
            f"Archive record {self.current_record_id}?\n\nCSV backup will be created before file is replaced.",
        ):
            return

        try:
            previous_records = self.csv_manager.load_records()
            existing_record = self.csv_manager.find_record(previous_records, self.current_record_id)
            if existing_record is None:
                raise ValueError("Selected record no longer exists on disk.")
            archived_record = self.csv_manager.build_archived_record(existing_record)
            updated_records = [
                archived_record if record_item.get("record_id", "") == self.current_record_id else record_item
                for record_item in previous_records
            ]
            self.csv_manager.save_records(updated_records, backup_reason="archived")
            self.version_history_manager.add_version(
                self.current_record_id,
                "ARCHIVE",
                archived_record,
                changed_at=archived_record.get("updated_at", ""),
            )
            self.current_record_id = ""
            self.reload_data(selected_candidate_id=self.selected_candidate_id, selected_record_id="", select_first=False)
            self.session_manager.record_successful_save(
                len([record_item for record_item in self.records if not record_item.get("archived_at", "").strip()])
            )
            self.set_status(f"Record {record.get('record_id', '')} archived.")
        except Exception as exc:
            self.logger.exception("Failed to archive record")
            self.session_manager.record_error(str(exc))
            self.set_status("Failed to archive record.", error=True)
            messagebox.showerror("Archive Error", f"Record could not be archived.\n\n{exc}")

    def open_unarchive_record_dialog(self) -> None:
        archived_records = self.csv_manager.get_archived_records(self.records, self.selected_candidate_id)
        if not archived_records:
            if self.selected_candidate_id:
                messagebox.showinfo("Unarchive Record", "No archived records are available for the selected candidate.")
            else:
                messagebox.showinfo("Unarchive Record", "No archived records are available.")
            return

        rows = [
            (
                record.get("record_id", ""),
                (
                    record.get("record_id", ""),
                    record.get("name", ""),
                    record.get("title", ""),
                    record.get("archived_at", ""),
                ),
            )
            for record in archived_records
        ]
        record_id = self._prompt_tree_selection(
            title="Unarchive Record",
            heading="Select archived record to restore.",
            columns=[
                ("record_id", "Record ID", 120, "w"),
                ("name", "Candidate", 170, "w"),
                ("title", "Title", 180, "w"),
                ("archived_at", "Archived At", 180, "w"),
            ],
            rows=rows,
            confirm_label="Unarchive",
        )
        if not record_id:
            return

        record = self.csv_manager.find_record(self.records, record_id)
        if record is None:
            messagebox.showwarning("Unarchive Record", "Selected archived record could not be found.")
            return

        if not messagebox.askyesno(
            "Confirm Unarchive Record",
            f"Unarchive record {record.get('record_id', '')}?",
        ):
            return

        try:
            previous_records = self.csv_manager.load_records()
            existing_record = self.csv_manager.find_record(previous_records, record_id)
            if existing_record is None:
                raise ValueError("Selected archived record no longer exists on disk.")

            restored_record = self.csv_manager.build_unarchived_record(existing_record)
            updated_records = [
                restored_record if record_item.get("record_id", "") == record_id else record_item
                for record_item in previous_records
            ]

            updated_candidates = self._clone_candidates(self.candidates)
            record_candidate = self.candidate_manager.find_candidate(updated_candidates, restored_record.get("candidate_id", ""))
            candidate_restored = False
            if record_candidate is not None and record_candidate.get("archived_at", "").strip():
                self.candidate_manager.restore_candidate(updated_candidates, record_candidate.get("candidate_id", ""))
                candidate_restored = True

            if candidate_restored:
                self._persist_candidate_and_record_changes(
                    updated_candidates,
                    updated_records=updated_records,
                    previous_records=previous_records,
                    backup_reason="record_unarchived",
                )
            else:
                self.csv_manager.save_records(updated_records, backup_reason="record_unarchived")

            self.version_history_manager.add_version(
                record_id,
                "UNARCHIVE",
                restored_record,
                changed_at=restored_record.get("updated_at", ""),
            )
            self.current_record_id = record_id
            self.reload_data(
                selected_candidate_id=restored_record.get("candidate_id", ""),
                selected_record_id=record_id,
                select_first=False,
            )
            self.set_status(f"Record {record_id} unarchived.")
        except Exception as exc:
            self.logger.exception("Failed to unarchive record")
            self.session_manager.record_error(str(exc))
            self.set_status("Failed to unarchive record.", error=True)
            messagebox.showerror("Unarchive Error", f"Record could not be unarchived.\n\n{exc}")

    def export_current_records(self) -> None:
        if not self.filtered_records:
            messagebox.showinfo("Export CSV", "No visible records to export for selected candidate.")
            return

        candidate_label = self._sanitize_filename_fragment(self.candidate_var.get())
        destination = filedialog.asksaveasfilename(
            title="Export CSV",
            defaultextension=".csv",
            initialdir=str(self.csv_path.parent),
            initialfile=f"candidate_records_{candidate_label}.csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if not destination:
            return

        try:
            self.csv_manager.export_records(self.filtered_records, Path(destination))
            self.set_status(f"Exported {len(self.filtered_records)} record(s) to {Path(destination).name}.")
            messagebox.showinfo("Export CSV", f"Exported {len(self.filtered_records)} record(s).")
        except Exception as exc:
            self.logger.exception("Failed to export CSV")
            self.set_status("Failed to export CSV.", error=True)
            messagebox.showerror("Export Error", f"CSV export failed.\n\n{exc}")

    @staticmethod
    def _sanitize_filename_fragment(value: str) -> str:
        cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", value or "")
        cleaned = cleaned.strip().replace(" ", "_").lower()
        cleaned = cleaned.strip("._")
        return cleaned or "export"

    def _invoke_save_shortcut(self) -> None:
        try:
            state = str(self.save_record_button.cget("state"))
        except tk.TclError:
            state = "normal"
        if state == "disabled":
            return
        self.save_record()

    def _confirm_discard_unsaved_changes(self, action_label: str) -> bool:
        if not self._form_dirty:
            return True
        return messagebox.askyesno(
            f"Unsaved Changes - {action_label}",
            "Detail form contains unsaved changes.\n\nDiscard changes and continue?",
        )

    def _restore_tree_selection_to_current(self) -> None:
        if not self.current_record_id:
            return
        for item_id in self.tree.get_children():
            values = self.tree.item(item_id, "values")
            if values and values[0] == self.current_record_id:
                self.tree.selection_set(item_id)
                self.tree.focus(item_id)
                return

    def populate_version_history(self, record_id: str) -> None:
        self.version_tree.delete(*self.version_tree.get_children())
        if not record_id:
            return
        entries = self.version_history_manager.list_versions(record_id)
        first_item = ""
        for entry in entries:
            item_id = self.version_tree.insert(
                "",
                END,
                values=(
                    f"Version {entry.get('version', '')}",
                    entry.get("change", ""),
                    entry.get("changed_at", ""),
                ),
            )
            if not first_item:
                first_item = item_id
        if first_item:
            self.version_tree.selection_set(first_item)
            self.version_tree.focus(first_item)

    def restore_selected_version(self) -> None:
        if not self.current_record_id:
            messagebox.showinfo("Restore Version", "Select record before restoring version.")
            return

        selection = self.version_tree.selection()
        if not selection:
            messagebox.showinfo("Restore Version", "Select version entry to restore.")
            return

        values = self.version_tree.item(selection[0], "values")
        if not values:
            return

        version_label = str(values[0])
        try:
            version_number = int(version_label.replace("Version", "").strip())
        except (TypeError, ValueError):
            messagebox.showwarning("Restore Version", "Selected version entry is malformed and cannot be restored.")
            return

        snapshot = self.version_history_manager.get_snapshot(self.current_record_id, version_number)
        if snapshot is None:
            messagebox.showwarning("Restore Version", "Selected version snapshot is no longer available.")
            return

        if self._form_dirty and not self._confirm_discard_unsaved_changes("Restore Version"):
            return

        if not messagebox.askyesno(
            "Confirm Restore",
            f"Restore {version_label} for record {self.current_record_id}?\n\nCSV backup will be created first.",
        ):
            return

        try:
            previous_records = self.csv_manager.load_records()
            updated_candidates = self._clone_candidates(self.candidates)

            snapshot_candidate_id = str(snapshot.get("candidate_id", "")).strip()
            selected_candidate = self.candidate_manager.find_candidate(updated_candidates, snapshot_candidate_id) if snapshot_candidate_id else None

            if selected_candidate is None:
                snapshot_name = self.candidate_manager.normalize_display_name(snapshot.get("name", ""))
                if not snapshot_name:
                    raise ValueError("Restored snapshot does not have valid candidate data.")
                name_matches = self.candidate_manager.find_candidates_by_name(updated_candidates, snapshot_name, active_only=True)
                if len(name_matches) == 1:
                    selected_candidate = name_matches[0]
                elif len(name_matches) > 1:
                    raise ValueError("Multiple active candidates use restored name. Select candidate manually before restoring.")
                else:
                    selected_candidate = self.candidate_manager.create_candidate(updated_candidates, snapshot_name)

            restored_snapshot = dict(snapshot)
            restored_snapshot["candidate_id"] = selected_candidate.get("candidate_id", "")
            restored_snapshot["name"] = selected_candidate.get("display_name", "")
            restored_record = self.csv_manager.build_restored_record(self.current_record_id, restored_snapshot)
            updated_records = [
                restored_record if record.get("record_id", "") == self.current_record_id else record
                for record in previous_records
            ]

            candidate_changes_required = updated_candidates != self.candidates
            if candidate_changes_required:
                self._persist_candidate_and_record_changes(
                    updated_candidates,
                    updated_records=updated_records,
                    previous_records=previous_records,
                    backup_reason="restored",
                )
            else:
                self.csv_manager.save_records(updated_records, backup_reason="restored")

            self.version_history_manager.add_version(
                self.current_record_id,
                "RESTORE",
                restored_record,
                changed_at=restored_record.get("updated_at", ""),
            )
            self.reload_data(
                selected_candidate_id=selected_candidate.get("candidate_id", ""),
                selected_record_id=self.current_record_id,
                select_first=True,
            )
            self.set_status(f"Restored {version_label} for record {self.current_record_id}.")
        except Exception as exc:
            self.logger.exception("Failed to restore version")
            self.session_manager.record_error(str(exc))
            self.set_status("Failed to restore version.", error=True)
            messagebox.showerror("Restore Error", f"Selected version could not be restored.\n\n{exc}")

    def on_tree_selection(self, _event: tk.Event) -> None:
        selection = self.tree.selection()
        if not selection:
            return
        values = self.tree.item(selection[0], "values")
        if not values:
            return
        record_id = values[0]
        if record_id == self.current_record_id:
            return
        if not self._confirm_discard_unsaved_changes("Switch Record"):
            self._restore_tree_selection_to_current()
            return
        record = self.csv_manager.find_record(self.records, record_id)
        if record is not None:
            self.load_record_into_form(record)
            self.set_status(f"Loaded record {record_id}.")
            self.schedule_state_save()

    def on_candidate_changed(self, *_args: Any) -> None:
        if self.candidate_updates_suspended:
            self._previous_candidate_label = self.candidate_var.get()
            return
        if self._form_dirty and not self._confirm_discard_unsaved_changes("Switch Candidate"):
            self.candidate_updates_suspended = True
            try:
                self.candidate_var.set(self._previous_candidate_label)
            finally:
                self.candidate_updates_suspended = False
            return
        self._form_dirty = False
        label = self.candidate_var.get().strip()
        self._previous_candidate_label = label or "None"
        self.selected_candidate_id = self.candidate_id_by_label.get(label, "")
        self._sync_candidate_menu_state()
        self.apply_candidate_filter(selected_record_id="", select_first=bool(self.selected_candidate_id))
        if self.selected_candidate_id:
            candidate = self.get_selected_candidate()
            candidate_name = candidate.get("display_name", "") if candidate else label
            self.set_status(f"Showing records for {candidate_name}.")
        else:
            self.set_status("Candidate selection cleared.")

    def on_view_mode_changed(self, *_args: Any) -> None:
        if self.view_mode_updates_suspended:
            return
        self.refresh_candidate_options(preferred_candidate_id=self.selected_candidate_id)
        self.apply_candidate_filter(selected_record_id="", select_first=bool(self.selected_candidate_id))
        self.set_status(f"Showing {self.view_mode_var.get().lower()} items.")

    def on_form_changed(self, *_args: Any) -> None:
        if not self._form_loading:
            self._form_dirty = True
        self.schedule_state_save()

    def on_window_configure(self, event: tk.Event) -> None:
        if event.widget is self.root:
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
                "selected_candidate": self.candidate_var.get().strip() or "None",
                "selected_candidate_id": self.selected_candidate_id,
                "view_mode": self.view_mode_var.get().strip() or "Active",
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
            "selected_candidate": self.candidate_var.get().strip() or "None",
            "selected_candidate_id": self.selected_candidate_id,
            "view_mode": self.view_mode_var.get().strip() or "Active",
            "selected_record_id": self.current_record_id,
            "mode": self.mode,
            "last_opened_at": self.session_state.get("last_opened_at", ""),
            "form_values": self.collect_form_data(),
        }

    def on_close(self) -> None:
        if self._form_dirty and not self._confirm_discard_unsaved_changes("Close Application"):
            return
        try:
            shutdown_state = self.build_shutdown_session_state()
            self.session_manager.mark_clean_shutdown(shutdown_state)
        except Exception:
            self.logger.exception("Failed during clean shutdown")
        finally:
            self.root.destroy()

    def set_mode(self, mode: str) -> None:
        self.mode = mode
        self.schedule_state_save()

    def set_status(self, message: str, error: bool = False) -> None:
        prefix = "Error: " if error else ""
        self.footer_status_var.set(f"{prefix}{message}")
::ENDFILE
::FILE|overwrite|app\version_history_manager.py
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from utils import current_timestamp, safe_json_load, safe_json_write


class VersionHistoryManager:
    def __init__(self, history_path: Path, logger: logging.Logger) -> None:
        self.history_path = history_path
        self.logger = logger

    def _load_store(self) -> dict[str, list[dict[str, Any]]]:
        payload = safe_json_load(
            self.history_path,
            {},
            logger=self.logger,
            invalid_backup_dir=self.history_path.parent / "invalid",
        )
        normalized: dict[str, list[dict[str, Any]]] = {}
        for record_id, entries in payload.items():
            if not isinstance(entries, list):
                continue
            normalized_entries: list[dict[str, Any]] = []
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                try:
                    version = int(entry.get("version", 0))
                except (TypeError, ValueError):
                    continue
                snapshot = entry.get("snapshot", {})
                if not isinstance(snapshot, dict):
                    snapshot = {}
                normalized_entries.append(
                    {
                        "version": version,
                        "change": str(entry.get("change", "")).strip() or "UNKNOWN",
                        "changed_at": str(entry.get("changed_at", "")).strip(),
                        "snapshot": {str(key): str(value) for key, value in snapshot.items()},
                    }
                )
            normalized_entries.sort(key=lambda item: item["version"])
            normalized[str(record_id)] = normalized_entries
        return normalized

    def _save_store(self, store: dict[str, list[dict[str, Any]]]) -> None:
        safe_json_write(self.history_path, store)

    def _normalize_snapshot(self, snapshot: dict[str, Any]) -> dict[str, str]:
        return {str(key): str(value).strip() for key, value in snapshot.items()}

    def ensure_baseline(self, records: list[dict[str, str]], change: str = "LEGACY_MIGRATION") -> None:
        store = self._load_store()
        changed = False
        for record in records:
            record_id = record.get("record_id", "").strip()
            if not record_id or store.get(record_id):
                continue
            store[record_id] = [
                {
                    "version": 1,
                    "change": change,
                    "changed_at": record.get("updated_at", "").strip() or current_timestamp(),
                    "snapshot": self._normalize_snapshot(record),
                }
            ]
            changed = True
        if changed:
            self._save_store(store)

    def list_versions(self, record_id: str) -> list[dict[str, Any]]:
        store = self._load_store()
        entries = store.get(record_id, [])
        return sorted(entries, key=lambda item: item["version"], reverse=True)

    def add_version(self, record_id: str, change: str, snapshot: dict[str, Any], changed_at: str | None = None) -> dict[str, Any]:
        store = self._load_store()
        entries = store.setdefault(record_id, [])
        next_version = max((int(entry.get("version", 0)) for entry in entries), default=0) + 1
        entry = {
            "version": next_version,
            "change": change,
            "changed_at": changed_at or current_timestamp(),
            "snapshot": self._normalize_snapshot(snapshot),
        }
        entries.append(entry)
        entries.sort(key=lambda item: item["version"])
        self._save_store(store)
        return entry

    def get_snapshot(self, record_id: str, version_number: int) -> dict[str, str] | None:
        for entry in self.list_versions(record_id):
            if int(entry.get("version", 0)) == version_number:
                snapshot = entry.get("snapshot", {})
                if isinstance(snapshot, dict):
                    return {str(key): str(value) for key, value in snapshot.items()}
        return None
::ENDFILE

::FILE|overwrite|app\candidate_manager.py
from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Any

from utils import current_timestamp, safe_json_load, safe_json_write


CANDIDATE_STORE_DEFAULT: dict[str, Any] = {
    "candidates": [],
}


class CandidateManager:
    def __init__(self, candidate_path: Path, logger: logging.Logger) -> None:
        self.candidate_path = candidate_path
        self.logger = logger

    def _load_store(self) -> dict[str, Any]:
        payload = safe_json_load(
            self.candidate_path,
            CANDIDATE_STORE_DEFAULT,
            logger=self.logger,
            invalid_backup_dir=self.candidate_path.parent / "invalid",
        )
        if not isinstance(payload.get("candidates"), list):
            payload["candidates"] = []
        return payload

    def _save_store(self, store: dict[str, Any]) -> None:
        safe_json_write(self.candidate_path, store)

    def normalize_display_name(self, display_name: str) -> str:
        return " ".join(str(display_name).strip().split())

    def generate_candidate_id(self) -> str:
        return f"CAN-{uuid.uuid4().hex[:12].upper()}"

    def _normalize_candidate(self, candidate: dict[str, Any], allow_generated_id: bool = False) -> dict[str, str]:
        candidate_id = str(candidate.get("candidate_id", "")).strip()
        if not candidate_id:
            if allow_generated_id:
                candidate_id = self.generate_candidate_id()
            else:
                raise ValueError("candidate_id is required")

        display_name = self.normalize_display_name(str(candidate.get("display_name", "")))
        if not display_name:
            raise ValueError("display_name is required")

        created_at = str(candidate.get("created_at", "")).strip() or current_timestamp()
        updated_at = str(candidate.get("updated_at", "")).strip() or created_at

        return {
            "candidate_id": candidate_id,
            "display_name": display_name,
            "archived_at": str(candidate.get("archived_at", "")).strip(),
            "created_at": created_at,
            "updated_at": updated_at,
        }

    def load_candidates(self) -> list[dict[str, str]]:
        store = self._load_store()
        candidates: list[dict[str, str]] = []
        for raw_candidate in store.get("candidates", []):
            if not isinstance(raw_candidate, dict):
                continue
            try:
                candidates.append(self._normalize_candidate(raw_candidate))
            except Exception:
                self.logger.exception("Failed to normalize candidate entry")
        candidates.sort(key=lambda item: (item.get("display_name", "").lower(), item.get("created_at", ""), item.get("candidate_id", "")))
        return candidates

    def save_candidates(self, candidates: list[dict[str, Any]]) -> None:
        normalized_candidates = [self._normalize_candidate(candidate, allow_generated_id=False) for candidate in candidates]
        normalized_candidates.sort(key=lambda item: (item.get("display_name", "").lower(), item.get("created_at", ""), item.get("candidate_id", "")))
        self._save_store({"candidates": normalized_candidates})

    def find_candidate(self, candidates: list[dict[str, str]], candidate_id: str) -> dict[str, str] | None:
        target_id = str(candidate_id).strip()
        for candidate in candidates:
            if candidate.get("candidate_id", "") == target_id:
                return candidate
        return None

    def find_candidates_by_name(
        self,
        candidates: list[dict[str, str]],
        display_name: str,
        *,
        active_only: bool = True,
        exclude_candidate_id: str = "",
    ) -> list[dict[str, str]]:
        normalized_name = self.normalize_display_name(display_name).casefold()
        excluded = str(exclude_candidate_id).strip()
        if not normalized_name:
            return []

        matches: list[dict[str, str]] = []
        for candidate in candidates:
            if excluded and candidate.get("candidate_id", "") == excluded:
                continue
            if active_only and candidate.get("archived_at", "").strip():
                continue
            if candidate.get("display_name", "").casefold() == normalized_name:
                matches.append(candidate)
        matches.sort(key=lambda item: (item.get("created_at", ""), item.get("candidate_id", "")))
        return matches

    def build_dropdown_options(
        self,
        candidates: list[dict[str, str]],
        *,
        view_mode: str = "Active",
    ) -> tuple[list[str], dict[str, str], dict[str, str]]:
        normalized_view_mode = str(view_mode).strip().lower() or "active"
        if normalized_view_mode == "archived":
            visible_candidates = [candidate for candidate in candidates if candidate.get("archived_at", "").strip()]
        elif normalized_view_mode == "all":
            visible_candidates = list(candidates)
        else:
            visible_candidates = [candidate for candidate in candidates if not candidate.get("archived_at", "").strip()]

        name_counts: dict[str, int] = {}
        for candidate in visible_candidates:
            key = candidate.get("display_name", "")
            name_counts[key] = name_counts.get(key, 0) + 1

        labels: list[str] = []
        candidate_id_by_label: dict[str, str] = {}
        candidate_label_by_id: dict[str, str] = {}
        for candidate in visible_candidates:
            label = candidate.get("display_name", "")
            if name_counts.get(label, 0) > 1:
                label = f"{label} [{candidate.get('candidate_id', '')[-6:]}]"
            if candidate.get("archived_at", "").strip():
                label = f"{label} (Archived)"
            labels.append(label)
            candidate_id_by_label[label] = candidate.get("candidate_id", "")
            candidate_label_by_id[candidate.get("candidate_id", "")] = label
        return labels, candidate_id_by_label, candidate_label_by_id

    def get_archived_candidates(self, candidates: list[dict[str, str]]) -> list[dict[str, str]]:
        archived_candidates = [candidate for candidate in candidates if candidate.get("archived_at", "").strip()]
        archived_candidates.sort(
            key=lambda item: (
                item.get("archived_at", ""),
                item.get("display_name", "").lower(),
                item.get("candidate_id", ""),
            ),
            reverse=True,
        )
        return archived_candidates

    def create_candidate(self, candidates: list[dict[str, str]], display_name: str) -> dict[str, str]:
        candidate = self._normalize_candidate(
            {
                "candidate_id": self.generate_candidate_id(),
                "display_name": display_name,
                "archived_at": "",
                "created_at": current_timestamp(),
                "updated_at": current_timestamp(),
            },
            allow_generated_id=False,
        )
        candidates.append(candidate)
        candidates.sort(key=lambda item: (item.get("display_name", "").lower(), item.get("created_at", ""), item.get("candidate_id", "")))
        return candidate

    def rename_candidate(self, candidates: list[dict[str, str]], candidate_id: str, display_name: str) -> dict[str, str]:
        candidate = self.find_candidate(candidates, candidate_id)
        if candidate is None:
            raise ValueError("Selected candidate no longer exists.")
        candidate["display_name"] = self.normalize_display_name(display_name)
        candidate["updated_at"] = current_timestamp()
        return candidate

    def archive_candidate(self, candidates: list[dict[str, str]], candidate_id: str) -> dict[str, str]:
        candidate = self.find_candidate(candidates, candidate_id)
        if candidate is None:
            raise ValueError("Selected candidate no longer exists.")
        timestamp = current_timestamp()
        candidate["archived_at"] = timestamp
        candidate["updated_at"] = timestamp
        return candidate

    def restore_candidate(self, candidates: list[dict[str, str]], candidate_id: str) -> dict[str, str]:
        candidate = self.find_candidate(candidates, candidate_id)
        if candidate is None:
            raise ValueError("Selected candidate no longer exists.")
        candidate["archived_at"] = ""
        candidate["updated_at"] = current_timestamp()
        return candidate

    def ensure_candidates_for_records(
        self,
        records: list[dict[str, str]],
    ) -> tuple[list[dict[str, str]], list[dict[str, str]], bool]:
        candidates = self.load_candidates()
        updated_records: list[dict[str, str]] = []
        records_changed = False
        candidates_changed = False

        for record in records:
            updated_record = dict(record)
            candidate_id = str(updated_record.get("candidate_id", "")).strip()
            display_name = self.normalize_display_name(updated_record.get("name", ""))

            candidate: dict[str, str] | None = None
            if candidate_id:
                candidate = self.find_candidate(candidates, candidate_id)
                if candidate is None:
                    fallback_name = display_name or candidate_id
                    candidate = self._normalize_candidate(
                        {
                            "candidate_id": candidate_id,
                            "display_name": fallback_name,
                            "archived_at": updated_record.get("archived_at", ""),
                            "created_at": updated_record.get("created_at", ""),
                            "updated_at": updated_record.get("updated_at", ""),
                        }
                    )
                    candidates.append(candidate)
                    candidates_changed = True
            elif display_name:
                name_matches = self.find_candidates_by_name(candidates, display_name, active_only=False)
                if len(name_matches) == 1:
                    candidate = name_matches[0]
                else:
                    candidate = self.create_candidate(candidates, display_name)
                    candidates_changed = True
                updated_record["candidate_id"] = candidate.get("candidate_id", "")
                records_changed = True

            if candidate is not None:
                if candidate.get("archived_at", "").strip() and not updated_record.get("archived_at", "").strip():
                    candidate["archived_at"] = ""
                    candidate["updated_at"] = current_timestamp()
                    candidates_changed = True
                if updated_record.get("candidate_id", "") != candidate.get("candidate_id", ""):
                    updated_record["candidate_id"] = candidate.get("candidate_id", "")
                    records_changed = True
                if updated_record.get("name", "") != candidate.get("display_name", ""):
                    updated_record["name"] = candidate.get("display_name", "")
                    records_changed = True

            updated_records.append(updated_record)

        if candidates_changed:
            self.save_candidates(candidates)
            candidates = self.load_candidates()
        return candidates, updated_records, records_changed

    def sync_records_to_candidate(
        self,
        records: list[dict[str, str]],
        candidate: dict[str, str],
        *,
        archive_records: bool = False,
        archive_timestamp: str = "",
    ) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
        updated_records: list[dict[str, str]] = []
        affected_records: list[dict[str, str]] = []
        timestamp = archive_timestamp or current_timestamp()

        for record in records:
            updated_record = dict(record)
            if updated_record.get("candidate_id", "") == candidate.get("candidate_id", ""):
                changed = False
                if updated_record.get("name", "") != candidate.get("display_name", ""):
                    updated_record["name"] = candidate.get("display_name", "")
                    changed = True
                if archive_records and not updated_record.get("archived_at", "").strip():
                    updated_record["archived_at"] = timestamp
                    updated_record["updated_at"] = timestamp
                    changed = True
                elif changed:
                    updated_record["updated_at"] = timestamp
                if changed:
                    affected_records.append(updated_record)
            updated_records.append(updated_record)

        return updated_records, affected_records
::ENDFILE

::FILE|overwrite|app\main.py
from __future__ import annotations

import logging
import sys
from pathlib import Path
import tkinter as tk
from tkinter import messagebox

from candidate_manager import CandidateManager
from csv_manager import CSVManager
from gui import RecordManagerApp
from session_manager import SessionManager
from utils import APP_ENCODING, ensure_dir, format_exception, safe_json_load, safe_json_write
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
    candidate_manager = CandidateManager(
        candidate_path=data_dir / "candidates.json",
        logger=logger,
    )
    version_history_manager = VersionHistoryManager(
        history_path=data_dir / "record_versions.json",
        logger=logger,
    )

    logger.info("Starting application from %s", project_root)
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
            logger.exception("Failed to display error dialog")

    def global_exception_handler(exc_type, exc_value, exc_traceback) -> None:
        logger.error("Unhandled exception", exc_info=(exc_type, exc_value, exc_traceback))
        try:
            session_manager.record_error(str(exc_value))
        except Exception:
            logger.exception("Failed to record error state from excepthook")
        if root.winfo_exists():
            report_to_user(exc_value)

    def tk_callback_exception(exc_type, exc_value, exc_traceback) -> None:
        logger.error("Unhandled Tk callback exception", exc_info=(exc_type, exc_value, exc_traceback))
        try:
            session_manager.record_error(str(exc_value))
        except Exception:
            logger.exception("Failed to record Tk callback error state")
        report_to_user(exc_value)

    sys.excepthook = global_exception_handler
    root.report_callback_exception = tk_callback_exception

    RecordManagerApp(
        root=root,
        settings=settings,
        csv_manager=csv_manager,
        candidate_manager=candidate_manager,
        session_manager=session_manager,
        version_history_manager=version_history_manager,
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
    "updated_at"
  ],
  "status_values": [
    "Open",
    "Clone",
    "In Progress",
    "Forfeited"
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

- The dashboard table shows `Record ID`, `Name`, `Phone Number`, `Status`, `Created At`, `Updated At`, and `Short Note / Description`.
- `Title` and `Category` use editable dropdowns: existing values are offered automatically, but new values can still be typed.
- The right-side form supports `Title`, `Category`, `Name`, `Phone Number`, `Status`, `Created At`, `Updated At`, and `Short Note / Description`.

## Rerun safety

Running `run_app.bat` repeatedly does not delete existing CSV or session files. Managed code files are refreshed from the BAT payload; user data files are only created when missing.
::ENDFILE
