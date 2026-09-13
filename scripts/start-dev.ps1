<#
.SYNOPSIS
    Starts the MeetingAI backend and frontend for local development.

.DESCRIPTION
    Creates the Python virtual environment on first run, installs backend and
    frontend dependencies if they are missing, then opens the FastAPI server and
    the Vite dev server in two separate PowerShell windows.

.PARAMETER SkipInstall
    Skip the dependency installation checks and start the servers straight away.

.PARAMETER BackendOnly
    Start only the FastAPI backend.

.PARAMETER FrontendOnly
    Start only the Vite dev server.

.EXAMPLE
    .\scripts\start-dev.ps1

.EXAMPLE
    .\scripts\start-dev.ps1 -SkipInstall
#>

[CmdletBinding()]
param(
    [switch]$SkipInstall,
    [switch]$BackendOnly,
    [switch]$FrontendOnly
)

$ErrorActionPreference = 'Stop'

$RepoRoot    = Split-Path -Parent $PSScriptRoot
$BackendDir  = Join-Path $RepoRoot 'backend'
$FrontendDir = Join-Path $RepoRoot 'frontend'
$VenvPython  = Join-Path $BackendDir '.venv\Scripts\python.exe'

function Write-Step($message) {
    Write-Host ''
    Write-Host "==> $message" -ForegroundColor Cyan
}

function Write-Warn($message) {
    Write-Host "    ! $message" -ForegroundColor Yellow
}

# --- Backend dependencies -------------------------------------------------

if (-not $FrontendOnly -and -not $SkipInstall) {
    if (-not (Test-Path $VenvPython)) {
        Write-Step 'Creating the Python virtual environment'

        # faster-whisper, chromadb and sentence-transformers need Python 3.11 or 3.12.
        $python = 'python'
        try {
            $available = & py -0p 2>$null
            if ($available -match '3\.12') { $python = 'py -3.12' }
            elseif ($available -match '3\.11') { $python = 'py -3.11' }
        } catch {
            # `py` is not installed; fall back to whatever `python` resolves to.
        }

        Write-Host "    Using $python"
        Invoke-Expression "$python -m venv `"$(Join-Path $BackendDir '.venv')`""
    }

    Write-Step 'Installing backend dependencies'
    & $VenvPython -m pip install --upgrade pip --quiet
    & $VenvPython -m pip install -r (Join-Path $BackendDir 'requirements.txt') --quiet
}

# --- Frontend dependencies ------------------------------------------------

if (-not $BackendOnly -and -not $SkipInstall) {
    if (-not (Test-Path (Join-Path $FrontendDir 'node_modules'))) {
        Write-Step 'Installing frontend dependencies'
        Push-Location $FrontendDir
        try { npm install } finally { Pop-Location }
    }
}

# --- Optional dependency check -------------------------------------------

Write-Step 'Checking optional local AI services'

try {
    Invoke-RestMethod -Uri 'http://localhost:11434/api/tags' -TimeoutSec 3 | Out-Null
    Write-Host '    Ollama is running.' -ForegroundColor Green
} catch {
    Write-Warn 'Ollama is not reachable at http://localhost:11434'
    Write-Warn 'Summaries and chat will fail until it is running. Install it from https://ollama.com/download'
    Write-Warn 'Then run:  ollama pull llama3.2'
}

# --- Start the servers ----------------------------------------------------

if (-not $FrontendOnly) {
    Write-Step 'Starting the backend on http://localhost:8000'
    Start-Process powershell -ArgumentList @(
        '-NoExit', '-Command',
        "Set-Location '$BackendDir'; & '.\.venv\Scripts\Activate.ps1'; uvicorn app.main:app --reload --port 8000"
    )
}

if (-not $BackendOnly) {
    Write-Step 'Starting the frontend on http://localhost:5173'
    Start-Process powershell -ArgumentList @(
        '-NoExit', '-Command',
        "Set-Location '$FrontendDir'; npm run dev"
    )
}

Write-Host ''
Write-Host 'MeetingAI is starting up.' -ForegroundColor Green
Write-Host '  Frontend : http://localhost:5173'
Write-Host '  Backend  : http://localhost:8000'
Write-Host '  API docs : http://localhost:8000/docs'
Write-Host '  Health   : http://localhost:8000/health'
Write-Host ''
Write-Host 'Close the two new PowerShell windows to stop the servers.'
