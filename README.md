# Record Manager Dashboard

Local-first Windows desktop app for role-scoped record reporting. The runtime now uses a normalized SQLite store with audit logging, version history, backup artifacts, and CSV/URL credential-source import instead of using `data/records.csv` as the live source of truth.

## Runtime stack

- Python + Tkinter desktop UI
- SQLite primary store at `data/runtime_store.db`
- JSON config and session state under `config/` and `session/`
- Legacy CSV migration/import helpers under `data/records.csv` and `data/backups/`

## Main features

- Bootstrap super-admin account, secure login, password reset-on-first-use
- Role hierarchy: `SUPER_ADMIN -> REGIONAL_MANAGER -> ASSOCIATE_MANAGER -> LOCAL_MANAGER -> CANDIDATE`
- Subtree-scoped dashboards, user management, hierarchy explorer, and candidate record oversight
- Candidate record workflow with unique `application_number`, fixed status enum, immutable version history, audit trail, archive/restore, and redundancy snapshots
- Credential source sync from `Offline (Path)` or `Online (URL)` with preview, validation, checksum, snapshot storage, and import audit

## Storage layout

- `data/runtime_store.db`: primary normalized runtime database
- `data/records.csv`: legacy import source only
- `data/backups/runtime/`: record/version/source snapshots and recovery artifacts
- `data/backups/legacy_csv/`: preserved legacy CSV backups
- `session/session_state.json`: UI/session preferences
- `session/app_state.json`: app lifecycle and last-save metadata
- `session/logs/application.log`: technical log output

## Record model

- `Title` remains `{ Name : Deployed Location }`
- `Application Number` is required and unique
- `Category` has been removed from runtime forms, validation, and exports
- `Status` is constrained to `Open`, `Clone`, `In Progress`, or `Forfeited`
- `Created At` stays immutable
- `Updated At` changes on meaningful updates

## Launch

- `.\run_app.bat`
- `$env:RUN_APP_NO_LAUNCH=1; .\run_app.bat`
- `python .\app\main.py`

`run_app.bat` is the primary double-click launcher. It verifies Python, prepares runtime folders, validates required source files, and launches the app with `pythonw.exe` when available for a cleaner desktop start. Use `RUN_APP_USE_CONSOLE=1` if you want to keep the console attached during launch.

## Launcher safety

`run_app.bat` no longer carries stale embedded source payloads. If required repository files are missing, launcher fails loudly instead of recreating outdated code.
