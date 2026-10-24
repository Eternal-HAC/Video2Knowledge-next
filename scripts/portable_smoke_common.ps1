# Only probe listeners belonging to the precise launched process or descendants.
# Importing this file performs no process, network or filesystem operation.
function Find-SmokeOwnedService($Process, [string]$ExpectedVersion) {
    if ($Process.HasExited) { return $null }
    $snapshot = @(Get-CimInstance Win32_Process -ErrorAction Stop)
    if (-not ($snapshot | Where-Object { $_.ProcessId -eq $Process.Id })) { return $null }
    $owned = @{ ([int]$Process.Id) = $true }
    do {
        $changed = $false
        foreach ($entry in $snapshot) {
            $childId = [int]$entry.ProcessId
            if ($owned.ContainsKey([int]$entry.ParentProcessId) -and -not $owned.ContainsKey($childId)) {
                $owned[$childId] = $true
                $changed = $true
            }
        }
    } while ($changed)

    $listeners = @(Get-NetTCPConnection -State Listen -ErrorAction Stop | Where-Object {
        $_.LocalAddress -eq '127.0.0.1' -and
        $_.LocalPort -ge 8000 -and $_.LocalPort -le 8019 -and
        $owned.ContainsKey([int]$_.OwningProcess)
    } | Sort-Object LocalPort -Unique)
    foreach ($listener in $listeners) {
        if ($Process.HasExited) { return $null }
        $candidate = "http://127.0.0.1:$($listener.LocalPort)"
        try {
            $health = Invoke-RestMethod -Uri "$candidate/api/health" -TimeoutSec 1
            if (-not $Process.HasExited -and
                $health.status -eq 'ok' -and
                $health.product -eq 'Video2Knowledge' -and
                $health.service -eq 'VideoToNo' -and
                $health.api_compat -eq 1 -and
                $health.mode -eq 'portable' -and
                $health.version -eq $ExpectedVersion) {
                return $candidate
            }
        } catch {
            # Startup can briefly own a socket before it serves HTTP. Retry later.
        }
    }
    return $null
}
