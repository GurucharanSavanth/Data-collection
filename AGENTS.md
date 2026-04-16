# Repository Guidelines

## Project Structure & Module Organization
`app/` contains the Python application code: `main.py` boots the app, `gui.py` owns the Tkinter interface, `csv_manager.py` handles CSV storage and backups, `session_manager.py` persists UI/app state, and `utils.py` holds shared helpers. `config/settings.json` stores editable app settings. `data/records.csv` is the primary record store, with backups in `data/backups/`. `session/` holds runtime state and logs. `build/` and `dist/` are PyInstaller outputs and should be treated as generated artifacts.

## Build, Test, and Development Commands
Use Windows PowerShell from the repository root.

- `.\run_app.bat` bootstraps Python if needed, recreates managed files, and launches the desktop app.
- `$env:RUN_APP_NO_LAUNCH=1; .\run_app.bat` validates bootstrap and file generation without opening the UI.
- `python .\app\main.py` runs the app directly when Python is already installed.
- `python -m compileall .\app` performs a quick syntax smoke test across the source tree.
- `pyinstaller .\RecordManagerDashboard.spec` rebuilds `dist/RecordManagerDashboard.exe` when packaging changes are required.

## Coding Style & Naming Conventions
Follow the existing Python style: 4-space indentation, type hints on public functions, and short, single-purpose helpers. Use `snake_case` for functions, variables, and module names, `PascalCase` for classes, and `UPPER_SNAKE_CASE` for constants such as `DEFAULT_SETTINGS`. Keep UI behavior in `gui.py` and file/state persistence in the manager modules rather than mixing responsibilities.

## Testing Guidelines
There is no dedicated automated test suite yet. Before opening a PR, run `python -m compileall .\app`, launch the app with either `.\run_app.bat` or `python .\app\main.py`, and verify create, update, delete, filter, and session-restore flows against `data/records.csv`. If you add automated tests, place them under `tests/` and mirror the `app/` module names.

## Commit & Pull Request Guidelines
The current history uses short, imperative subjects (`first commit`). Keep commit titles concise and action-oriented, for example `Add CSV schema migration guard`. PRs should include a summary of user-visible changes, manual verification steps, and screenshots when `gui.py` changes affect layout or form behavior.

## Generated Data & Safety Notes
Do not hand-edit `build/`, `dist/`, `session/logs/`, or `app/__pycache__/`. Preserve real user data in `data/` and `session/` during refactors; the bootstrap script is designed to refresh managed code without deleting those files.
