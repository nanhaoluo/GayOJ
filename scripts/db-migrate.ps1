param(
    [string]$DatabaseUrl = "",
    [string]$MigrationsPath = "migrations/versions",
    [string]$Psql = "psql"
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($DatabaseUrl)) {
    $DatabaseUrl = $env:GAYOJ_DATABASE_URL
}

if ([string]::IsNullOrWhiteSpace($DatabaseUrl)) {
    throw "GAYOJ_DATABASE_URL is required. Example: postgresql://gayoj:gayoj@127.0.0.1:5432/gayoj"
}

$root = Get-Location
$migrationRoot = Join-Path $root $MigrationsPath
if (-not (Test-Path -LiteralPath $migrationRoot)) {
    throw "Migration directory not found: $migrationRoot"
}

$files = @(Get-ChildItem -LiteralPath $migrationRoot -Filter "*.sql" | Sort-Object Name)
if ($files.Count -eq 0) {
    throw "No migration files found in $migrationRoot"
}

foreach ($file in $files) {
    Write-Host "[db-migrate] applying $($file.Name)"
    & $Psql $DatabaseUrl -v "ON_ERROR_STOP=1" -f $file.FullName
    if ($LASTEXITCODE -ne 0) {
        throw "Migration failed: $($file.FullName)"
    }
}

Write-Host "[db-migrate] applied $($files.Count) migration(s)"
