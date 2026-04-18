# Record Manager Dashboard Documentation

## 1. Overview

Record Manager Dashboard is a local-first Windows desktop application built with Python and Tkinter. It is designed for role-based user management, candidate reporting, scoped record visibility, credential-source imports, record versioning, and recovery.

The application no longer uses `data/records.csv` as the live runtime source of truth. Runtime data is stored in a normalized SQLite database at:

- `data/runtime_store.db`

Legacy CSV files are still supported for:

- one-time migration
- source import
- raw source snapshot preservation
- CSV export

## 2. Core Capabilities

The application supports:

- secure role-based login
- one-time super-admin bootstrap
- password reset on first login where required
- hierarchy-based visibility and management
- scoped dashboards for managers and candidates
- candidate record creation and update
- unique application-number enforcement
- record version history
- recovery from prior record versions
- backup artifact creation on critical changes
- credential import from offline CSV path or online CSV URL
- audit logging for protected actions

## 3. Runtime Stack

- Language: Python
- UI framework: Tkinter / ttk
- Primary persistence: SQLite
- Config/state: JSON files
- Launcher: Windows batch file (`run_app.bat`)

Key runtime modules:

- `app/main.py` - startup, service wiring, logging, legacy migration
- `app/gui.py` - login/bootstrap UI and role dashboards
- `app/database.py` - SQLite initialization and transaction handling
- `app/repositories.py` - database data-access layer
- `app/services.py` - auth, users, records, backups, legacy migration
- `app/source_sync.py` - credential-source preview and commit workflow
- `app/authorization.py` - subtree and permission enforcement
- `app/security.py` - password hashing and verification
- `app/validators.py` - centralized validation rules
- `app/csv_manager.py` - legacy CSV helper, snapshots, export support
- `app/session_manager.py` - UI/session persistence

## 4. Project Structure

Important directories:

- `app/` - application source code
- `config/` - application settings
- `data/` - SQLite DB, legacy CSV, backups, snapshots
- `session/` - UI state, app state, runtime logs
- `tests/` - automated tests

Important runtime files:

- `run_app.bat`
- `config/settings.json`
- `data/runtime_store.db`
- `data/records.csv`
- `session/logs/application.log`
- `session/session_state.json`
- `session/app_state.json`

## 5. Launcher and Startup

### 5.1 Primary Entry Point

The primary point of contact for end users is:

- `run_app.bat`

Double-clicking `run_app.bat` is the intended launch flow.

### 5.2 What the Launcher Does

The launcher:

1. verifies PowerShell availability
2. locates Python
3. installs Python silently if needed
4. verifies pip
5. ensures runtime folders exist
6. verifies required repository files exist
7. audits required standard-library modules
8. launches the app

When available, the launcher uses `pythonw.exe` for a cleaner double-click experience without holding an open console window.

### 5.3 Validation Mode

To validate launcher setup without opening the app:

```powershell
$env:RUN_APP_NO_LAUNCH=1; .\run_app.bat
```

To force console-attached launch for debugging:

```powershell
$env:RUN_APP_USE_CONSOLE=1; .\run_app.bat
```

### 5.4 Important Launcher Safety Behavior

The launcher does **not** regenerate embedded source files from a stale batch payload. If required code files are missing, launch fails loudly rather than silently restoring outdated application logic.

## 6. First Launch and Bootstrap

If the database contains no users, the app opens in **Bootstrap Super Admin** mode.

Fields shown:

- Login ID
- Display Name
- Password
- Confirm Password

Default suggested values:

- Login ID: `super.admin`
- Display Name: `Super Admin`

You must choose your own password.

After bootstrap:

- the first SUPER_ADMIN account is created
- bootstrap is considered complete
- future launches open the normal login page

Important:

- SUPER_ADMIN can only be created through bootstrap
- SUPER_ADMIN is not created from the normal user-management form

## 7. Login and Password Handling

### 7.1 Login

Users log in with:

- Login ID
- Password

The login page also supports:

- Enter key submission
- show/hide password toggle
- last used login ID memory

### 7.2 Password Storage

Passwords are **not** stored in plaintext at runtime.

The application stores:

- secure password hashes only

### 7.3 Reset on First Use

Some accounts, especially imported or candidate accounts, may be marked as:

- `RESET_REQUIRED`

Such users must choose a new password before entering the dashboard.

## 8. Roles and Hierarchy

The application supports the following roles:

- `SUPER_ADMIN`
- `REGIONAL_MANAGER`
- `ASSOCIATE_MANAGER`
- `LOCAL_MANAGER`
- `CANDIDATE`

Hierarchy:

```text
SUPER_ADMIN
  -> REGIONAL_MANAGER
      -> ASSOCIATE_MANAGER
          -> LOCAL_MANAGER
              -> CANDIDATE
```

Additionally, a `REGIONAL_MANAGER` may directly own `LOCAL_MANAGER` users when allowed by the role rules.

## 9. Permission Model

Permissions are enforced centrally in the service/domain layer, not just in the UI.

### 9.1 High-Level Rules

- users can only manage allowed child roles
- users can only see their authorized subtree
- no lateral branch visibility
- no upward privilege leakage
- no self-promotion
- no editing of unauthorized peers or ancestors

### 9.2 Effective Management Scope

- SUPER_ADMIN can manage all downstream users
- REGIONAL_MANAGER can manage users in their own branch
- ASSOCIATE_MANAGER can manage users in their own branch
- LOCAL_MANAGER can manage only candidates in their own branch
- CANDIDATE cannot create or manage other users

## 10. Creating Users

The Users tab supports scoped user creation and updates.

### 10.1 Fields

- Login ID
- Role
- Candidate Name
- Deployed Location
- Phone
- Parent Login ID
- Password / Reset Password
- Active

### 10.2 Important Rules

- Login ID must be unique
- Parent Login ID must already exist
- Parent must be valid for the chosen role
- Candidate login ID also becomes referral number
- Parent must be within your authorized subtree

### 10.3 Parent Selection

The UI now provides a guided dropdown for `Parent Login ID`.

You should:

1. choose the target role first
2. select one of the allowed parent entries from the dropdown

The form also shows a hint listing valid parent login IDs for the selected role.

### 10.4 Example User Creation

Create first Regional Manager under Super Admin:

- Login ID: `region.north`
- Role: `REGIONAL_MANAGER`
- Candidate Name: `North Region Manager`
- Deployed Location: `North Zone`
- Phone: `9876543210`
- Parent Login ID: `super.admin`
- Password / Reset Password: `NorthRegion@123`
- Active: checked

Create Associate Manager:

- Login ID: `assoc.north.01`
- Role: `ASSOCIATE_MANAGER`
- Candidate Name: `Associate North One`
- Deployed Location: `North Hub`
- Phone: `9876500001`
- Parent Login ID: `region.north`
- Password / Reset Password: `AssocNorth@123`
- Active: checked

Create Local Manager:

- Login ID: `local.north.01`
- Role: `LOCAL_MANAGER`
- Candidate Name: `Local North One`
- Deployed Location: `North City`
- Phone: `9876500002`
- Parent Login ID: `assoc.north.01`
- Password / Reset Password: `LocalNorth@123`
- Active: checked

Create Candidate:

- Login ID: `cand.north.01`
- Role: `CANDIDATE`
- Candidate Name: `Ravi Kumar`
- Deployed Location: `North City Branch`
- Phone: `9876500003`
- Parent Login ID: `local.north.01`
- Password / Reset Password: `RaviTemp@123`
- Active: checked

## 11. Candidate Referral Number Rule

For candidates:

- referral number = login ID

This mapping is enforced consistently.

Example:

- Candidate Login ID: `cand.north.01`
- Referral Number: `cand.north.01`

## 12. Dashboards by Role

### 12.1 SUPER_ADMIN Dashboard

Includes:

- Records
- Users
- Hierarchy
- Credential Source
- Audit / Recovery

### 12.2 Manager Dashboards

Managers see:

- records in their authorized branch
- users in their authorized branch
- hierarchy tree for their subtree

### 12.3 Candidate Dashboard

Candidate dashboard shows:

- candidate name prominently
- own records only
- candidate referral/login context
- record form for own reports

## 13. Record Management

### 13.1 Record Form Fields

Current record fields:

- Title
- Application Number
- Name
- Phone Number
- Status
- Created At
- Updated At
- Short Notes / Description

Removed field:

- Category

### 13.2 Field Rules

#### Title

Title format remains:

```text
{ Name : Deployed Location }
```

For candidates, title is derived from candidate profile context.

#### Application Number

- required
- unique
- enforced in validation and database constraints

#### Status

Allowed values only:

- `Open`
- `Clone`
- `In Progress`
- `Forfeited`

#### Created At

- original creation timestamp
- should remain stable

#### Updated At

- updates on meaningful record changes

### 13.3 Candidate Record Table Columns

Candidate view shows:

- Record ID
- Name
- Phone Number
- Created At
- Referral Number

### 13.4 Manager Record Table

Manager views include broader oversight columns such as:

- Record ID
- Application Number
- Referral Number
- Name
- Status
- Created At
- Updated At

### 13.5 Buttons

Important button name:

- `Prepare New` was renamed to `New Record Report`

## 14. Record Save, Versioning, and Recovery

When a record is saved:

1. authorization is checked
2. input is validated
3. payload is normalized
4. primary row is inserted or updated
5. a version-history row is added
6. an audit row is added
7. a backup artifact is written
8. the UI is refreshed from persisted data

### 14.1 Version History

Every meaningful record change creates an entry in:

- `record_versions`

### 14.2 Archive Instead of Hard Delete

The UI uses archive behavior instead of destructive delete.

### 14.3 Restore

Users with permission can restore a selected record version from the Version History section.

## 15. Credential Source Sync

The application supports two credential-source modes:

- `Offline (Path)`
- `Online (URL)`

Only one mode is active at a time.

### 15.1 Offline Mode

Admin enters a local CSV file path.

### 15.2 Online Mode

Admin enters a CSV URL.

### 15.3 Import Workflow

The sync process is:

1. configure source
2. preview source
3. validate rows
4. inspect accepted and rejected rows
5. commit import

### 15.4 Source Snapshot Safety

For every committed import:

- raw source snapshot is preserved
- checksum is recorded
- snapshot metadata is stored
- row-level mapping results are saved

### 15.5 Typical Import Columns

Required:

- `login_id`
- `role`
- `display_name`

Optional:

- `referral_code`
- `parent_login_id`
- `password`
- `deployed_location`
- `phone`
- `active_flag`

## 16. Storage and Data Locations

### 16.1 Primary Database

- `data/runtime_store.db`

### 16.2 Legacy CSV

- `data/records.csv`

Used for:

- legacy migration source
- compatibility backup/import path

### 16.3 Backups

- `data/backups/runtime/`
- `data/backups/db/`
- `data/backups/legacy_csv/`

### 16.4 Source Snapshots

- `data/snapshots/`

### 16.5 Logs

- `session/logs/application.log`

## 17. Session and App State

The app persists UI state between runs:

- selected record
- selected candidate
- selected user
- last login ID
- form values
- window geometry/state

Files:

- `session/session_state.json`
- `session/app_state.json`

## 18. Security Notes

The application includes:

- hashed passwords only
- centralized authorization
- subtree-scoped visibility
- permission-denied audit logging
- constrained status and role values
- unique application number constraint
- import validation before commit

Sensitive values should not be written to:

- source control
- logs
- exported backups as plaintext passwords

## 19. Audit Logging

Protected actions create audit rows, including examples such as:

- login success/failure
- user creation
- user update
- password reset
- record create/update/restore
- import preview/commit
- source configuration updates
- permission-denied events

## 20. Troubleshooting

### 20.1 "Parent login ID does not exist."

Cause:

- the entered parent login ID is missing
- or it is not in your visible branch
- or you typed a value instead of using the allowed parent

Fix:

1. choose the target role first
2. use the Parent Login ID dropdown
3. verify the parent user already exists

Example for first manager:

- Parent Login ID must be `super.admin`

### 20.2 "Application Number must be unique."

Cause:

- another record already uses the same application number

Fix:

- enter a different application number

### 20.3 Invalid source path or URL

Cause:

- local file path does not exist
- URL is malformed
- CSV is missing required columns

Fix:

- correct the path/URL
- preview again before committing

### 20.4 Password reset blocks dashboard entry

Cause:

- account is marked `RESET_REQUIRED`

Fix:

- complete the password reset dialog

### 20.5 Check the log file

For technical investigation:

- open `session/logs/application.log`

## 21. Developer Validation Commands

Syntax check:

```powershell
python -m compileall .\app
```

Run tests:

```powershell
python -m unittest discover -s tests -v
```

Launcher validation:

```powershell
$env:RUN_APP_NO_LAUNCH=1; .\run_app.bat
```

Direct app launch:

```powershell
python .\app\main.py
```

## 22. Notes for Future Maintenance

- keep runtime truth in SQLite, not scattered CSV reads
- keep all role checks in services/authorization layer
- do not reintroduce plaintext password storage
- do not bypass versioning/audit on record updates
- do not bypass source preview validation on imports
- if hierarchy rules change, update centralized role maps rather than scattered UI logic

## 23. Quick Start Summary

1. double-click `run_app.bat`
2. if first launch, create `super.admin`
3. log in
4. create `REGIONAL_MANAGER` under `super.admin`
5. continue hierarchy creation downward
6. create candidate users under local managers
7. candidates log in and create `New Record Report` entries
8. managers monitor records in their scoped dashboards

