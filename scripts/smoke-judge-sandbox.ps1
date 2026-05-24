param(
    [switch]$RunDocker
)

$ErrorActionPreference = "Stop"

function Assert-True {
    param(
        [bool]$Condition,
        [string]$Message
    )
    if (-not $Condition) {
        throw $Message
    }
}

$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$oldPythonPath = $env:PYTHONPATH
$judgePath = Join-Path $root "apps\judge"
if ([string]::IsNullOrWhiteSpace($oldPythonPath)) {
    $env:PYTHONPATH = $judgePath
} else {
    $env:PYTHONPATH = "$judgePath$([IO.Path]::PathSeparator)$oldPythonPath"
}

try {
    Write-Host "[judge-sandbox] dry-run command contract"
    $dryRunText = py -3.12 -m gayoj_judge --language python --time-limit-ms 750 --memory-limit-mb 64 --dry-run
    if ($LASTEXITCODE -ne 0) {
        throw "gayoj_judge dry-run failed"
    }
    $dryRun = $dryRunText | ConvertFrom-Json
    $runCommandText = [string]::Join(" ", @($dryRun.run_command))

    Assert-True ($runCommandText.Contains("--network none")) "Docker sandbox must disable networking"
    Assert-True ($runCommandText.Contains("--memory 64m")) "Docker sandbox must set memory limit"
    Assert-True ($runCommandText.Contains("--memory-swap 64m")) "Docker sandbox must pin memory swap to memory limit"
    Assert-True ($runCommandText.Contains("--pids-limit 64")) "Docker sandbox must limit processes"
    Assert-True ($runCommandText.Contains("--read-only")) "Docker sandbox root filesystem must be read-only"
    Assert-True ($runCommandText.Contains("--cap-drop ALL")) "Docker sandbox must drop Linux capabilities"
    Assert-True ($runCommandText.Contains("--security-opt no-new-privileges")) "Docker sandbox must forbid new privileges"
    Assert-True ($runCommandText.Contains("timeout --signal=KILL 1s")) "Docker sandbox must enforce runtime timeout"

    if ($RunDocker -or $env:GAYOJ_JUDGE_RUN_DOCKER_SMOKE -eq "1") {
        if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
            throw "Docker smoke was requested, but docker is not available on PATH"
        }
        Write-Host "[judge-sandbox] running Docker smoke"
        $source = New-TemporaryFile
        try {
            @'
import sys

for line in sys.stdin:
    a, b = map(int, line.split())
    print(a + b)
'@ | Set-Content -Encoding UTF8 -NoNewline $source
            $resultText = py -3.12 -m gayoj_judge --language python --source-file $source --stdin "1 2`n"
            if ($LASTEXITCODE -ne 0) {
                throw "gayoj_judge Docker smoke failed: $resultText"
            }
            $result = $resultText | ConvertFrom-Json
            Assert-True ($result.verdict -eq "ok") "Docker smoke verdict must be ok"
            Assert-True ($result.stdout.Trim() -eq "3") "Docker smoke output must match expected answer"
        } finally {
            Remove-Item -LiteralPath $source -Force -ErrorAction SilentlyContinue
        }
    } else {
        Write-Host "[judge-sandbox] Docker execution skipped; set GAYOJ_JUDGE_RUN_DOCKER_SMOKE=1 or pass -RunDocker to run it"
    }
} finally {
    $env:PYTHONPATH = $oldPythonPath
}
