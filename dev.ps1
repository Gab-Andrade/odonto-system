# Sobe o backend para testes locais (Windows, sem Docker).
#
#   .\dev.ps1            migra o banco de dev e sobe a API em http://localhost:8000/docs
#   .\dev.ps1 -Demo      idem, criando antes os dados de demonstração (idempotente)
#   .\dev.ps1 -Front     sobe também o frontend (npm run dev) em outra janela
#
# Requer backend/.venv (python -m venv .venv; pip install -e ".[dev]") e backend/.env.
param(
    [switch]$Demo,
    [switch]$Front,
    [string]$Slug = "teste"
)

$ErrorActionPreference = "Stop"
$backend = Join-Path $PSScriptRoot "backend"
$activate = Join-Path $backend ".venv\Scripts\Activate.ps1"
if (-not (Test-Path $activate)) {
    Write-Error "Venv não encontrada em backend\.venv. Crie com: py -m venv backend\.venv; backend\.venv\Scripts\pip install -e `"backend[dev]`""
}
if (-not (Test-Path (Join-Path $backend ".env"))) {
    Write-Error "Falta backend\.env. Copie de backend\.env.example e ajuste."
}

. $activate
Push-Location $backend
try {
    alembic upgrade head
    if ($LASTEXITCODE -ne 0) { throw "alembic upgrade head falhou" }

    if ($Demo) {
        python -m app.cli demo --slug $Slug
        if ($LASTEXITCODE -ne 0) { throw "falha ao criar os dados de demonstração" }
    }

    if ($Front) {
        $frontend = Join-Path $PSScriptRoot "frontend"
        $npm = "npm"
        if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
            $npm = "C:\Program Files\nodejs\npm.cmd"
        }
        Start-Process powershell -WorkingDirectory $frontend -ArgumentList "-NoExit", "-Command", "& '$npm' run dev"
    }

    Write-Host "API: http://localhost:8000/docs  (Ctrl+C para parar)"
    uvicorn app.main:app --reload
}
finally {
    Pop-Location
}
