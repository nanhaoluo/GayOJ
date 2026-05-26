param(
    [string]$Username = "alice",
    [string]$Password = "gayoj123",
    [string]$CoachUsername = "coach",
    [string]$CoachPassword = "gayoj123"
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

function Write-Step {
    param([string]$Message)
    Write-Host "[p8-social-smoke] $Message"
}

function Assert-True {
    param(
        [bool]$Condition,
        [string]$Message
    )
    if (-not $Condition) {
        throw "P8 social smoke assertion failed: $Message"
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

function Invoke-ApiJson {
    param(
        [ValidateSet("GET", "POST", "PATCH", "PUT", "DELETE")]
        [string]$Method,
        [string]$Path,
        [object]$Body = $null,
        [string]$Token = "",
        [hashtable]$Headers = @{}
    )

    $requestHeaders = @{}
    if (-not [string]::IsNullOrWhiteSpace($Token)) {
        $requestHeaders["Authorization"] = "Bearer $Token"
    }
    foreach ($key in $Headers.Keys) {
        $requestHeaders[$key] = $Headers[$key]
    }

    $parameters = @{
        Method = $Method
        Uri = "$script:BaseUrl$Path"
        Headers = $requestHeaders
        TimeoutSec = 15
    }
    if ($null -ne $Body) {
        $parameters["ContentType"] = "application/json; charset=utf-8"
        $parameters["Body"] = ($Body | ConvertTo-Json -Depth 20)
    }

    $response = Invoke-WebRequest @parameters -UseBasicParsing
    if ([string]::IsNullOrWhiteSpace($response.Content)) {
        return $null
    }
    return $response.Content | ConvertFrom-Json
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

    try {
        Invoke-ApiJson -Method $Method -Path $Path -Body $Body -Token $Token | Out-Null
    } catch {
        $statusCode = $null
        if ($_.Exception.Response -and $_.Exception.Response.StatusCode) {
            $statusCode = [int]$_.Exception.Response.StatusCode
        }
        Assert-True ($statusCode -eq $ExpectedStatus) "$Method $Path must fail with HTTP $ExpectedStatus"
        return
    }
    throw "P8 social smoke assertion failed: $Method $Path must fail with HTTP $ExpectedStatus"
}

$tempRoot = [System.IO.Path]::GetTempPath()
$tempDir = Join-Path $tempRoot ("gayoj-p8-social-" + [System.Guid]::NewGuid().ToString("N"))
$dbPath = Join-Path $tempDir "gayoj-p8-social.sqlite3"
$apiOut = Join-Path $tempDir "api.out.log"
$apiErr = Join-Path $tempDir "api.err.log"
$apiProcess = $null

$oldEnv = @{
    GAYOJ_STORAGE_BACKEND = $env:GAYOJ_STORAGE_BACKEND
    GAYOJ_SQLITE_PATH = $env:GAYOJ_SQLITE_PATH
}

try {
    New-Item -ItemType Directory -Path $tempDir | Out-Null
    $port = Find-FreePort
    $script:BaseUrl = "http://127.0.0.1:$port/api/v1"
    $healthUrl = "http://127.0.0.1:$port/api/v1/health"

    Set-EnvOrRemove -Name "GAYOJ_STORAGE_BACKEND" -Value "sqlite"
    Set-EnvOrRemove -Name "GAYOJ_SQLITE_PATH" -Value $dbPath

    Write-Step "starting temporary API on $script:BaseUrl"
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

    Write-Step "logging in users"
    $studentLogin = Invoke-ApiJson -Method POST -Path "/auth/login" -Body @{
        username = $Username
        password = $Password
    }
    $coachLogin = Invoke-ApiJson -Method POST -Path "/auth/login" -Body @{
        username = $CoachUsername
        password = $CoachPassword
    }
    $studentToken = [string]$studentLogin.access_token
    $coachToken = [string]$coachLogin.access_token
    Assert-True (-not [string]::IsNullOrWhiteSpace($studentToken)) "student login must return a token"
    Assert-True (-not [string]::IsNullOrWhiteSpace($coachToken)) "coach login must return a token"

    Write-Step "creating categorized solution"
    $solution = Invoke-ApiJson -Method POST -Path "/discussions" -Token $studentToken -Body @{
        type = "solution"
        target_id = "P1001"
        title = "P8 smoke solution"
        content = "Read two integers and print their sum."
        solution_category = "tutorial"
    }
    Assert-True ($solution.type -eq "solution") "created post must be a solution"
    Assert-True ($solution.solution_category -eq "tutorial") "created solution must preserve category"
    Assert-True (-not ($solution.PSObject.Properties.Name -contains "liked_by")) "solution response must not expose liked_by"
    Assert-True (-not ($solution.PSObject.Properties.Name -contains "bookmarked_by")) "solution response must not expose bookmarked_by"
    $solutionId = [string]$solution.id

    Write-Step "checking idempotent like and bookmark"
    $liked = Invoke-ApiJson -Method PUT -Path "/discussions/$solutionId/like" -Token $coachToken
    $likedAgain = Invoke-ApiJson -Method PUT -Path "/discussions/$solutionId/like" -Token $coachToken
    $bookmarked = Invoke-ApiJson -Method PUT -Path "/discussions/$solutionId/bookmark" -Token $coachToken
    Assert-True ($liked.changed -eq $true) "first like must change state"
    Assert-True ($liked.discussion.likes -eq 1) "first like must increase like count"
    Assert-True ($likedAgain.changed -eq $false) "second like must be idempotent"
    Assert-True ($likedAgain.discussion.likes -eq 1) "second like must keep like count stable"
    Assert-True ($bookmarked.discussion.bookmarked -eq $true) "bookmark endpoint must mark viewer state"
    Assert-True (-not ($bookmarked.discussion.PSObject.Properties.Name -contains "bookmarked_by")) "bookmark response must not expose bookmark user ids"

    Write-Step "checking solution category filter and type guard"
    $filtered = Invoke-ApiJson -Method GET -Path "/discussions?type=solution&solution_category=tutorial" -Token $coachToken
    $filteredIds = @($filtered.items | ForEach-Object { $_.id })
    Assert-True ($filteredIds -contains $solutionId) "solution category filter must include the created solution"
    Assert-True (($filtered.items | ConvertTo-Json -Depth 20) -notmatch "liked_by|bookmarked_by") "discussion list must stay redacted"
    $general = Invoke-ApiJson -Method POST -Path "/discussions" -Token $studentToken -Body @{
        type = "general"
        title = "P8 smoke general"
        content = "General discussion."
    }
    Invoke-ApiFailure -Method PUT -Path "/discussions/$($general.id)/like" -ExpectedStatus 400 -Token $coachToken

    Write-Step "checking notification stream redaction"
    $streamResponse = Invoke-WebRequest -UseBasicParsing -Method GET -Uri "$script:BaseUrl/notifications/stream?token=$studentToken" -Headers @{ Accept = "text/event-stream" } -TimeoutSec 15
    Assert-True ($streamResponse.Headers["Content-Type"] -like "text/event-stream*") "notification stream must use SSE content type"
    Assert-True ($streamResponse.Content -match "题解收到点赞") "solution like must notify the solution author"
    Assert-True ($streamResponse.Content -notmatch "source_code|judge_config|answers|expected|bookmarked_by|liked_by") "notification stream must not expose sensitive fields"

    Write-Host ""
    Write-Host "P8 social smoke passed against $script:BaseUrl"
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
