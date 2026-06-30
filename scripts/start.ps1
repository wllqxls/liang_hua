$ErrorActionPreference = "Stop"

& "$PSScriptRoot\setup_terminal.ps1"

$python = Join-Path $PSScriptRoot "..\venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    $python = "python"
}

& $python main.py
