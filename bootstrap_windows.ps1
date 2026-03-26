param(
    [switch]$RunApp,
    [switch]$SkipSystem
)

$ErrorActionPreference = "Stop"

function Test-CommandExists {
    param([Parameter(Mandatory = $true)][string]$Name)
    return $null -ne (Get-Command $Name -ErrorAction SilentlyContinue)
}

function Get-PythonCommand {
    if (Test-CommandExists -Name "py") {
        return @{
            Exe = "py"
            PrefixArgs = @("-3")
        }
    }
    if (Test-CommandExists -Name "python") {
        return @{
            Exe = "python"
            PrefixArgs = @()
        }
    }
    return $null
}

function Install-Python {
    if (Test-CommandExists -Name "winget") {
        Write-Host "Installing Python via winget..."
        & winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
        return
    }

    if (Test-CommandExists -Name "choco") {
        Write-Host "Installing Python via Chocolatey..."
        & choco install python -y
        return
    }

    throw "Could not install Python automatically. Install Python 3.10+ and re-run this script."
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

$pythonCmd = Get-PythonCommand
if (-not $pythonCmd) {
    Install-Python
    $pythonCmd = Get-PythonCommand
}

if (-not $pythonCmd) {
    throw "Python still not found after installation attempt. Restart terminal and run script again."
}

$argsList = @("install.py")
if ($RunApp) {
    $argsList += "--run-app"
}
if ($SkipSystem) {
    $argsList += "--skip-system"
}

$allArgs = @($pythonCmd.PrefixArgs + $argsList)
Write-Host "Running installer with: $($pythonCmd.Exe) $($allArgs -join ' ')"
& $pythonCmd.Exe @allArgs
