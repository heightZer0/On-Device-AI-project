param(
    [string]$BaseUrl = "http://127.0.0.1:8000",
    [string]$Token = $env:BAJAHOE_DEVICE_TOKEN,
    [int]$MonitorSeconds = 20
)

$ErrorActionPreference = "Stop"
if ([string]::IsNullOrWhiteSpace($Token)) {
    throw "Token is required. Set `$env:BAJAHOE_DEVICE_TOKEN or pass -Token."
}

$headers = @{ Authorization = "Bearer $Token" }
$root = "$BaseUrl/api/v1"

function Send-Post($Path, $Payload) {
    $json = $Payload | ConvertTo-Json -Depth 10
    Invoke-RestMethod -Method Post -Uri "$root$Path" -Headers $headers `
        -ContentType "application/json" -Body $json
}

Write-Host "== P2 health =="
Invoke-RestMethod -Method Get -Uri "$root/health" | ConvertTo-Json -Depth 8
Write-Host "== Current status (webcam opens during calibration) =="
Invoke-RestMethod -Method Get -Uri "$root/status" -Headers $headers | ConvertTo-Json -Depth 8

$calibration = Send-Post "/calibration/start" @{
    duration_sec = 8
    request_id = [guid]::NewGuid().ToString()
}
Write-Host "== Camera detection at calibration start =="
$calibration.detection | ConvertTo-Json -Depth 8

$ready = $false
for ($i = 0; $i -lt 40; $i++) {
    Start-Sleep -Seconds 1
    $preview = Invoke-RestMethod -Method Get `
        -Uri "$root/calibration/preview?calibration_id=$($calibration.calibration_id)" `
        -Headers $headers
    Write-Host ("Calibration: {0}, progress: {1}" -f $preview.state, $preview.progress)
    if ($preview.state -eq "READY") { $ready = $true; break }
    if ($preview.state -eq "FAILED") {
        $preview | ConvertTo-Json -Depth 8
        Send-Post "/calibration/confirm" @{
            calibration_id = $calibration.calibration_id
            confirm = $false
            request_id = [guid]::NewGuid().ToString()
        } | Out-Null
        throw "Calibration failed. Check camera framing and the P1 failure details above."
    }
}

if (-not $ready) {
    Send-Post "/calibration/confirm" @{
        calibration_id = $calibration.calibration_id
        confirm = $false
        request_id = [guid]::NewGuid().ToString()
    } | Out-Null
    throw "Calibration did not become READY in 40 seconds."
}

$choice = Read-Host "Calibration is READY. Save this camera baseline and start monitoring? [y/N]"
if ($choice -notin @("y", "Y", "yes", "YES")) {
    Send-Post "/calibration/confirm" @{
        calibration_id = $calibration.calibration_id
        confirm = $false
        request_id = [guid]::NewGuid().ToString()
    } | Out-Null
    Write-Host "Calibration cancelled; no baseline was saved."
    exit 0
}

$confirmed = Send-Post "/calibration/confirm" @{
    calibration_id = $calibration.calibration_id
    confirm = $true
    request_id = [guid]::NewGuid().ToString()
}
$confirmed | ConvertTo-Json -Depth 8
if (-not $confirmed.calibrated) { throw "P2 did not confirm a saved calibration." }

Send-Post "/monitoring/start" @{ request_id = [guid]::NewGuid().ToString() } | Out-Null
Write-Host "== Live status from webcam -> P1 -> P2 API =="
for ($i = 0; $i -lt $MonitorSeconds; $i++) {
    $status = Invoke-RestMethod -Method Get -Uri "$root/status" -Headers $headers
    $p = $status.posture
    $s = $status.session
    [pscustomobject]@{
        second = $i + 1
        camera = $status.camera
        system_state = $status.system_state
        posture_state = $p.state
        reason = $p.reason
        indicators = ($p.indicators | ConvertTo-Json -Compress -Depth 6)
        focus_sec = $s.focus_sec
        good_sec = $s.good_sec
        attention_sec = $s.attention_sec
        unavailable_sec = $s.unavailable_sec
    } | Format-List
    Start-Sleep -Seconds 1
}

$ended = Send-Post "/monitoring/stop" @{ request_id = [guid]::NewGuid().ToString() }
Write-Host "== Session summary returned by P2 =="
$ended.session_summary | ConvertTo-Json -Depth 8
