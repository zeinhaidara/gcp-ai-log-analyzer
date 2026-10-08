param([string]$Dashboard = 'log-analyzer-dev', [string]$LogId = '')
$ErrorActionPreference = 'Stop'
$gcpCli = (Get-Command gcloud.cmd -ErrorAction SilentlyContinue).Source
if (!$gcpCli) { $gcpCli = Join-Path $env:LOCALAPPDATA 'Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd' }
if (!(Test-Path -LiteralPath $gcpCli)) { throw 'Install Google Cloud SDK first' }
$project = 'ai-log-analyzer-511017'
$region = 'us-central1'
if (!$LogId) {
$baseUrl = & $gcpCli run services describe $Dashboard --project=$project --region=$region --format='value(status.url)'
if ($LASTEXITCODE -ne 0) { throw 'Dashboard URL lookup failed' }
$identityToken = & $gcpCli auth print-identity-token
if ($LASTEXITCODE -ne 0) { throw 'Identity token failed' }
$payload = @{ filename='adk-smoke-test.txt'; content="2026-10-08T20:00:00Z INFO Application started`n2026-10-08T20:00:01Z ERROR Database connection timed out`n2026-10-08T20:00:02Z WARN Retry scheduled" } | ConvertTo-Json
$uploaded = Invoke-RestMethod -Method Post -Uri "$baseUrl/logs" -Headers @{Authorization="Bearer $identityToken"} -ContentType application/json -Body $payload
$LogId = $uploaded.id
}
if ($LogId -notmatch '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$') { throw 'Expected a UUID log ID' }
$accessToken = & $gcpCli auth print-access-token
if ($LASTEXITCODE -ne 0) { throw 'Access token failed' }
$message = @{log_id=$LogId} | ConvertTo-Json -Compress
$encoded = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($message))
$publishBody = @{messages=@(@{data=$encoded})} | ConvertTo-Json -Depth 5
Invoke-RestMethod -Method Post -Uri "https://pubsub.googleapis.com/v1/projects/$project/topics/log-analyzer-dev-investigations:publish" -Headers @{Authorization="Bearer $accessToken"} -ContentType application/json -Body $publishBody | Out-Null
Write-Output "Published investigation for log_id=$LogId"
$resultUrl = "https://firestore.googleapis.com/v1/projects/$project/databases/(default)/documents/investigations/$LogId"
$completed = $false
for ($attempt=0; $attempt -lt 60; $attempt++) {
    try {
        $result = Invoke-RestMethod -Uri $resultUrl -Headers @{Authorization="Bearer $accessToken"}
        if ($result.fields.status.stringValue -eq 'completed') { $completed=$true; break }
    } catch {
        if ([int]$_.Exception.Response.StatusCode -ne 404) { throw }
    }
    Start-Sleep -Seconds 5
}
if (!$completed) { throw "Investigation incomplete. Inspect Firestore and agent logs for $LogId" }
$sdkBin=Split-Path $gcpCli
$env:PATH="$sdkBin;$env:PATH"
$query = "SELECT log_id, severity, model FROM ``$project.log_analyzer_dev.incidents`` WHERE log_id = '$LogId'"
$rows = & "$sdkBin\bq.cmd" --project_id=$project --location=$region query --use_legacy_sql=false --maximum_bytes_billed=20971520 --format=json $query
if ($LASTEXITCODE -ne 0) { throw "BigQuery verification failed: $($rows -join ' ')" }
$parsed = ($rows -join "`n") | ConvertFrom-Json
if (@($parsed).Count -ne 1) { throw 'Expected exactly one incident row' }
Write-Output "VERIFIED uploaded log -> Pub/Sub -> ADK/Gemini -> Firestore -> BigQuery. log_id=$LogId"
Write-Output "Model=$($result.fields.model.stringValue); severity=$($parsed[0].severity)"
