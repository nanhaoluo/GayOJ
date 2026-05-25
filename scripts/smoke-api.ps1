param(
    [string]$BaseUrl = "",
    [string]$HealthUrl = "",
    [string]$Username = "alice",
    [string]$Password = "gayoj123",
    [string]$AdminUsername = "admin",
    [string]$AdminPassword = "gayoj123",
    [string]$JudgeNodeToken = "",
    [string]$EnvFile = ".env"
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$envPath = Join-Path (Get-Location) $EnvFile
if (Test-Path -LiteralPath $envPath) {
    . (Join-Path $PSScriptRoot "load-env.ps1") -Path $envPath -Quiet
}

if ([string]::IsNullOrWhiteSpace($BaseUrl)) {
    $BaseUrl = $env:GAYOJ_API_BASE
}
if ([string]::IsNullOrWhiteSpace($BaseUrl)) {
    $BaseUrl = "http://127.0.0.1:8000/api/v1"
}
$BaseUrl = $BaseUrl.TrimEnd("/")

if ([string]::IsNullOrWhiteSpace($HealthUrl)) {
    $HealthUrl = $env:GAYOJ_HEALTH_URL
}
if ([string]::IsNullOrWhiteSpace($HealthUrl)) {
    $HealthUrl = "http://127.0.0.1:8000/health"
}
if ([string]::IsNullOrWhiteSpace($JudgeNodeToken)) {
    $JudgeNodeToken = $env:GAYOJ_JUDGE_NODE_TOKEN
}
if ([string]::IsNullOrWhiteSpace($JudgeNodeToken)) {
    $JudgeNodeToken = "gayoj-dev-judge-node-token"
}

function Write-Step {
    param([string]$Message)
    Write-Host "[smoke] $Message"
}

function Assert-True {
    param(
        [bool]$Condition,
        [string]$Message
    )
    if (-not $Condition) {
        throw "Smoke assertion failed: $Message"
    }
}

function Has-Property {
    param(
        [object]$Value,
        [string]$Name
    )
    return $null -ne $Value -and ($Value.PSObject.Properties.Name -contains $Name)
}

function ConvertTo-ItemArray {
    param([object]$Value)

    $items = @()
    if ($null -eq $Value) {
        return $items
    }
    if ($Value -is [System.Array]) {
        foreach ($item in $Value) {
            if ($item -is [System.Array]) {
                foreach ($nested in $item) {
                    $items += $nested
                }
            } else {
                $items += $item
            }
        }
        return $items
    }
    return @($Value)
}

function Invoke-ApiJson {
    param(
        [ValidateSet("GET", "POST", "PATCH", "PUT", "DELETE")]
        [string]$Method,
        [string]$Path,
        [object]$Body = $null,
        [string]$Token = "",
        [hashtable]$ExtraHeaders = @{}
    )

    $headers = @{}
    if (-not [string]::IsNullOrWhiteSpace($Token)) {
        $headers["Authorization"] = "Bearer $Token"
    }
    foreach ($key in $ExtraHeaders.Keys) {
        $headers[$key] = $ExtraHeaders[$key]
    }

    $uri = "$BaseUrl$Path"
    $parameters = @{
        Method = $Method
        Uri = $uri
        Headers = $headers
        TimeoutSec = 15
    }
    if ($null -ne $Body) {
        $parameters["ContentType"] = "application/json; charset=utf-8"
        $parameters["Body"] = ($Body | ConvertTo-Json -Depth 20)
    }

    try {
        $response = Invoke-WebRequest @parameters -UseBasicParsing
        if ([string]::IsNullOrWhiteSpace($response.Content)) {
            return $null
        }
        return $response.Content | ConvertFrom-Json
    } catch {
        $detail = $_.Exception.Message
        if ($_.ErrorDetails -and $_.ErrorDetails.Message) {
            $detail = $_.ErrorDetails.Message
        }
        throw "$Method $uri failed: $detail"
    }
}

function Invoke-ApiFailure {
    param(
        [ValidateSet("GET", "POST", "PATCH", "PUT", "DELETE")]
        [string]$Method,
        [string]$Path,
        [int]$ExpectedStatus,
        [object]$Body = $null,
        [string]$Token = ""
    )

    $headers = @{}
    if (-not [string]::IsNullOrWhiteSpace($Token)) {
        $headers["Authorization"] = "Bearer $Token"
    }

    $uri = "$BaseUrl$Path"
    $parameters = @{
        Method = $Method
        Uri = $uri
        Headers = $headers
        TimeoutSec = 15
    }
    if ($null -ne $Body) {
        $parameters["ContentType"] = "application/json; charset=utf-8"
        $parameters["Body"] = ($Body | ConvertTo-Json -Depth 20)
    }

    try {
        Invoke-WebRequest @parameters -UseBasicParsing | Out-Null
    } catch {
        $statusCode = $null
        if ($_.Exception.Response -and $_.Exception.Response.StatusCode) {
            $statusCode = [int]$_.Exception.Response.StatusCode
        }
        Assert-True ($statusCode -eq $ExpectedStatus) "$Method $uri must fail with HTTP $ExpectedStatus"
        return
    }
    throw "Smoke assertion failed: $Method $uri must fail with HTTP $ExpectedStatus"
}

function Invoke-ApiMultipartUpload {
    param(
        [string]$Path,
        [string]$FilePath,
        [string]$Token = ""
    )

    Add-Type -AssemblyName System.Net.Http
    $client = [System.Net.Http.HttpClient]::new()
    $form = [System.Net.Http.MultipartFormDataContent]::new()
    $fileContent = $null
    try {
        if (-not [string]::IsNullOrWhiteSpace($Token)) {
            $client.DefaultRequestHeaders.Authorization = [System.Net.Http.Headers.AuthenticationHeaderValue]::new("Bearer", $Token)
        }
        $bytes = [System.IO.File]::ReadAllBytes($FilePath)
        $fileContent = [System.Net.Http.ByteArrayContent]::new($bytes)
        $fileContent.Headers.ContentType = [System.Net.Http.Headers.MediaTypeHeaderValue]::Parse("application/zip")
        $form.Add($fileContent, "file", [System.IO.Path]::GetFileName($FilePath))
        $response = $client.PostAsync("$BaseUrl$Path", $form).GetAwaiter().GetResult()
        $text = $response.Content.ReadAsStringAsync().GetAwaiter().GetResult()
        if (-not $response.IsSuccessStatusCode) {
            throw "POST $BaseUrl$Path failed: HTTP $([int]$response.StatusCode) $text"
        }
        return $text | ConvertFrom-Json
    } finally {
        if ($fileContent) {
            $fileContent.Dispose()
        }
        $form.Dispose()
        $client.Dispose()
    }
}

function Invoke-ApiDownload {
    param(
        [string]$Path,
        [string]$OutputPath,
        [string]$Token = ""
    )

    $headers = @{}
    if (-not [string]::IsNullOrWhiteSpace($Token)) {
        $headers["Authorization"] = "Bearer $Token"
    }
    Invoke-WebRequest -UseBasicParsing -Method GET -Uri "$BaseUrl$Path" -Headers $headers -TimeoutSec 15 -OutFile $OutputPath
}

Write-Step "checking health endpoint"
$health = Invoke-RestMethod -Method GET -Uri $HealthUrl -TimeoutSec 15
Assert-True ($health.status -eq "ok") "health endpoint must return status=ok"

Write-Step "logging in as $Username"
$login = Invoke-ApiJson -Method POST -Path "/auth/login" -Body @{
    username = $Username
    password = $Password
}
Assert-True (-not [string]::IsNullOrWhiteSpace($login.access_token)) "login must return access_token"
Assert-True ($login.user.username -eq $Username) "login user must match requested username"
$token = [string]$login.access_token

Write-Step "checking current user"
$me = Invoke-ApiJson -Method GET -Path "/auth/me" -Token $token
Assert-True ($me.username -eq $Username) "auth/me must return the logged-in user"
Assert-True (-not (Has-Property -Value $me -Name "email")) "auth/me must not expose private email"

Write-Step "checking profile settings update"
$profile = Invoke-ApiJson -Method GET -Path "/users/me/profile" -Token $token
Assert-True ($profile.username -eq $Username) "profile endpoint must return the logged-in user"
Assert-True (Has-Property -Value $profile -Name "email") "profile endpoint must include private email"
$originalProfile = @{
    display_name = [string]$profile.display_name
    school = [string]$profile.school
    email = [string]$profile.email
}
$updatedProfileName = "$($originalProfile.display_name) Smoke"
try {
    $updatedProfile = Invoke-ApiJson -Method PATCH -Path "/users/me/profile" -Token $token -Body @{
        display_name = $updatedProfileName
        school = $originalProfile.school
        email = $originalProfile.email
    }
    Assert-True ($updatedProfile.display_name -eq $updatedProfileName) "profile update must persist display_name"
    $meAfterProfileUpdate = Invoke-ApiJson -Method GET -Path "/auth/me" -Token $token
    Assert-True ($meAfterProfileUpdate.display_name -eq $updatedProfileName) "auth/me must reflect updated display_name"
} finally {
    Invoke-ApiJson -Method PATCH -Path "/users/me/profile" -Token $token -Body $originalProfile | Out-Null
}

Write-Step "checking problem list"
$problems = @(ConvertTo-ItemArray -Value (Invoke-ApiJson -Method GET -Path "/problems"))
Assert-True ($problems.Count -ge 4) "problem list must contain seeded problems"
$problemById = @{}
foreach ($problem in $problems) {
    $problemById[$problem.id] = $problem
}
Assert-True ($problemById.ContainsKey("P1001")) "problem list must contain code problem P1001"
Assert-True ($problemById.ContainsKey("P1002")) "problem list must contain blank problem P1002"
Assert-True ($problemById.ContainsKey("P1003")) "problem list must contain single choice problem P1003"
Assert-True ($problemById.ContainsKey("P1004")) "problem list must contain multiple choice problem P1004"

Write-Step "checking tag hierarchy and multi-tag problem filters"
$tagTree = @(ConvertTo-ItemArray -Value (Invoke-ApiJson -Method GET -Path "/tags"))
Assert-True ($tagTree.Count -gt 0) "tag tree endpoint must return knowledge tags"
$tagIds = @($tagTree | ForEach-Object { $_.id })
Assert-True ($tagIds -contains "TAG1001") "tag tree must include seeded algorithm root"
$tagCombinatorics = -join ([char[]](0x7EC4, 0x5408, 0x6570, 0x5B66))
$tagGraph = -join ([char[]](0x56FE, 0x8BBA))
$tagSystemSecurity = -join ([char[]](0x7CFB, 0x7EDF, 0x5B89, 0x5168))
$tagOnlineJudge = -join ([char[]](0x5728, 0x7EBF, 0x8BC4, 0x6D4B))
$comboPath = "/problems?tag=$([uri]::EscapeDataString($tagCombinatorics))&tag=$([uri]::EscapeDataString($tagGraph))"
$comboProblems = @(ConvertTo-ItemArray -Value (Invoke-ApiJson -Method GET -Path $comboPath))
Assert-True ($comboProblems.Count -eq 1) "multi-tag AND filter must narrow to one seeded problem"
Assert-True ($comboProblems[0].id -eq "P1002") "multi-tag filter for 组合数学+图论 must return P1002"
$securityTags = "$tagSystemSecurity,$tagOnlineJudge"
$securityPath = "/problems?tags=$([uri]::EscapeDataString($securityTags))"
$securityProblems = @(ConvertTo-ItemArray -Value (Invoke-ApiJson -Method GET -Path $securityPath))
Assert-True ($securityProblems.Count -eq 1) "comma separated tags filter must work"
Assert-True ($securityProblems[0].id -eq "P1004") "security tag filter must return P1004"

Write-Step "checking public problem detail does not expose judge_config"
$publicBlank = Invoke-ApiJson -Method GET -Path "/problems/P1002"
Assert-True ($publicBlank.type -eq "blank") "P1002 must be a blank problem"
Assert-True (-not (Has-Property -Value $publicBlank -Name "judge_config")) "public problem detail must not include judge_config"

Write-Step "submitting objective answer"
$objectiveSubmission = Invoke-ApiJson -Method POST -Path "/problems/P1003/submit-objective" -Token $token -Body @{
    answers = @{
        choice = "B"
    }
}
Assert-True ($objectiveSubmission.problem_type -eq "single_choice") "objective submission must target single_choice problem"
Assert-True ($objectiveSubmission.status -eq "accepted") "objective submission must be accepted"
Assert-True ($objectiveSubmission.score -eq $objectiveSubmission.max_score) "objective submission must receive full score"

Write-Step "submitting code answer through API queue path"
$codeSource = @"
import sys

def main():
    a, b = map(int, sys.stdin.readline().split())
    print(a + b)

if __name__ == "__main__":
    main()
"@
$codeSubmission = Invoke-ApiJson -Method POST -Path "/problems/P1001/submit-code" -Token $token -Body @{
    language = "python"
    source_code = $codeSource
}
Assert-True ($codeSubmission.problem_type -eq "code") "code submission must target code problem"
Assert-True ($codeSubmission.status -eq "queued") "code submission must enter the online judge queue"
Assert-True (-not [string]::IsNullOrWhiteSpace([string]$codeSubmission.queue_job_id)) "code submission must create a queue job id"
Assert-True (-not [string]::IsNullOrWhiteSpace([string]$codeSubmission.queued_at)) "code submission must record queued_at"
Assert-True ([string]::IsNullOrWhiteSpace([string]$codeSubmission.judged_at)) "API must not mark code submissions judged locally"
Assert-True (@(ConvertTo-ItemArray -Value $codeSubmission.details).Count -eq 0) "API must not attach local judge details to code submissions"

Write-Step "checking my submissions"
$mySubmissions = @(ConvertTo-ItemArray -Value (Invoke-ApiJson -Method GET -Path "/submissions?mine=true" -Token $token))
$mySubmissionIds = @($mySubmissions | ForEach-Object { $_.id })
Assert-True ($mySubmissionIds -contains $objectiveSubmission.id) "my submissions must include the objective submission"
Assert-True ($mySubmissionIds -contains $codeSubmission.id) "my submissions must include the code submission"

Write-Step "checking problem sets"
$problemSets = @(ConvertTo-ItemArray -Value (Invoke-ApiJson -Method GET -Path "/problem-sets"))
Assert-True ($problemSets.Count -gt 0) "problem sets endpoint must return at least one public problem set"
$firstProblemSet = $problemSets[0]
Assert-True (-not [string]::IsNullOrWhiteSpace([string]$firstProblemSet.id)) "problem set must include id"
$firstProblemSetProblems = @(ConvertTo-ItemArray -Value $firstProblemSet.problems)
Assert-True ($firstProblemSetProblems.Count -gt 0) "problem set must include problem summaries"
foreach ($problem in $firstProblemSetProblems) {
    Assert-True (-not (Has-Property -Value $problem -Name "judge_config")) "problem set problem summary must not include judge_config"
}

Write-Step "checking notifications"
$notifications = @(ConvertTo-ItemArray -Value (Invoke-ApiJson -Method GET -Path "/notifications" -Token $token))
Assert-True ($notifications.Count -gt 0) "notifications endpoint must return user notifications"
$judgeNotifications = @($notifications | Where-Object { $_.type -eq "judge" })
Assert-True ($judgeNotifications.Count -gt 0) "submissions must create judge notifications"
$targetNotification = $notifications[0]
$readNotification = Invoke-ApiJson -Method PATCH -Path "/notifications/$($targetNotification.id)/read" -Token $token
Assert-True ($readNotification.id -eq $targetNotification.id) "mark-read endpoint must return the target notification"
Assert-True ($readNotification.is_read -eq $true) "notification must be marked read"

Write-Step "checking admin role management"
$roleAdminLogin = Invoke-ApiJson -Method POST -Path "/auth/login" -Body @{
    username = $AdminUsername
    password = $AdminPassword
}
$roleAdminToken = [string]$roleAdminLogin.access_token
$matrix = Invoke-ApiJson -Method GET -Path "/admin/rbac/matrix" -Token $roleAdminToken
$adminRole = @((ConvertTo-ItemArray -Value $matrix.roles) | Where-Object { $_.code -eq "admin" })[0]
Assert-True ($null -ne $adminRole) "RBAC matrix must include admin role"
Assert-True ($adminRole.permissions -contains "user:role:update") "admin role must include user:role:update"
Assert-True ($adminRole.permissions -contains "tag:manage") "admin role must include tag:manage"
$adminUsers = @(ConvertTo-ItemArray -Value (Invoke-ApiJson -Method GET -Path "/admin/users" -Token $roleAdminToken))
$judgeUser = @($adminUsers | Where-Object { $_.username -eq "judge" })[0]
Assert-True ($null -ne $judgeUser) "admin users endpoint must include judge demo account"
$roleUpdate = Invoke-ApiJson -Method PATCH -Path "/admin/users/$($judgeUser.id)/role" -Token $roleAdminToken -Body @{
    role = [string]$judgeUser.role
}
Assert-True ($roleUpdate.id -eq $judgeUser.id) "role update must return the target user"
Assert-True ($roleUpdate.role -eq $judgeUser.role) "role update must preserve requested role"
Assert-True (@(ConvertTo-ItemArray -Value $roleUpdate.permissions).Count -gt 0) "updated user must include derived permissions"

Write-Step "checking P4 compiler configuration management"
$compilerConfigs = @(ConvertTo-ItemArray -Value (Invoke-ApiJson -Method GET -Path "/admin/compiler-configs" -Token $roleAdminToken))
Assert-True ($compilerConfigs.Count -eq 4) "admin compiler config list must expose four seeded languages"
$cppConfig = @($compilerConfigs | Where-Object { $_.code -eq "cpp" })[0]
Assert-True ($null -ne $cppConfig) "admin compiler config list must include cpp"
Assert-True ((ConvertTo-ItemArray -Value $cppConfig.compile_command).Count -gt 0) "admin compiler config must include compile command"
$publicLanguages = @(ConvertTo-ItemArray -Value (Invoke-ApiJson -Method GET -Path "/judge/languages"))
Assert-True (@($publicLanguages | ForEach-Object { $_.code }) -join "," -eq "c,cpp,java,python") "public judge languages must expose the enabled compiler list"
Assert-True (-not (Has-Property -Value $publicLanguages[0] -Name "compile_command")) "public judge languages must not expose compile commands"
$restoredC = $null
try {
    $disabledC = Invoke-ApiJson -Method PUT -Path "/admin/compiler-configs/c" -Token $roleAdminToken -Body @{
        enabled = $false
    }
    Assert-True ($disabledC.enabled -eq $false) "compiler config update must disable a language"
    $publicLanguagesAfterDisable = @(ConvertTo-ItemArray -Value (Invoke-ApiJson -Method GET -Path "/judge/languages"))
    Assert-True (@($publicLanguagesAfterDisable | ForEach-Object { $_.code }) -join "," -eq "cpp,java,python") "disabled languages must disappear from public judge language list"
    Invoke-ApiFailure -Method POST -Path "/problems/P1001/submit-code" -Token $token -ExpectedStatus 400 -Body @{
        language = "c"
        source_code = "int main(void) { return 0; }"
    }
    $restoredC = Invoke-ApiJson -Method PUT -Path "/admin/compiler-configs/c" -Token $roleAdminToken -Body @{
        enabled = $true
    }
    Assert-True ($restoredC.enabled -eq $true) "compiler config restore must re-enable the language"
    $publicLanguagesAfterRestore = @(ConvertTo-ItemArray -Value (Invoke-ApiJson -Method GET -Path "/judge/languages"))
    Assert-True (@($publicLanguagesAfterRestore | ForEach-Object { $_.code }) -join "," -eq "c,cpp,java,python") "restored compiler languages must return to the public list"
} finally {
    if ($null -eq $restoredC) {
        Invoke-ApiJson -Method PUT -Path "/admin/compiler-configs/c" -Token $roleAdminToken -Body @{
            enabled = $true
        } | Out-Null
    }
}

Write-Step "checking code rejudge queue path"
$rejudgedSubmission = Invoke-ApiJson -Method POST -Path "/judge/submissions/$($codeSubmission.id)/rejudge" -Token $roleAdminToken -Body @{
    reason = "smoke manual rejudge"
}
Assert-True ($rejudgedSubmission.id -eq $codeSubmission.id) "manual rejudge must return the target submission"
Assert-True ($rejudgedSubmission.status -eq "queued") "manual rejudge must re-enter the online judge queue"
Assert-True (-not [string]::IsNullOrWhiteSpace([string]$rejudgedSubmission.queue_job_id)) "manual rejudge must attach a queue job id"
Assert-True ([string]::IsNullOrWhiteSpace([string]$rejudgedSubmission.judged_at)) "manual rejudge must clear judged_at"
Assert-True (@(ConvertTo-ItemArray -Value $rejudgedSubmission.details).Count -eq 0) "manual rejudge must clear old judge details"

$batchRejudge = Invoke-ApiJson -Method POST -Path "/judge/submissions/rejudge" -Token $roleAdminToken -Body @{
    submission_ids = @([string]$codeSubmission.id)
    reason = "smoke batch rejudge"
}
Assert-True ($batchRejudge.requeued_count -eq 1) "batch rejudge must requeue the selected code submission"
Assert-True ($batchRejudge.skipped_count -eq 0) "batch rejudge should not skip the selected code submission"

$judgeMonitor = Invoke-ApiJson -Method GET -Path "/judge/monitor" -Token $roleAdminToken
Assert-True ($judgeMonitor.queue_depth -ge 1) "judge monitor must report queued rejudge work"
Assert-True ($judgeMonitor.queue.pending -ge 1) "judge queue summary must include pending jobs"

Write-Step "checking P4 judge node heartbeat and queue claim"
$judgeNodeHeaders = @{
    "X-Judge-Node-Token" = $JudgeNodeToken
}
$heartbeat = Invoke-ApiJson -Method POST -Path "/judge/nodes/heartbeat" -ExtraHeaders $judgeNodeHeaders -Body @{
    id = "smoke-node"
    name = "smoke-worker"
    status = "online"
    languages = @("python")
    queue_depth = 0
    load = 0.08
}
Assert-True ($heartbeat.id -eq "smoke-node") "heartbeat must register the smoke judge node"
Assert-True ($heartbeat.status -eq "online") "heartbeat must report the node online"
$pendingRejudge = @(ConvertTo-ItemArray -Value $batchRejudge.requeued)[0]
$claim = Invoke-ApiJson -Method POST -Path "/judge/nodes/smoke-node/claim" -ExtraHeaders $judgeNodeHeaders
Assert-True ($claim.node.id -eq "smoke-node") "claim must return the worker node"
Assert-True ($null -ne $claim.job) "claim must lease a pending queue job"
Assert-True (-not [string]::IsNullOrWhiteSpace([string]$pendingRejudge.queue_job_id)) "batch rejudge must leave a pending queue job"
Assert-True ($claim.submission.queue_job_id -eq $claim.job.id) "claimed submission must point at the leased queue job"
Assert-True ($claim.job.language -eq "python") "claim must respect the worker language filter"
Assert-True ($claim.job.status -eq "leased") "claim must lease, not judge, the queue job"
Assert-True ($claim.submission.status -eq "judging") "claimed submission must move to judging"
Assert-True ([string]::IsNullOrWhiteSpace([string]$claim.submission.judged_at)) "worker claim must not mark code submission judged"
Assert-True (@(ConvertTo-ItemArray -Value $claim.submission.details).Count -eq 0) "worker claim must not attach local judge details"
$adminNodesAfterHeartbeat = @(ConvertTo-ItemArray -Value (Invoke-ApiJson -Method GET -Path "/admin/judge-nodes" -Token $roleAdminToken))
$smokeNode = @($adminNodesAfterHeartbeat | Where-Object { $_.id -eq "smoke-node" })[0]
Assert-True ($null -ne $smokeNode) "admin judge node list must show heartbeat-registered nodes"

Write-Step "checking P3 problem management CRUD"
Invoke-ApiFailure -Method GET -Path "/admin/problems" -Token $token -ExpectedStatus 403
Invoke-ApiFailure -Method GET -Path "/admin/tags" -Token $token -ExpectedStatus 403
$adminTags = @(ConvertTo-ItemArray -Value (Invoke-ApiJson -Method GET -Path "/admin/tags" -Token $roleAdminToken))
Assert-True ($adminTags.Count -gt 0) "admin tag list must include seeded tags"
$smokeTagName = "Smoke Tag $([guid]::NewGuid().ToString('N').Substring(0, 8))"
$createdTag = Invoke-ApiJson -Method POST -Path "/admin/tags" -Token $roleAdminToken -Body @{
    name = $smokeTagName
    parent_id = $null
    sort_order = 900
}
Assert-True ($createdTag.name -eq $smokeTagName) "admin tag create must return the new tag"
$renamedTagName = "$smokeTagName Updated"
$renamedTag = Invoke-ApiJson -Method PUT -Path "/admin/tags/$($createdTag.id)" -Token $roleAdminToken -Body @{
    name = $renamedTagName
    parent_id = $null
    sort_order = 901
}
Assert-True ($renamedTag.name -eq $renamedTagName) "admin tag update must persist name"
$deletedTag = Invoke-ApiJson -Method DELETE -Path "/admin/tags/$($createdTag.id)" -Token $roleAdminToken
Assert-True ($deletedTag.id -eq $createdTag.id) "admin tag delete must remove unused tag"
$adminProblems = @(ConvertTo-ItemArray -Value (Invoke-ApiJson -Method GET -Path "/admin/problems" -Token $roleAdminToken))
Assert-True ($adminProblems.Count -ge 4) "admin problem list must include seeded problems"
$managedBlank = @($adminProblems | Where-Object { $_.id -eq "P1002" })[0]
Assert-True (Has-Property -Value $managedBlank -Name "judge_config") "admin problem list must include judge_config for management"
$basicDifficulty = -join ([char[]](0x57FA, 0x7840))
$managedProblem = Invoke-ApiJson -Method POST -Path "/admin/problems" -Token $roleAdminToken -Body @{
    title = "Smoke P3 single choice"
    type = "single_choice"
    difficulty = $basicDifficulty
    tags = @("smoke", "P3")
    statement = "Smoke create problem: which condition does binary search need?"
    options = @(
        @{ key = "A"; text = "Positive numbers only" },
        @{ key = "B"; text = "Monotonic search space" },
        @{ key = "C"; text = "Recursion only" }
    )
    judge_config = @{
        answer = "B"
        score = 100
    }
}
Assert-True ($managedProblem.type -eq "single_choice") "admin problem create must support single_choice"
Assert-True (Has-Property -Value $managedProblem -Name "judge_config") "admin created problem must return management judge_config"
$managedPublicDetail = Invoke-ApiJson -Method GET -Path "/problems/$($managedProblem.id)"
Assert-True (-not (Has-Property -Value $managedPublicDetail -Name "judge_config")) "public detail for managed problem must not include judge_config"
$updatedManagedProblem = Invoke-ApiJson -Method PUT -Path "/admin/problems/$($managedProblem.id)" -Token $roleAdminToken -Body @{
    title = "Smoke P3 single choice"
    type = "single_choice"
    difficulty = $basicDifficulty
    tags = @("smoke", "P3")
    statement = "Smoke updated problem: binary search needs an ordered or monotonic search space."
    options = @(
        @{ key = "A"; text = "Positive numbers only" },
        @{ key = "B"; text = "Monotonic search space" },
        @{ key = "C"; text = "Recursion only" }
    )
    visible = $true
    judge_config = @{
        answer = "B"
        score = 100
    }
}
Assert-True ($updatedManagedProblem.statement -like "Smoke updated problem*") "admin problem update must persist statement"
$managedVersions = @(ConvertTo-ItemArray -Value (Invoke-ApiJson -Method GET -Path "/admin/problems/$($managedProblem.id)/versions" -Token $roleAdminToken))
Assert-True ($managedVersions.Count -ge 1) "admin problem update must create a restorable version"
Assert-True ($managedVersions[0].snapshot.statement -like "Smoke create problem*") "problem version snapshot must preserve the pre-update statement"
$restoredManagedProblem = Invoke-ApiJson -Method POST -Path "/admin/problems/$($managedProblem.id)/versions/$($managedVersions[0].id)/restore" -Token $roleAdminToken
Assert-True ($restoredManagedProblem.statement -like "Smoke create problem*") "problem version restore must recover the archived statement"
$restoredVersions = @(ConvertTo-ItemArray -Value (Invoke-ApiJson -Method GET -Path "/admin/problems/$($managedProblem.id)/versions" -Token $roleAdminToken))
Assert-True ($restoredVersions.Count -ge 2) "problem restore must archive the state before rollback"
$deletedManagedProblem = Invoke-ApiJson -Method DELETE -Path "/admin/problems/$($managedProblem.id)" -Token $roleAdminToken
Assert-True ($deletedManagedProblem.visible -eq $false) "admin problem delete must soft-delete the problem"
Invoke-ApiFailure -Method GET -Path "/problems/$($managedProblem.id)" -ExpectedStatus 404
$republishedManagedProblem = Invoke-ApiJson -Method PATCH -Path "/admin/problems/$($managedProblem.id)/visibility" -Token $roleAdminToken -Body @{
    visible = $true
}
Assert-True ($republishedManagedProblem.visible -eq $true) "admin problem visibility endpoint must republish the problem"
$publicRepublishedManagedProblem = Invoke-ApiJson -Method GET -Path "/problems/$($managedProblem.id)"
Assert-True ($publicRepublishedManagedProblem.id -eq $managedProblem.id) "republished problem must return to public detail"
$deletedManagedProblem = Invoke-ApiJson -Method PATCH -Path "/admin/problems/$($managedProblem.id)/visibility" -Token $roleAdminToken -Body @{
    visible = $false
}
Assert-True ($deletedManagedProblem.visible -eq $false) "admin problem visibility endpoint must unpublish the problem"

Write-Step "checking P3-04 code test-data upload and download"
$managedCodeProblem = Invoke-ApiJson -Method POST -Path "/admin/problems" -Token $roleAdminToken -Body @{
    title = "Smoke P3 code test data"
    type = "code"
    difficulty = $basicDifficulty
    tags = @("smoke", "P3")
    statement = "Read two integers and print their sum."
    input_format = "Two integers."
    output_format = "One integer."
    samples = @(
        @{ input = "1 2"; output = "3" }
    )
    time_limit_ms = 1000
    memory_limit_mb = 128
    visible = $true
    judge_config = @{
        mode = "standard"
    }
}
$tempRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("gayoj-smoke-testdata-" + [System.Guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $tempRoot -Force | Out-Null
try {
    $inputPath = Join-Path $tempRoot "1.in"
    $outputPath = Join-Path $tempRoot "1.out"
    $zipPath = Join-Path $tempRoot "cases.zip"
    $downloadPath = Join-Path $tempRoot "downloaded.zip"
    Set-Content -LiteralPath $inputPath -Encoding ASCII -Value "1 2"
    Set-Content -LiteralPath $outputPath -Encoding ASCII -Value "3"
    Compress-Archive -LiteralPath @($inputPath, $outputPath) -DestinationPath $zipPath -Force
    $uploadedTestData = Invoke-ApiMultipartUpload -Path "/admin/problems/$($managedCodeProblem.id)/testdata" -FilePath $zipPath -Token $roleAdminToken
    Assert-True ($uploadedTestData.case_count -eq 1) "test data upload must detect one input/output pair"
    Assert-True ($uploadedTestData.object_key -like "testdata/$($managedCodeProblem.id)/*") "test data upload must return an object key"
    Invoke-ApiDownload -Path "/admin/problems/$($managedCodeProblem.id)/testdata/download" -OutputPath $downloadPath -Token $roleAdminToken
    Assert-True ((Test-Path -LiteralPath $downloadPath) -and ((Get-Item -LiteralPath $downloadPath).Length -gt 0)) "test data download must write a ZIP file"
    $testDataCodeSubmission = Invoke-ApiJson -Method POST -Path "/problems/$($managedCodeProblem.id)/submit-code" -Token $token -Body @{
        language = "python"
        source_code = "print(sum(map(int, input().split())))"
    }
    Assert-True ($testDataCodeSubmission.status -eq "queued") "code submission after test data upload must remain queue-only"
    Assert-True ($null -eq $testDataCodeSubmission.judged_at) "code submission must not be locally judged by API"
} finally {
    Remove-Item -LiteralPath $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
    Invoke-ApiJson -Method DELETE -Path "/admin/problems/$($managedCodeProblem.id)" -Token $roleAdminToken | Out-Null
}

Write-Step "checking P3 problem package import/export"
Invoke-ApiFailure -Method GET -Path "/admin/problems/export?format=hydro&ids=P1003" -Token $token -ExpectedStatus 403
$exportedProblems = Invoke-ApiJson -Method GET -Path "/admin/problems/export?format=hydro&ids=P1003" -Token $roleAdminToken
Assert-True ($exportedProblems.format -eq "hydro") "problem export must return the requested format"
Assert-True ($exportedProblems.problem_count -eq 1) "problem export must include the selected problem"
Assert-True ([string]$exportedProblems.content -like "*P1003*") "problem export content must include selected problem data"
$importProblemId = "SMOKE-HYDRO-$([guid]::NewGuid().ToString('N').Substring(0, 8).ToUpperInvariant())"
$hydroImportContent = @{
    format = "hydro"
    version = "1.0"
    problems = @(
        @{
            pid = $importProblemId
            title = "Smoke P3 Hydro import"
            type = "single_choice"
            difficulty = $basicDifficulty
            tags = @("smoke", "P3")
            content = "Smoke import problem: choose the monotonic condition."
            options = @(
                @{ key = "A"; text = "Monotonic search space" },
                @{ key = "B"; text = "Random order" }
            )
            judge = @{
                answer = "A"
                score = 100
            }
        }
    )
} | ConvertTo-Json -Depth 20
$importedProblems = Invoke-ApiJson -Method POST -Path "/admin/problems/import" -Token $roleAdminToken -Body @{
    format = "hydro"
    content = $hydroImportContent
    conflict_strategy = "create_new"
}
Assert-True ($importedProblems.created -eq 1) "problem import must create one problem"
$importTarget = [string]$importedProblems.items[0].target_id
$importedPublicDetail = Invoke-ApiJson -Method GET -Path "/problems/$importTarget"
Assert-True (-not (Has-Property -Value $importedPublicDetail -Name "judge_config")) "public detail for imported problem must not include judge_config"
$deletedImportedProblem = Invoke-ApiJson -Method DELETE -Path "/admin/problems/$importTarget" -Token $roleAdminToken
Assert-True ($deletedImportedProblem.visible -eq $false) "imported smoke problem must be soft-deleted after smoke"

if ($Username -ne $AdminUsername) {
    Write-Step "checking banned account enforcement"
    $adminLogin = Invoke-ApiJson -Method POST -Path "/auth/login" -Body @{
        username = $AdminUsername
        password = $AdminPassword
    }
    $adminToken = [string]$adminLogin.access_token

    try {
        $bannedUser = Invoke-ApiJson -Method PATCH -Path "/admin/users/$($me.id)/ban?disabled=true" -Token $adminToken
        Assert-True ($bannedUser.disabled -eq $true) "admin ban endpoint must disable the target user"

        Invoke-ApiFailure -Method GET -Path "/auth/me" -Token $token -ExpectedStatus 403
        Invoke-ApiFailure -Method GET -Path "/users/me/profile" -Token $token -ExpectedStatus 403
        Invoke-ApiFailure -Method PUT -Path "/users/me/password" -Token $token -ExpectedStatus 403 -Body @{
            current_password = $Password
            new_password = "newpass1"
        }
        Invoke-ApiFailure -Method POST -Path "/problems/P1003/submit-objective" -Token $token -ExpectedStatus 403 -Body @{
            answers = @{
                choice = "B"
            }
        }
        Invoke-ApiFailure -Method POST -Path "/offline-results/sync" -Token $token -ExpectedStatus 403 -Body @{
            results = @(
                @{
                    problem_id = "P1003"
                    answers = @{
                        choice = "B"
                    }
                }
            )
        }
        Invoke-ApiFailure -Method POST -Path "/auth/login" -ExpectedStatus 401 -Body @{
            username = $Username
            password = $Password
        }
    } finally {
        Invoke-ApiJson -Method PATCH -Path "/admin/users/$($me.id)/ban?disabled=false" -Token $adminToken | Out-Null
    }

    $relogin = Invoke-ApiJson -Method POST -Path "/auth/login" -Body @{
        username = $Username
        password = $Password
    }
    Assert-True (-not [string]::IsNullOrWhiteSpace($relogin.access_token)) "unbanned user must be able to log in again"
}

Write-Host ""
Write-Host "API smoke passed against $BaseUrl"
