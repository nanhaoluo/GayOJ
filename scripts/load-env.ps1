param(
    [string]$Path = ".env",
    [switch]$Override,
    [switch]$Quiet
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $Path)) {
    if (-not $Quiet) {
        Write-Host "Environment file not found: $Path"
    }
    return
}

$loaded = 0
foreach ($line in Get-Content -LiteralPath $Path) {
    $trimmed = $line.Trim()
    if (-not $trimmed -or $trimmed.StartsWith("#")) {
        continue
    }

    $separator = $trimmed.IndexOf("=")
    if ($separator -le 0) {
        continue
    }

    $key = $trimmed.Substring(0, $separator).Trim()
    $value = $trimmed.Substring($separator + 1).Trim()
    if (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'"))) {
        $value = $value.Substring(1, $value.Length - 2)
    }

    if (-not $Override -and [Environment]::GetEnvironmentVariable($key, "Process")) {
        continue
    }

    Set-Item -Path "Env:$key" -Value $value
    $loaded += 1
}

if (-not $Quiet) {
    Write-Host "Loaded $loaded environment values from $Path"
}
