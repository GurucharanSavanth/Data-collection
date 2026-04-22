@echo off
setlocal EnableExtensions

title Record Manager Dashboard Launcher
cd /d "%~dp0"

set "ROOT_DIR=%~dp0"
if not "%ROOT_DIR:~-1%"=="\" set "ROOT_DIR=%ROOT_DIR%\"
set "APP_EXE=%ROOT_DIR%dist\RecordManagerDashboard.exe"
set "APP_SOURCE=%ROOT_DIR%app\main.py"
set "BUILD_SCRIPT=%ROOT_DIR%build.ps1"
set "LAUNCH_MODE=source"
set "LAUNCH_REASON=Source fallback."
set "BUILD_ARGS=-SkipValidation"
set "PYTHON_EXE="
set "PYTHON_INSTALLER=%TEMP%\record_manager_dashboard_python_installer.exe"
set "PYTHON_TARGET_DIR="
set "PYTHON_INSTALL_URL="

echo ==================================================
echo Record Manager Dashboard Launcher
echo ==================================================
echo Root: "%ROOT_DIR%"
echo.

echo [1/4] Resolving launch mode...
call :ResolveLaunchMode
echo Mode: %LAUNCH_MODE% ^| %LAUNCH_REASON%

if /I "%RUN_APP_FULL_BUILD%"=="1" (
    set "BUILD_ARGS="
)

if /I "%LAUNCH_MODE%"=="exe" (
    if /I "%RUN_APP_NO_LAUNCH%"=="1" (
        echo [2/4] Launch suppressed. Packaged executable is ready.
        endlocal & exit /b 0
    )

    echo [2/4] Launching packaged executable...
    "%APP_EXE%"
    set "APP_EXIT=%ERRORLEVEL%"

    if not "%APP_EXIT%"=="0" (
        echo.
        echo Packaged application exited with code %APP_EXIT%.
        echo If needed, check writable app data under %%LOCALAPPDATA%%\RecordManagerDashboard\session\logs\
    )

    endlocal & exit /b %APP_EXIT%
)

call :ConfigurePythonDownload

echo [2/4] Locating Python...
call :LocatePython
if not defined PYTHON_EXE (
    echo Python was not found on this system.
    echo Attempting silent current-user installation...
    call :InstallPython
    if errorlevel 1 call :Fatal "Python could not be installed automatically."
    call :RefreshEnvironment
    call :LocatePython
)
if not defined PYTHON_EXE call :Fatal "Python installation completed but python.exe is still not discoverable."

echo Using Python: "%PYTHON_EXE%"
echo [3/4] Verifying source runtime...
"%PYTHON_EXE%" -c "import tkinter, csv, json, logging, pathlib, uuid, tempfile, re" >nul 2>&1
if errorlevel 1 call :Fatal "Python executed, but one or more required standard-library modules could not be imported."

if not exist "%APP_SOURCE%" call :Fatal "Source entry point app\main.py is missing."

"%PYTHON_EXE%" -m compileall "%ROOT_DIR%app" >nul
if errorlevel 1 call :Fatal "Source compile smoke test failed."

if /I "%LAUNCH_MODE%"=="build_exe" (
    if not exist "%BUILD_SCRIPT%" call :Fatal "Build script build.ps1 is missing."

    echo [4/4] Building packaged executable...
    if defined BUILD_ARGS (
        powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%BUILD_SCRIPT%" %BUILD_ARGS%
    ) else (
        powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%BUILD_SCRIPT%"
    )
    if errorlevel 1 call :Fatal "Executable build failed."
    if not exist "%APP_EXE%" call :Fatal "Build completed but dist\RecordManagerDashboard.exe was not found."

    if /I "%RUN_APP_NO_LAUNCH%"=="1" (
        echo Build complete. Launch suppressed.
        endlocal & exit /b 0
    )

    echo Launching packaged executable...
    "%APP_EXE%"
    set "APP_EXIT=%ERRORLEVEL%"

    if not "%APP_EXIT%"=="0" (
        echo.
        echo Packaged application exited with code %APP_EXIT%.
        echo If needed, check writable app data under %%LOCALAPPDATA%%\RecordManagerDashboard\session\logs\
    )

    endlocal & exit /b %APP_EXIT%
)

if /I "%RUN_APP_NO_LAUNCH%"=="1" (
    echo [4/4] Launch suppressed. Source validation complete.
    endlocal & exit /b 0
)

echo [4/4] Launching source application...
"%PYTHON_EXE%" "%APP_SOURCE%"
set "APP_EXIT=%ERRORLEVEL%"

if not "%APP_EXIT%"=="0" (
    echo.
    echo Source application exited with code %APP_EXIT%.
    echo Review "%ROOT_DIR%session\logs\application.log" for technical details.
)

endlocal & exit /b %APP_EXIT%

:ResolveLaunchMode
set "LAUNCH_MODE=source"
set "LAUNCH_REASON=Source fallback."

if /I "%RUN_APP_FORCE_SOURCE%"=="1" (
    set "LAUNCH_REASON=RUN_APP_FORCE_SOURCE=1."
    exit /b 0
)

if /I "%RUN_APP_USE_EXE%"=="1" (
    if not exist "%APP_EXE%" (
        set "LAUNCH_MODE=build_exe"
        set "LAUNCH_REASON=RUN_APP_USE_EXE=1 and packaged executable is missing."
        exit /b 0
    )
    set "LAUNCH_MODE=exe"
    set "LAUNCH_REASON=RUN_APP_USE_EXE=1."
    exit /b 0
)

if not exist "%APP_SOURCE%" (
    if exist "%APP_EXE%" (
        set "LAUNCH_MODE=exe"
        set "LAUNCH_REASON=Source entry point missing. Using packaged executable."
    ) else (
        set "LAUNCH_REASON=Source entry point missing and packaged executable not found."
    )
    exit /b 0
)

if not exist "%APP_EXE%" (
    set "LAUNCH_MODE=build_exe"
    set "LAUNCH_REASON=Packaged executable missing. Auto-building."
    exit /b 0
)

where powershell.exe >nul 2>&1
if errorlevel 1 (
    set "LAUNCH_MODE=exe"
    set "LAUNCH_REASON=PowerShell unavailable. Using existing packaged executable."
    exit /b 0
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command ^
    "$ErrorActionPreference = 'Stop';" ^
    "$watchedPaths = @(" ^
    "  (Join-Path $env:ROOT_DIR 'app')," ^
    "  (Join-Path $env:ROOT_DIR 'RecordManagerDashboard.spec')," ^
    "  (Join-Path $env:ROOT_DIR 'build.ps1')," ^
    "  (Join-Path $env:ROOT_DIR 'requirements-build.txt')," ^
    "  (Join-Path $env:ROOT_DIR 'packaging\version_info.txt')," ^
    "  (Join-Path $env:ROOT_DIR 'config\settings.json')" ^
    ");" ^
    "$files = foreach ($watchedPath in $watchedPaths) {" ^
    "  if (-not (Test-Path -LiteralPath $watchedPath)) { continue }" ^
    "  $item = Get-Item -LiteralPath $watchedPath -Force;" ^
    "  if ($item.PSIsContainer) { Get-ChildItem -LiteralPath $item.FullName -Recurse -File } else { $item }" ^
    "};" ^
    "$latestSource = $files | Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 1;" ^
    "$exe = Get-Item -LiteralPath $env:APP_EXE;" ^
    "if ($null -eq $latestSource) { exit 0 }" ^
    "if ($latestSource.LastWriteTimeUtc -gt $exe.LastWriteTimeUtc) { exit 1 }" ^
    "exit 0"

if errorlevel 1 (
    set "LAUNCH_MODE=build_exe"
    set "LAUNCH_REASON=Source files changed after packaged executable."
    exit /b 0
)

set "LAUNCH_MODE=exe"
set "LAUNCH_REASON=Packaged executable is current."
exit /b 0

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
        echo winget reported success, but Python is still not available in current session.
    ) else (
        echo winget installation failed. Falling back to official Python installer...
    )
) else (
    echo winget is not available. Falling back to official Python installer...
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
start /wait "" "%PYTHON_INSTALLER%" /quiet InstallAllUsers=0 PrependPath=1 Include_pip=0 Include_tcltk=1 Include_test=0 Include_doc=0 Include_dev=0 Shortcuts=0 SimpleInstall=1 TargetDir="%PYTHON_TARGET_DIR%"
call :RefreshEnvironment
call :LocatePython
if defined PYTHON_EXE exit /b 0

echo Official installer completed, but Python is still not available in current session.
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

:Fatal
echo.
echo ERROR: %~1
echo.
exit /b 1
