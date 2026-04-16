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
