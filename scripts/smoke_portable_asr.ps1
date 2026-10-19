#requires -Version 7.0

param(
    [Parameter(Mandatory = $true)]
    [string]$Exe,
    [string]$ExpectedVersion = "1.4.2-v2k.1",
    [string]$Model = "small",
    [int]$StartupTimeoutSeconds = 180,
    [int]$TaskTimeoutSeconds = 600
)

$ErrorActionPreference = "Stop"
$exePath = (Resolve-Path -LiteralPath $Exe).Path
$tempBase = [System.IO.Path]::GetTempPath().TrimEnd("\")
$smokeRoot = Join-Path $tempBase ("v2k-rc-smoke-" + [guid]::NewGuid().ToString("N"))
$workspace = Join-Path $smokeRoot "workspace"
$wav = Join-Path $smokeRoot "packaged-asr-smoke.wav"
$process = $null
$oldEnv = @{
    VIDEOTONOTES_WORKSPACE = $env:VIDEOTONOTES_WORKSPACE
    VIDEOTONOTES_NO_BROWSER = $env:VIDEOTONOTES_NO_BROWSER
    HF_HUB_OFFLINE = $env:HF_HUB_OFFLINE
    TRANSFORMERS_OFFLINE = $env:TRANSFORMERS_OFFLINE
    WHISPER_CACHE_DIR = $env:WHISPER_CACHE_DIR
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

try {
    New-Item -ItemType Directory -Path $workspace -Force | Out-Null
    $modelRoot = Join-Path $env:USERPROFILE ".cache\huggingface\hub"
    $snapshots = Join-Path $modelRoot "models--Systran--faster-whisper-$Model\snapshots"
    $snapshot = Get-ChildItem -LiteralPath $snapshots -Directory | Select-Object -First 1
    if (-not $snapshot) {
        throw "The cached Whisper $Model snapshot is missing; refusing to download it."
    }
    foreach ($name in "config.json", "model.bin", "tokenizer.json", "vocabulary.txt") {
        $file = Get-Item -LiteralPath (Join-Path $snapshot.FullName $name)
        if ($file.Length -le 0) {
            throw "The cached Whisper $Model file is invalid: $name"
        }
    }

    Add-Type -AssemblyName System.Speech
    $synth = [System.Speech.Synthesis.SpeechSynthesizer]::new()
    try {
        $synth.SelectVoice("Microsoft Huihui Desktop")
        $synth.Rate = -1
        $synth.SetOutputToWaveFile($wav)
        $speechBase64 = "6L+Z5piv5omT5YyF54mI5pys55qE5pys5Zyw6K+t6Z+z6K+G5Yir5rWL6K+V44CC6KeG6aKR55+l6K+G5bel5YW35bqU5b2T55Sf5oiQ5bim5pe26Ze06L2055qE5Lit5paH6L2s5b2V77yM5bm25LiU5YWo56iL5LiN6K6/6Zeu572R57uc5qih5Z6L44CC"
        $speechText = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($speechBase64))
        $synth.Speak($speechText)
        $synth.SetOutputToNull()
    } finally {
        $synth.Dispose()
    }
    if ((Get-Item -LiteralPath $wav).Length -le 1000) {
        throw "SAPI failed to generate the smoke-test audio."
    }

    $env:VIDEOTONOTES_WORKSPACE = $workspace
    $env:VIDEOTONOTES_NO_BROWSER = "1"
    $env:HF_HUB_OFFLINE = "1"
    $env:TRANSFORMERS_OFFLINE = "1"
    $env:WHISPER_CACHE_DIR = $modelRoot
    $process = Start-Process -FilePath $exePath -PassThru -WindowStyle Hidden
    Restore-SmokeEnvironment

    $baseUrl = $null
    for ($attempt = 0; $attempt -lt $StartupTimeoutSeconds; $attempt++) {
        foreach ($port in 8000..8019) {
            try {
                $candidate = "http://127.0.0.1:$port"
                $health = Invoke-RestMethod -Uri "$candidate/api/health" -TimeoutSec 1
                if (
                    $health.status -eq "ok" -and
                    $health.service -eq "VideoToNo" -and
                    $health.mode -eq "portable" -and
                    $health.version -eq $ExpectedVersion
                ) {
                    $baseUrl = $candidate
                    break
                }
            } catch {}
        }
        if ($baseUrl) { break }
        if ($process.HasExited) {
            throw "The portable executable exited before startup, exit=$($process.ExitCode)"
        }
        Start-Sleep -Seconds 1
    }
    if (-not $baseUrl) {
        throw "The portable executable was not healthy within $StartupTimeoutSeconds seconds."
    }
    Write-Output "SMOKE_HEALTH_OK version=$ExpectedVersion mode=portable"

    $upload = Invoke-RestMethod -Method Post -Uri "$baseUrl/api/upload" -Form @{
        file = Get-Item -LiteralPath $wav
    }
    $request = @{
        upload_task_id = $upload.task_id
        processing_mode = "reuse"
        prefer_subtitles = $true
        whisper_model = $Model
        use_gpu = $false
    } | ConvertTo-Json
    $submitted = Invoke-RestMethod `
        -Method Post `
        -Uri "$baseUrl/api/transcribe" `
        -ContentType "application/json; charset=utf-8" `
        -Body $request
    $taskId = $submitted.task_id

    $status = $null
    for ($attempt = 0; $attempt -lt $TaskTimeoutSeconds; $attempt++) {
        $status = Invoke-RestMethod -Uri "$baseUrl/api/task/$taskId" -TimeoutSec 3
        if ($status.status -in @("completed", "failed", "cancelled")) { break }
        if (($attempt % 10) -eq 0) {
            Write-Output (
                "SMOKE_PROGRESS status={0} step={1} progress={2}" -f `
                    $status.status, $status.step_name, $status.progress
            )
        }
        Start-Sleep -Seconds 1
    }
    if ($status.status -ne "completed") {
        throw "The transcription task did not complete: status=$($status.status); error=$($status.error)"
    }

    $jsonTranscript = Invoke-RestMethod -Uri "$baseUrl/api/task/$taskId/transcript" -TimeoutSec 5
    $markdownTranscript = Invoke-RestMethod `
        -Uri "$baseUrl/api/task/$taskId/transcript?output_format=markdown" `
        -TimeoutSec 5
    $srtTranscript = Invoke-RestMethod `
        -Uri "$baseUrl/api/task/$taskId/transcript?output_format=srt" `
        -TimeoutSec 5
    if ([int]$jsonTranscript.segment_count -le 0) {
        throw "The JSON transcript has no segments."
    }
    if ([string]::IsNullOrWhiteSpace([string]$markdownTranscript.text)) {
        throw "The Markdown transcript is empty."
    }
    if (-not ([string]$srtTranscript.text).Contains("-->")) {
        throw "The SRT transcript has no SubRip time arrow."
    }

    $taskDir = Join-Path $workspace $taskId
    foreach ($name in "transcript.json", "transcript.md", "task.json") {
        if (-not (Test-Path -LiteralPath (Join-Path $taskDir $name) -PathType Leaf)) {
            throw "A task artifact is missing: $name"
        }
    }
    $archives = @(Get-ChildItem -LiteralPath (Join-Path $workspace "transcripts") -File -Filter "*.md")
    if ($archives.Count -lt 1) {
        throw "The central transcript archive is missing."
    }

    $sensitivePattern = "(?i)(Bearer\s+[A-Za-z0-9._-]+|api[_-]?key\s*[:=]\s*\S+|sk-[A-Za-z0-9]{8,})"
    foreach ($auditFile in (Join-Path $workspace "_app.log"), (Join-Path $taskDir "task.json")) {
        if (Test-Path -LiteralPath $auditFile) {
            $content = Get-Content -LiteralPath $auditFile -Raw
            if ($content -match $sensitivePattern) {
                throw "Sensitive-data audit failed: $([IO.Path]::GetFileName($auditFile))"
            }
        }
    }

    Write-Output (
        "SMOKE_TRANSCRIPT_OK segments={0} language={1} markdown_chars={2} srt_chars={3} archives={4}" -f `
            $jsonTranscript.segment_count,
            $jsonTranscript.language,
            ([string]$markdownTranscript.text).Length,
            ([string]$srtTranscript.text).Length,
            $archives.Count
    )
    Write-Output "SMOKE_TASK_OK status=$($status.status) requested_model=$Model device=$($status.result.device)"
} catch {
    Write-Output ("SMOKE_FAILED " + $_.Exception.Message)
    $log = Join-Path $workspace "_app.log"
    if (Test-Path -LiteralPath $log) {
        Get-Content -LiteralPath $log -Tail 80
    }
    throw
} finally {
    Restore-SmokeEnvironment
    if ($process -and -not $process.HasExited) {
        Stop-SmokeProcessTree -RootProcessId $process.Id
        Start-Sleep -Seconds 2
    }

    $resolvedSmoke = [IO.Path]::GetFullPath($smokeRoot)
    $resolvedTemp = [IO.Path]::GetFullPath($tempBase).TrimEnd("\") + "\"
    $safeName = (Split-Path -Leaf $resolvedSmoke).StartsWith("v2k-rc-smoke-")
    if ($resolvedSmoke.StartsWith($resolvedTemp, [StringComparison]::OrdinalIgnoreCase) -and $safeName) {
        Remove-Item -LiteralPath $resolvedSmoke -Recurse -Force -ErrorAction SilentlyContinue
    } else {
        Write-Warning "The temporary-directory identity check failed; it was not removed."
    }
}
