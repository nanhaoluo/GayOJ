param(
    [string]$EnvFile = ".env"
)

$ErrorActionPreference = "Stop"

$envPath = Join-Path (Get-Location) $EnvFile
if (Test-Path -LiteralPath $envPath) {
    . (Join-Path $PSScriptRoot "load-env.ps1") -Path $envPath -Quiet
}

$hostName = if ($env:GAYOJ_API_HOST) { $env:GAYOJ_API_HOST } else { "127.0.0.1" }
$port = if ($env:GAYOJ_API_PORT) { $env:GAYOJ_API_PORT } else { "8000" }
$reload = if ($env:GAYOJ_API_RELOAD) { $env:GAYOJ_API_RELOAD } else { "true" }

$arguments = @(
    "-3.12",
    "-m",
    "uvicorn",
    "app.main:app",
    "--app-dir",
    "apps/api",
    "--host",
    $hostName,
    "--port",
    $port
)

if ($reload.ToLowerInvariant() -ne "false") {
    $arguments += "--reload"
}

& py @arguments
