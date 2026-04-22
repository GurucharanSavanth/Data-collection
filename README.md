# Record Manager Dashboard

Windows desktop record-tracking app built with Python and Tkinter.

## Recent UX Improvements

- Main table now supports live search across record ID, title, application number, referral number, candidate name, phone, status, notes, and timestamps.
- Header now shows live summary counts for visible, active, archived, and status-specific records.
- Unarchive dialogs now include search.
- Candidate unarchive can restore candidate only or candidate plus linked archived records in one action.

## Stack

- Python 3.12+
- Tkinter UI
- CSV + JSON local persistence
- PyInstaller onefile packaging

## App Launch

Development launch:

```powershell
python .\app\main.py
```

One-click launcher:

```powershell
.\run_app.bat
```

`run_app.bat` behavior:

- Default: if source changed after last packaged build, auto-build `dist\RecordManagerDashboard.exe`, then launch exe.
- If packaged exe is already current, launch exe directly.
- If packaged exe is missing, auto-build exe first.
- Source launch is now fallback or explicit override mode.

Launcher overrides:

- `RUN_APP_FORCE_SOURCE=1` -> skip exe and run `app\main.py`
- `RUN_APP_USE_EXE=1` -> force packaged exe mode
- `RUN_APP_FULL_BUILD=1` -> auto-build with full packaged validation before launch
- `RUN_APP_NO_LAUNCH=1` -> validate/build only, do not open UI

Launcher validation without UI:

```powershell
$env:RUN_APP_NO_LAUNCH=1
.\run_app.bat
```

Force source mode:

```powershell
$env:RUN_APP_FORCE_SOURCE=1
.\run_app.bat
```

Force exe mode:

```powershell
$env:RUN_APP_USE_EXE=1
.\run_app.bat
```

## Writable Storage

Source mode writes inside repo root:

- `data\`
- `config\`
- `session\`

Packaged `.exe` mode writes to:

- `%LOCALAPPDATA%\RecordManagerDashboard\`

Portable override options:

- `RECORD_MANAGER_DATA_DIR=C:\path\to\custom-root`
- `RECORD_MANAGER_PORTABLE=1`

Frozen first run also migrates legacy sidecar files from next to `.exe` into `%LOCALAPPDATA%\RecordManagerDashboard\` when no storage override is set.

Practical note:

- `run_app.bat` default now prefers packaged exe workflow.
- If you want runtime data to keep using repo-local `data\` and `session\`, use `RUN_APP_FORCE_SOURCE=1`.

## Release Build

Install build dependencies and produce validated onefile `.exe`:

```powershell
.\build.ps1
```

Batch wrapper:

```powershell
.\build.bat
```

Build pipeline steps:

1. Install pinned PyInstaller toolchain from `requirements-build.txt`
2. Run `python -m compileall .\app`
3. Build onefile executable with `RecordManagerDashboard.spec`
4. Run packaged `--self-test`
5. Run packaged `--startup-smoke`

Final artifact:

- `dist\RecordManagerDashboard.exe`

Build logs:

- `build\logs\build_*.log`
- `build\logs\exe_self_test_*.json`
- `build\logs\exe_startup_smoke_*.json`

## GitHub Releases

Official release page:

- `https://github.com/GurucharanSavanth/Data-collection/releases`

Latest public release observed:

- `V2`

## Validation Modes

Non-UI data/business flow validation:

```powershell
python .\app\main.py --self-test --storage-root .\build\source-self-test
```

Tk startup smoke:

```powershell
python .\app\main.py --startup-smoke --storage-root .\build\source-startup-smoke
```

Both modes also work on packaged executable.
