param([string]$Dashboard = 'log-analyzer-dev', [string]$LogId = '')
$ErrorActionPreference = 'Stop'
$gcpCli = Join-Path $env:LOCALAPPDATA 'Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd'
$project = 'ai-log-analyzer-511017'
$region = 'us-central1'
$baseUrl = & $gcpCli run services describe $Dashboard --project=$project --region=$region --format='value(status.url)'
if ($LASTEXITCODE -ne 0) { throw 'Dashboard URL lookup failed' }
if (!$LogId) {
    $payload = @{ filename='automatic-adk-smoke-test.txt'; content="2026-10-09T18:00:00Z INFO orders started`n2026-10-09T18:00:01Z ERROR database timed out`n2026-10-09T18:00:02Z WARN retry scheduled" } | ConvertTo-Json
    $uploaded = Invoke-RestMethod -Method Post -Uri "$baseUrl/logs" -ContentType application/json -Body $payload
    $LogId = $uploaded.id
    if ($uploaded.investigation.status -ne 'queued') { throw "Upload saved but dispatch failed: $LogId" }
} else {
    if ($LogId -notmatch '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$') { throw 'Expected a UUID log ID' }
    Invoke-RestMethod -Method Post -Uri "$baseUrl/logs/$LogId/investigation" | Out-Null
}
Write-Output "Waiting for automatic investigation: $LogId"
$completed = $false
for ($attempt=0; $attempt -lt 60; $attempt++) {
    $result = Invoke-RestMethod -Uri "$baseUrl/logs/$LogId/investigation"
    if ($result.status -eq 'completed') { $completed=$true; break }
    Start-Sleep -Seconds 5
}
if (!$completed) { throw "Investigation incomplete. Inspect agent logs for $LogId" }
$sdkBin = Split-Path $gcpCli
$env:PATH = "$sdkBin;$env:PATH"
$query = "SELECT log_id, severity, model FROM ``$project.log_analyzer_dev.incidents`` WHERE completed_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY) AND log_id = '$LogId'"
$rows = & "$sdkBin\bq.cmd" --project_id=$project --location=$region query --use_legacy_sql=false --maximum_bytes_billed=20971520 --format=json $query
if ($LASTEXITCODE -ne 0) { throw 'BigQuery verification failed' }
$parsed = ($rows -join "`n") | ConvertFrom-Json
if (@($parsed).Count -ne 1) { throw 'Expected exactly one incident row' }
Write-Output "VERIFIED dashboard upload -> automatic Pub/Sub -> ADK/Gemini -> displayed API findings -> BigQuery. log_id=$LogId"
Write-Output "Model=$($result.model); severity=$($result.findings.severity); history_count=$($result.history_count)"
