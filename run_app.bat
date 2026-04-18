@echo off
setlocal EnableExtensions

title Record Manager Launcher
cd /d "%~dp0"

set "ROOT_DIR=%~dp0"
if not "%ROOT_DIR:~-1%"=="\" set "ROOT_DIR=%ROOT_DIR%\"
set "PYTHON_EXE="
set "PYTHONW_EXE="
set "PYTHON_INSTALLER=%TEMP%\record_manager_python_installer.exe"
set "PYTHON_TARGET_DIR="
set "PYTHON_INSTALL_URL="

echo ==================================================
echo Record Manager Launcher
echo ==================================================
echo Root: "%ROOT_DIR%"
echo.

call :ConfigurePythonDownload

echo [1/7] Verifying PowerShell availability...
where powershell.exe >nul 2>&1
if errorlevel 1 (
    call :Fatal "Windows PowerShell is required to prepare and launch the application."
    endlocal & exit /b 1
)

echo [2/7] Locating Python...
call :LocatePython
if not defined PYTHON_EXE (
    echo Python was not found on this system.
    echo Attempting a silent current-user installation...
    call :InstallPython
    if errorlevel 1 (
        call :Fatal "Python could not be installed automatically."
        endlocal & exit /b 1
    )
    call :RefreshEnvironment
    call :LocatePython
)
if not defined PYTHON_EXE (
    call :Fatal "Python installation completed but python.exe is still not discoverable."
    endlocal & exit /b 1
)
call :LocatePythonw

echo Using Python: "%PYTHON_EXE%"
echo [3/7] Verifying Python runtime...
"%PYTHON_EXE%" --version >nul 2>&1
if errorlevel 1 (
    call :Fatal "Python was found but could not be executed."
    endlocal & exit /b 1
)

echo [4/7] Verifying pip...
call :VerifyPip
if errorlevel 1 (
    call :Fatal "pip could not be verified or initialized."
    endlocal & exit /b 1
)

echo [5/7] Ensuring runtime folder structure exists...
call :EnsureFolders
if errorlevel 1 (
    call :Fatal "One or more required folders could not be created."
    endlocal & exit /b 1
)

echo [6/7] Verifying repository runtime files...
call :VerifyRuntimeFiles
if errorlevel 1 (
    call :Fatal "One or more required application files are missing."
    endlocal & exit /b 1
)

echo [7/7] Runtime dependency audit...
"%PYTHON_EXE%" -c "import tkinter, sqlite3, hashlib, csv, json, logging, pathlib, urllib.request" >nul 2>&1
if errorlevel 1 (
    call :Fatal "Python executed, but one or more required standard-library modules could not be imported."
    endlocal & exit /b 1
)
echo Runtime checks passed.

if /I "%RUN_APP_NO_LAUNCH%"=="1" (
    echo Launch suppressed because RUN_APP_NO_LAUNCH=1 was provided for validation.
    endlocal & exit /b 0
)

echo.
echo Launching application...
call :LaunchApplication
set "APP_EXIT=%ERRORLEVEL%"
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

if defined PYTHON_TARGET_DIR call :TryPythonCandidate "%PYTHON_TARGET_DIR%\python.exe"
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

:LocatePythonw
set "PYTHONW_EXE="
if not defined PYTHON_EXE exit /b 0
for %%I in ("%PYTHON_EXE%") do set "PYTHONW_EXE=%%~dpIpythonw.exe"
if not exist "%PYTHONW_EXE%" set "PYTHONW_EXE="
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
    "%ROOT_DIR%data\backups\runtime"
    "%ROOT_DIR%data\backups\db"
    "%ROOT_DIR%data\snapshots"
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

:VerifyRuntimeFiles
for %%F in (
    "%ROOT_DIR%app\main.py"
    "%ROOT_DIR%app\gui.py"
    "%ROOT_DIR%app\database.py"
    "%ROOT_DIR%app\services.py"
    "%ROOT_DIR%app\source_sync.py"
    "%ROOT_DIR%app\authorization.py"
    "%ROOT_DIR%app\repositories.py"
    "%ROOT_DIR%app\security.py"
    "%ROOT_DIR%app\validators.py"
    "%ROOT_DIR%config\settings.json"
) do (
    if not exist "%%~fF" (
        echo Missing required file: %%~fF
        exit /b 1
    )
)
exit /b 0

:LaunchApplication
if defined PYTHONW_EXE if /I not "%RUN_APP_USE_CONSOLE%"=="1" (
    start "" "%PYTHONW_EXE%" "%ROOT_DIR%app\main.py"
    echo Application launched with pythonw.exe.
    exit /b 0
)

"%PYTHON_EXE%" "%ROOT_DIR%app\main.py"
set "APP_EXIT=%ERRORLEVEL%"
if not "%APP_EXIT%"=="0" (
    echo.
    echo The application exited with code %APP_EXIT%.
    echo Review "%ROOT_DIR%session\logs\application.log" for technical details.
)
exit /b %APP_EXIT%

:Fatal
echo.
echo ERROR: %~1
echo.
if /I not "%RUN_APP_NO_LAUNCH%"=="1" if /I not "%RUN_APP_NO_PAUSE%"=="1" (
    echo Press any key to exit.
    pause >nul
)
exit /b 1
