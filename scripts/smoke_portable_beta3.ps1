#requires -Version 7.0

param(
    [Parameter(Mandatory = $true)]
    [string]$Exe,
    [string]$ExpectedVersion = "",
    [int]$StartupTimeoutSeconds = 180
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "portable_smoke_common.ps1")
$exePath = (Resolve-Path -LiteralPath $Exe).Path
$repoRoot = Split-Path -Parent $PSScriptRoot
if (-not $ExpectedVersion) {
    $versionLine = Select-String -Path (Join-Path $repoRoot "product_info.py") -Pattern '^VERSION = "([^"]+)"' | Select-Object -First 1
    if (-not $versionLine) { throw "无法从 product_info.py 读取 VERSION" }
    $ExpectedVersion = $versionLine.Matches[0].Groups[1].Value
}

$tempBase = [System.IO.Path]::GetTempPath().TrimEnd("\")
$smokeRoot = Join-Path $tempBase ("v2k-beta3-smoke-" + [guid]::NewGuid().ToString("N"))
$workspace = Join-Path $smokeRoot "workspace"
$process = $null
$oldEnv = @{
    VIDEO2KNOWLEDGE_WORKSPACE = $env:VIDEO2KNOWLEDGE_WORKSPACE
    VIDEO2KNOWLEDGE_NO_BROWSER = $env:VIDEO2KNOWLEDGE_NO_BROWSER
}

function Restore-SmokeEnvironment {
    foreach ($key in $oldEnv.Keys) {
        if ($null -eq $oldEnv[$key]) {
            Remove-Item "Env:$key" -ErrorAction SilentlyContinue
        } else {
            Set-Item "Env:$key" $oldEnv[$key]
        }
    }
}

function Stop-SmokeProcessTree([int]$RootProcessId) {
    $processes = @(Get-CimInstance Win32_Process)
    $ids = [System.Collections.Generic.List[int]]::new()

    function Add-Children([int]$ParentId) {
        foreach ($child in $processes | Where-Object { $_.ParentProcessId -eq $ParentId }) {
            Add-Children -ParentId ([int]$child.ProcessId)
            $ids.Add([int]$child.ProcessId)
        }
    }

    Add-Children -ParentId $RootProcessId
    $ids.Add($RootProcessId)
    foreach ($processId in $ids) {
        Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
    }
}

function Start-SmokeProcess {
    $env:VIDEO2KNOWLEDGE_WORKSPACE = $workspace
    $env:VIDEO2KNOWLEDGE_NO_BROWSER = "1"
    $script:process = Start-Process -FilePath $exePath -PassThru -WindowStyle Hidden
    Restore-SmokeEnvironment

    for ($attempt = 0; $attempt -lt $StartupTimeoutSeconds; $attempt++) {
        $candidate = Find-SmokeOwnedService -Process $script:process -ExpectedVersion $ExpectedVersion
        if ($candidate) { return $candidate }
        if ($script:process.HasExited) {
            throw "The portable executable exited before startup, exit=$($script:process.ExitCode)"
        }
        Start-Sleep -Seconds 1
    }
    throw "The portable executable was not healthy within $StartupTimeoutSeconds seconds."
}

function Stop-SmokeProcess {
    if ($script:process -and -not $script:process.HasExited) {
        Stop-SmokeProcessTree -RootProcessId $script:process.Id
        Start-Sleep -Seconds 2
    }
    $script:process = $null
}

function Write-JsonFile([string]$Path, [hashtable]$Payload) {
    [System.IO.File]::WriteAllText(
        $Path,
        ($Payload | ConvertTo-Json -Depth 8),
        [System.Text.UTF8Encoding]::new($false)
    )
}

try {
    New-Item -ItemType Directory -Path $workspace -Force | Out-Null
    $noteDir = Join-Path $workspace "seed-note"
    $failedDir = Join-Path $workspace "seed-failed"
    New-Item -ItemType Directory -Path $noteDir, $failedDir | Out-Null

    $sourceUrl = "https://www.youtube.com/watch?v=v2k-beta3-offline"
    $noteManifest = @{
        task_id = "seed-note"
        created_at = "2026-10-22T03:00:00+00:00"
        source_url = $sourceUrl
        normalized_source_url = $sourceUrl
        output = "note"
        origin = "web"
        title = "Beta.3 合成历史笔记"
        note_template_snapshot = @{ id = "builtin-study-lecture"; name = "学习讲义"; version = 1 }
        runtime = @{
            status = "completed"
            step = 7
            step_name = "完成"
            progress = 100
            created_at = "2026-10-22T03:00:00+00:00"
            finished_at = "2026-10-22T03:00:05+00:00"
            elapsed_seconds = 5
            result = @{ title = "Beta.3 合成历史笔记" }
        }
    }
    Write-JsonFile -Path (Join-Path $noteDir "task.json") -Payload $noteManifest
    [System.IO.File]::WriteAllText(
        (Join-Path $noteDir "notes.md"),
        "# Beta.3 合成历史笔记`n",
        [System.Text.UTF8Encoding]::new($false)
    )
    Write-JsonFile -Path (Join-Path $noteDir "transcript.json") -Payload @{
        language = "zh"
        source = "test"
        segments = @(@{ start = 0; end = 1; text = "合成转录" })
    }
    Write-JsonFile -Path (Join-Path $failedDir "task.json") -Payload @{
        task_id = "seed-failed"
        created_at = "2026-10-22T02:00:00+00:00"
        output = "note"
        origin = "web"
        title = "Beta.3 合成失败任务"
        runtime = @{
            status = "failed"
            created_at = "2026-10-22T02:00:00+00:00"
            finished_at = "2026-10-22T02:00:03+00:00"
            elapsed_seconds = 3
            result = @{ title = "Beta.3 合成失败任务" }
        }
    }

    $baseUrl = Start-SmokeProcess
    Write-Output "BETA3_SMOKE_HEALTH_OK version=$ExpectedVersion mode=portable"

    $templates = Invoke-RestMethod -Uri "$baseUrl/api/note-templates" -TimeoutSec 5
    if (@($templates.templates).Count -ne 6) {
        throw "Expected six built-in templates."
    }
    foreach ($template in @($templates.templates)) {
        if ([string]::IsNullOrWhiteSpace([string]$template.preview_markdown)) {
            throw "A template preview is empty: $($template.id)"
        }
    }

    $history = Invoke-RestMethod -Uri "$baseUrl/api/tasks?offset=0&limit=1" -TimeoutSec 5
    if ($history.total -ne 2 -or -not $history.has_more -or @($history.tasks).Count -ne 1) {
        throw "History pagination contract failed."
    }
    $inspect = Invoke-RestMethod `
        -Method Post `
        -Uri "$baseUrl/api/source-inspect" `
        -ContentType "application/json; charset=utf-8" `
        -Body (@{ video_url = $sourceUrl } | ConvertTo-Json)
    if (
        $inspect.platform -ne "youtube" -or
        $inspect.support_level -ne "focused" -or
        $inspect.reusable_task.task_id -ne "seed-note"
    ) {
        throw "Offline source inspection or transcript reuse lookup failed."
    }
    $favorite = Invoke-RestMethod `
        -Method Patch `
        -Uri "$baseUrl/api/task/seed-note/favorite" `
        -ContentType "application/json; charset=utf-8" `
        -Body '{"favorite":true}'
    if (-not $favorite.favorite) { throw "Favorite update failed." }

    Stop-SmokeProcess
    $baseUrl = Start-SmokeProcess
    $favorites = Invoke-RestMethod -Uri "$baseUrl/api/tasks?favorite=true" -TimeoutSec 5
    if ($favorites.total -ne 1 -or $favorites.tasks[0].task_id -ne "seed-note") {
        throw "Favorite did not survive a portable restart."
    }
    $opened = Invoke-RestMethod -Uri "$baseUrl/api/task/seed-note" -TimeoutSec 5
    if (-not ([string]$opened.result.markdown).Contains("Beta.3 合成历史笔记")) {
        throw "Lazy history task restoration failed."
    }
    $homeHtml = (Invoke-WebRequest -Uri "$baseUrl/" -TimeoutSec 5).Content
    foreach ($marker in "templatePreviewPanel", "historyFavorite", "sourceInspectPanel") {
        if (-not $homeHtml.Contains($marker)) { throw "The packaged page is missing $marker." }
    }

    Write-Output "BETA3_SMOKE_TEMPLATES_OK count=6 previews=6"
    Write-Output "BETA3_SMOKE_HISTORY_OK total=2 favorite_persisted=true lazy_restore=true"
    Write-Output "BETA3_SMOKE_SOURCE_OK platform=youtube support=focused reusable=seed-note"
} catch {
    Write-Output ("BETA3_SMOKE_FAILED " + $_.Exception.Message)
    $log = Join-Path $workspace "_app.log"
    if (Test-Path -LiteralPath $log) {
        Get-Content -LiteralPath $log -Tail 80
    }
    throw
} finally {
    Restore-SmokeEnvironment
    Stop-SmokeProcess
    $resolvedSmoke = [IO.Path]::GetFullPath($smokeRoot)
    $resolvedTemp = [IO.Path]::GetFullPath($tempBase).TrimEnd("\") + "\"
    $safeName = (Split-Path -Leaf $resolvedSmoke).StartsWith("v2k-beta3-smoke-")
    if ($resolvedSmoke.StartsWith($resolvedTemp, [StringComparison]::OrdinalIgnoreCase) -and $safeName) {
        Remove-Item -LiteralPath $resolvedSmoke -Recurse -Force -ErrorAction SilentlyContinue
    } else {
        Write-Warning "The temporary-directory identity check failed; it was not removed."
    }
}
