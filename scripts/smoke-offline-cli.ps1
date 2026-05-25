param(
    [string]$Username = "alice",
    [string]$Password = "gayoj123"
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

function Write-Step {
    param([string]$Message)
    Write-Host "[offline-cli-smoke] $Message"
}

function Assert-True {
    param(
        [bool]$Condition,
        [string]$Message
    )
    if (-not $Condition) {
        throw "Offline CLI smoke assertion failed: $Message"
    }
}

function Set-EnvOrRemove {
    param(
        [string]$Name,
        [AllowNull()][string]$Value
    )
    if ($null -eq $Value) {
        Remove-Item -Path "Env:$Name" -ErrorAction SilentlyContinue
    } else {
        Set-Item -Path "Env:$Name" -Value $Value
    }
}

function Find-FreePort {
    $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Parse("127.0.0.1"), 0)
    try {
        $listener.Start()
        return [int]$listener.LocalEndpoint.Port
    } finally {
        $listener.Stop()
    }
}

$tempRoot = [System.IO.Path]::GetTempPath()
$tempDir = Join-Path $tempRoot ("gayoj-p5-06-" + [System.Guid]::NewGuid().ToString("N"))
$dbPath = Join-Path $tempDir "gayoj-offline-cli-smoke.sqlite3"
$apiOut = Join-Path $tempDir "api.out.log"
$apiErr = Join-Path $tempDir "api.err.log"
$packPath = Join-Path $tempDir "ps1001-pack.json"
$answersPath = Join-Path $tempDir "answers.json"
$resultsPath = Join-Path $tempDir "offline-results.json"
$cachePath = Join-Path $tempDir "offline-results.cache.json"
$apiProcess = $null

$oldEnv = @{
    GAYOJ_STORAGE_BACKEND = $env:GAYOJ_STORAGE_BACKEND
    GAYOJ_SQLITE_PATH = $env:GAYOJ_SQLITE_PATH
    GAYOJ_API_HOST = $env:GAYOJ_API_HOST
    GAYOJ_API_PORT = $env:GAYOJ_API_PORT
    GAYOJ_API_RELOAD = $env:GAYOJ_API_RELOAD
    GAYOJ_CLI_API_BASE = $env:GAYOJ_CLI_API_BASE
    GAYOJ_API_BASE = $env:GAYOJ_API_BASE
}

try {
    New-Item -ItemType Directory -Path $tempDir | Out-Null

    $port = Find-FreePort
    $baseUrl = "http://127.0.0.1:$port/api/v1"
    $healthUrl = "http://127.0.0.1:$port/api/v1/health"
    $cliPath = Join-Path (Get-Location) "tools/offline-cli/gayoj_offline.py"

    Set-EnvOrRemove -Name "GAYOJ_STORAGE_BACKEND" -Value "sqlite"
    Set-EnvOrRemove -Name "GAYOJ_SQLITE_PATH" -Value $dbPath
    Set-EnvOrRemove -Name "GAYOJ_API_HOST" -Value "127.0.0.1"
    Set-EnvOrRemove -Name "GAYOJ_API_PORT" -Value ([string]$port)
    Set-EnvOrRemove -Name "GAYOJ_API_RELOAD" -Value "false"
    Set-EnvOrRemove -Name "GAYOJ_CLI_API_BASE" -Value $baseUrl
    Set-EnvOrRemove -Name "GAYOJ_API_BASE" -Value $baseUrl

    Write-Step "starting temporary API on $baseUrl"
    $apiProcess = Start-Process -FilePath "py" -ArgumentList @(
        "-3.12",
        "-m",
        "uvicorn",
        "app.main:app",
        "--app-dir",
        "apps/api",
        "--host",
        "127.0.0.1",
        "--port",
        ([string]$port)
    ) -RedirectStandardOutput $apiOut -RedirectStandardError $apiErr -WindowStyle Hidden -PassThru

    $ready = $false
    for ($i = 0; $i -lt 80; $i++) {
        if ($apiProcess.HasExited) {
            $stderr = if (Test-Path -LiteralPath $apiErr) { Get-Content -Path $apiErr -Raw } else { "" }
            throw "temporary API exited early: $stderr"
        }
        try {
            $health = Invoke-RestMethod -Method GET -Uri $healthUrl -TimeoutSec 2
            if ($health.status -eq "ok") {
                $ready = $true
                break
            }
        } catch {
            Start-Sleep -Milliseconds 500
        }
    }
    Assert-True $ready "temporary API must become healthy"

    Write-Step "logging in through CLI"
    $token = ((& py -3.12 $cliPath login --api $baseUrl -u $Username -p $Password) | Select-Object -Last 1).Trim()
    Assert-True (-not [string]::IsNullOrWhiteSpace($token)) "CLI login must return a token"

    Write-Step "pulling PS1001 objective offline pack"
    $pullOutput = (& py -3.12 $cliPath pull-set PS1001 --api $baseUrl --token $token -o $packPath) -join "`n"
    Assert-True ($pullOutput -like "*Offline pack saved:*") "pull-set must print saved path"
    Assert-True ($pullOutput -like "*Pack summary:*") "pull-set must print a pack summary"
    Assert-True (Test-Path -LiteralPath $packPath) "pull-set must write pack file"

    Write-Step "inspecting pack"
    $inspectOutput = (& py -3.12 $cliPath inspect $packPath) -join "`n"
    Assert-True ($inspectOutput -like "*Problem types:*") "inspect must print problem type counts"

    Write-Step "generating answer file from authorized pack judge_config"
    $answerScript = @'
import json
import sys

pack_path, answers_path = sys.argv[1], sys.argv[2]
with open(pack_path, "r", encoding="utf-8-sig") as handle:
    pack = json.load(handle)

answers = {}
for problem in pack["payload"]["problems"]:
    config = problem.get("judge_config", {})
    if problem["type"] == "blank":
        answers[problem["id"]] = {
            key: (values[0] if isinstance(values, list) and values else "")
            for key, values in config.get("answers", {}).items()
        }
    elif problem["type"] == "single_choice":
        answers[problem["id"]] = config.get("answer", "")
    elif problem["type"] == "multiple_choice":
        answers[problem["id"]] = config.get("answer", [])
    else:
        raise SystemExit(f"unexpected non-objective problem: {problem['id']}")

with open(answers_path, "w", encoding="utf-8") as handle:
    json.dump({"answers": answers}, handle, ensure_ascii=False, indent=2)
print(len(answers))
'@
    $answerCountText = (($answerScript | py -3.12 - $packPath $answersPath) | Select-Object -Last 1).Trim()
    $answerCount = [int]$answerCountText
    Assert-True ($answerCount -gt 0) "answer file must include at least one objective problem"

    Write-Step "running non-interactive practice"
    $practiceOutput = (& py -3.12 $cliPath practice $packPath --answers $answersPath --cache $cachePath -o $resultsPath) -join "`n"
    Assert-True ($practiceOutput -like "*Practice summary:*") "practice must print summary"
    Assert-True ($practiceOutput -like "*Practice cache saved:*") "practice must write a local cache"
    Assert-True (Test-Path -LiteralPath $resultsPath) "practice must write results file"
    Assert-True (Test-Path -LiteralPath $cachePath) "practice must write cache file"

    Write-Step "resuming practice from local cache"
    $resumeOutput = (& py -3.12 $cliPath practice $packPath --answers $answersPath --cache $cachePath --resume -o $resultsPath) -join "`n"
    Assert-True ($resumeOutput -like "*Resuming cached practice:*") "resume must read local progress cache"
    Assert-True ($resumeOutput -like "*Skipping cached result:*") "resume must skip cached answers"

    Write-Step "syncing results to API"
    $syncOutput = (& py -3.12 $cliPath sync-results $resultsPath --api $baseUrl --token $token --fail-on-rejected) -join "`n"
    Assert-True ($syncOutput -like "*Sync summary:*") "sync-results must print summary"
    Assert-True ($syncOutput -like "*synced=$answerCount*") "first sync must create all local objective results"
    Assert-True ($syncOutput -like "*rejected=0*") "first sync must not reject results"

    Write-Step "syncing again to verify merged duplicates"
    $secondSyncOutput = (& py -3.12 $cliPath sync-results $resultsPath --api $baseUrl --token $token --fail-on-rejected) -join "`n"
    Assert-True ($secondSyncOutput -like "*synced=0*") "second sync must not create duplicate submissions"
    Assert-True ($secondSyncOutput -like "*merged=$answerCount*") "second sync must merge duplicate local results"
    Assert-True ($secondSyncOutput -like "*rejected=0*") "second sync must not reject results"

    Write-Host ""
    Write-Host "Offline CLI smoke passed with temporary SQLite store $dbPath"
}
finally {
    if ($apiProcess -and -not $apiProcess.HasExited) {
        Stop-Process -Id $apiProcess.Id -Force
        $apiProcess.WaitForExit(5000) | Out-Null
    }

    foreach ($key in $oldEnv.Keys) {
        Set-EnvOrRemove -Name $key -Value $oldEnv[$key]
    }

    $resolvedTempRoot = [System.IO.Path]::GetFullPath($tempRoot)
    $resolvedTempDir = [System.IO.Path]::GetFullPath($tempDir)
    if ($resolvedTempDir.StartsWith($resolvedTempRoot, [System.StringComparison]::OrdinalIgnoreCase) -and
        (Test-Path -LiteralPath $resolvedTempDir)) {
        Remove-Item -LiteralPath $resolvedTempDir -Recurse -Force
    }
}
