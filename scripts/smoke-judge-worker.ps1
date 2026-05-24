param()

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

function Write-Step {
    param([string]$Message)
    Write-Host "[judge-worker-smoke] $Message"
}

function Assert-True {
    param(
        [bool]$Condition,
        [string]$Message
    )
    if (-not $Condition) {
        throw "Judge worker smoke assertion failed: $Message"
    }
}

$tempRoot = [System.IO.Path]::GetTempPath()
$tempDir = Join-Path $tempRoot ("gayoj-p4-02-" + [System.Guid]::NewGuid().ToString("N"))
$dbPath = Join-Path $tempDir "dev-db.json"
New-Item -ItemType Directory -Path $tempDir | Out-Null

try {
    Write-Step "preparing temporary JSON store with one queued code submission"
    $prepareScript = @'
from pathlib import Path
import sys

root = Path.cwd()
sys.path.insert(0, str(root / "apps" / "api"))

from app.db import JsonRepository, now
from app.models import Submission
from app.services import make_submission_id

repository = JsonRepository(Path(sys.argv[1]))
submission = Submission(
    id=make_submission_id(),
    user_id="u-student",
    problem_id="P1001",
    problem_title="A+B Problem",
    problem_type="code",
    language="python",
    source_code="raise SystemExit('judge worker smoke source must not execute')\n",
    status="queued",
    score=0,
    max_score=100,
    details=[],
    message="queued for P4-02 smoke",
    created_at=now(),
)
repository.add_submission(submission)
print(submission.id)
'@
    $submissionId = (($prepareScript | py -3.12 - $dbPath) | Select-Object -Last 1).Trim()
    Assert-True (-not [string]::IsNullOrWhiteSpace($submissionId)) "temporary submission id must be created"

    Write-Step "claiming the queued task through the judge worker CLI"
    $resultText = py -3.12 apps/judge/worker.py --storage $dbPath --worker-id smoke-worker --languages python --once --json
    $result = $resultText | ConvertFrom-Json
    Assert-True ($result.event -eq "claimed") "worker must claim a queued task"
    Assert-True ($result.worker_id -eq "smoke-worker") "worker id must be preserved"
    Assert-True ($result.task.submission_id -eq $submissionId) "worker must claim the prepared submission"
    Assert-True ($result.task.source_ref -eq "submission:$($submissionId):source") "task must carry a redacted source reference only"
    Assert-True ($result.boundary -eq "claim_only_no_execution") "worker smoke must stay claim-only"
    Assert-True (-not ($resultText -like "*source_code*")) "worker must not echo the source storage field name"
    Assert-True (-not ($resultText -like "*judge worker smoke source must not execute*")) "worker must not execute or echo source"

    Write-Step "verifying stored submission was only marked judging"
    $verifyScript = @'
from pathlib import Path
import sys

root = Path.cwd()
sys.path.insert(0, str(root / "apps" / "api"))

from app.db import JsonRepository

repository = JsonRepository(Path(sys.argv[1]))
submission = repository.get_submission(sys.argv[2])
assert submission is not None
assert submission.status == "judging"
assert submission.score == 0
assert submission.judged_at is None
assert submission.details == []
assert "smoke-worker" in submission.message
print("ok")
'@
    $verifyOutput = (($verifyScript | py -3.12 - $dbPath $submissionId) | Select-Object -Last 1).Trim()
    Assert-True ($verifyOutput -eq "ok") "claimed submission must remain unjudged"

    Write-Host ""
    Write-Host "Judge worker smoke passed with temporary store $dbPath"
}
finally {
    $resolvedTempRoot = [System.IO.Path]::GetFullPath($tempRoot)
    $resolvedTempDir = [System.IO.Path]::GetFullPath($tempDir)
    if ((Test-Path -LiteralPath $tempDir) -and $resolvedTempDir.StartsWith($resolvedTempRoot)) {
        Remove-Item -LiteralPath $tempDir -Recurse -Force
    }
}
