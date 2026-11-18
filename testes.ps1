# Roda lint e testes do backend, incluindo os de integração, no banco LOCAL odonto_test.
#
#   .\testes.ps1                      tudo
#   .\testes.ps1 tests/test_unit.py   argumentos repassados ao pytest
#
# ATENÇÃO: o banco odonto_test é APAGADO e recriado a cada execução. Nunca aponte para o
# banco de dev (odonto). Como criar o odonto_test: README, seção "Testando localmente".
$ErrorActionPreference = "Stop"
$backend = Join-Path $PSScriptRoot "backend"
. (Join-Path $backend ".venv\Scripts\Activate.ps1")
Push-Location $backend
try {
    $env:TEST_DATABASE_URL = "postgresql+psycopg://odonto_app:odonto_app@localhost:5432/odonto_test"
    $env:TEST_MIGRATIONS_DATABASE_URL = "postgresql+psycopg://odonto:odonto@localhost:5432/odonto_test"
    ruff check .
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    ruff format --check .
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    pytest -q @args
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
