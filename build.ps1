param(
    [switch]$SkipDependencyInstall,
    [switch]$SkipValidation
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path -LiteralPath $PSScriptRoot).Path
Set-Location -LiteralPath $repoRoot

$buildRoot = Join-Path $repoRoot "build"
$pyinstallerWorkRoot = Join-Path $buildRoot "pyinstaller"
$distRoot = Join-Path $repoRoot "dist"
$validationRoot = Join-Path $buildRoot "validation-runtime"
$logRoot = Join-Path $buildRoot "logs"
New-Item -ItemType Directory -Path $logRoot -Force | Out-Null

$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$buildLog = Join-Path $logRoot "build_$timestamp.log"

function Assert-RepoChildPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        return
    }

    $resolved = (Resolve-Path -LiteralPath $Path).Path
    if (-not $resolved.StartsWith($repoRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to modify path outside repository root: $resolved"
    }
}

function Reset-Directory {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    Assert-RepoChildPath -Path $Path
    if (Test-Path -LiteralPath $Path) {
        Remove-Item -LiteralPath $Path -Recurse -Force
    }
    New-Item -ItemType Directory -Path $Path -Force | Out-Null
}

function Invoke-LoggedCommand {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Description,
        [Parameter(Mandatory = $true)]
        [string]$Executable,
        [Parameter()]
        [string[]]$Arguments = @()
    )

    Write-Host "==> $Description"
    "==> $Description" | Tee-Object -FilePath $buildLog -Append | Out-Null

    $stdoutPath = Join-Path $logRoot ("stdout_" + [guid]::NewGuid().Guid + ".log")
    $stderrPath = Join-Path $logRoot ("stderr_" + [guid]::NewGuid().Guid + ".log")

    function Format-NativeArgument {
        param(
            [Parameter(Mandatory = $true)]
            [AllowEmptyString()]
            [string]$Argument
        )

        $escaped = $Argument -replace '(\\*)"', '$1$1\"'
        $escaped = $escaped -replace '(\\+)$', '$1$1'
        return '"' + $escaped + '"'
    }

    $quotedArguments = ($Arguments | ForEach-Object { Format-NativeArgument -Argument $_ }) -join " "

    try {
        $process = Start-Process `
            -FilePath $Executable `
            -ArgumentList $quotedArguments `
            -Wait `
            -PassThru `
            -NoNewWindow `
            -RedirectStandardOutput $stdoutPath `
            -RedirectStandardError $stderrPath

        foreach ($streamPath in @($stdoutPath, $stderrPath)) {
            if (Test-Path -LiteralPath $streamPath) {
                Get-Content -LiteralPath $streamPath | Tee-Object -FilePath $buildLog -Append
            }
        }

        if ($process.ExitCode -ne 0) {
            throw "$Description failed with exit code $($process.ExitCode)."
        }
    }
    finally {
        foreach ($streamPath in @($stdoutPath, $stderrPath)) {
            if (Test-Path -LiteralPath $streamPath) {
                Remove-Item -LiteralPath $streamPath -Force
            }
        }
    }
}

$pythonExe = (Get-Command python -ErrorAction Stop).Source

if (-not $SkipDependencyInstall) {
    Invoke-LoggedCommand `
        -Description "Install build dependencies" `
        -Executable $pythonExe `
        -Arguments @("-m", "pip", "install", "--disable-pip-version-check", "-r", "requirements-build.txt")
}

Invoke-LoggedCommand `
    -Description "Compile source" `
    -Executable $pythonExe `
    -Arguments @("-m", "compileall", "app")

Reset-Directory -Path $pyinstallerWorkRoot
Reset-Directory -Path $distRoot
Reset-Directory -Path $validationRoot

Invoke-LoggedCommand `
    -Description "Build onefile executable" `
    -Executable $pythonExe `
    -Arguments @(
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--distpath",
        $distRoot,
        "--workpath",
        $pyinstallerWorkRoot,
        "RecordManagerDashboard.spec"
    )

$exePath = Join-Path $distRoot "RecordManagerDashboard.exe"
if (-not (Test-Path -LiteralPath $exePath)) {
    throw "Expected executable was not created: $exePath"
}

if (-not $SkipValidation) {
    $selfTestReport = Join-Path $logRoot "exe_self_test_$timestamp.json"
    $startupSmokeReport = Join-Path $logRoot "exe_startup_smoke_$timestamp.json"

    Invoke-LoggedCommand `
        -Description "Run packaged self-test" `
        -Executable $exePath `
        -Arguments @("--self-test", "--storage-root", $validationRoot, "--report", $selfTestReport)

    Invoke-LoggedCommand `
        -Description "Run packaged startup smoke" `
        -Executable $exePath `
        -Arguments @("--startup-smoke", "--storage-root", $validationRoot, "--report", $startupSmokeReport)
}

$exeItem = Get-Item -LiteralPath $exePath
Write-Host ""
Write-Host "Build complete: $exePath"
Write-Host ("Size: {0:N2} MB" -f ($exeItem.Length / 1MB))
Write-Host "Log: $buildLog"
