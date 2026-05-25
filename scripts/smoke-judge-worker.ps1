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
$dbPath = Join-Path $tempDir "gayoj-smoke.sqlite3"
New-Item -ItemType Directory -Path $tempDir | Out-Null

try {
    Write-Step "preparing temporary SQLite store with one queued code submission"
    $prepareScript = @'
from pathlib import Path
import sys

root = Path.cwd()
sys.path.insert(0, str(root / "apps" / "api"))

from app.db import SnapshotRepository, now
from app.models import Submission
from app.services import make_submission_id

repository = SnapshotRepository.sqlite(Path(sys.argv[1]))
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

from app.db import SnapshotRepository

repository = SnapshotRepository.sqlite(Path(sys.argv[1]))
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

    Write-Step "running execute_once through an injected sandbox executor"
    $executeScript = @'
from pathlib import Path
import json
import sys

root = Path.cwd()
sys.path.insert(0, str(root / "apps" / "api"))
sys.path.insert(0, str(root / "apps" / "judge"))

from app.db import SnapshotRepository, now
from app.models import Submission
from app.services import make_submission_id
from gayoj_judge import CompileOutcome, RunOutcome
from worker import JudgeWorker

class SmokeExecutor:
    def __init__(self):
        self.runs = []
        self.cleaned = False

    def compile(self, task):
        return CompileOutcome(ok=True, artifact={"submission_id": task.submission_id})

    def run(self, task, artifact, test_case):
        self.runs.append(test_case.id)
        return RunOutcome(status="accepted", stdout=test_case.expected_output, time_ms=5, memory_kb=512)

    def cleanup(self, artifact):
        self.cleaned = True

repository = SnapshotRepository.sqlite(Path(sys.argv[1]))
submission = Submission(
    id=make_submission_id(),
    user_id="u-student",
    problem_id="P1001",
    problem_title="A+B Problem",
    problem_type="code",
    language="python",
    source_code="raise SystemExit('execute smoke must use injected sandbox only')\n",
    status="queued",
    score=0,
    max_score=100,
    details=[],
    message="queued for P4 execute smoke",
    created_at=now(),
)
repository.add_submission(submission)
worker = JudgeWorker(repository, worker_id="execute-smoke-worker", name="execute smoke worker", languages=["python"])
executor = SmokeExecutor()
event = worker.execute_once(executor)
stored = repository.get_submission(submission.id)
job = repository.get_judge_queue_job(stored.queue_job_id)
print(json.dumps({
    "event": event,
    "submission_id": submission.id,
    "status": stored.status,
    "score": stored.score,
    "max_score": stored.max_score,
    "details": stored.details,
    "job_status": job.status,
    "runs": executor.runs,
    "cleaned": executor.cleaned,
}, ensure_ascii=False))
'@
    $executeText = (($executeScript | py -3.12 - $dbPath) | Select-Object -Last 1)
    $executeResult = $executeText | ConvertFrom-Json
    Assert-True ($executeResult.event.event -eq "judged") "execute_once must judge the claimed task"
    Assert-True ($executeResult.event.boundary -eq "worker_sandbox_execution") "execute_once must report worker sandbox boundary"
    Assert-True ($executeResult.status -eq "accepted") "execute_once must write back the final result"
    Assert-True ($executeResult.score -eq $executeResult.max_score) "accepted smoke result must receive full score"
    Assert-True ($executeResult.job_status -eq "completed") "execute_once must complete the queue job"
    Assert-True ($executeResult.cleaned -eq $true) "execute_once must call sandbox cleanup"
    Assert-True (@($executeResult.runs).Count -eq 2) "execute_once must run both seeded sample test points"
    Assert-True (-not ($executeText -like "*execute smoke must use injected sandbox only*")) "execute smoke must not echo source"
    foreach ($detail in @($executeResult.details)) {
        Assert-True (-not (Get-Member -InputObject $detail -Name "input_preview" -MemberType NoteProperty)) "details must not expose hidden input preview"
        Assert-True (-not (Get-Member -InputObject $detail -Name "expected_preview" -MemberType NoteProperty)) "details must not expose expected output preview"
    }

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
