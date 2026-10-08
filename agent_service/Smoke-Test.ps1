param([string]$Dashboard = 'log-analyzer-dev')
$ErrorActionPreference = 'Stop'
$gcpCli = (Get-Command gcloud.cmd -ErrorAction Stop).Source
$project = 'ai-log-analyzer-511017'
$region = 'us-central1'
$baseUrl = & $gcpCli run services describe $Dashboard --project=$project --region=$region --format='value(status.url)'
if ($LASTEXITCODE -ne 0) { throw 'Dashboard URL lookup failed' }
$identityToken = & $gcpCli auth print-identity-token
if ($LASTEXITCODE -ne 0) { throw 'Identity token failed' }
$payload = @{ filename='adk-smoke-test.txt'; content="2026-10-08T20:00:00Z INFO Application started`n2026-10-08T20:00:01Z ERROR Database connection timed out`n2026-10-08T20:00:02Z WARN Retry scheduled" } | ConvertTo-Json
$uploaded = Invoke-RestMethod -Method Post -Uri "$baseUrl/logs" -Headers @{Authorization="Bearer $identityToken"} -ContentType application/json -Body $payload
$message = @{log_id=$uploaded.id} | ConvertTo-Json -Compress
& $gcpCli pubsub topics publish log-analyzer-dev-investigations --project=$project "--message=$message" --format='value(messageIds)' | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Publish failed' }
$accessToken = & $gcpCli auth print-access-token
if ($LASTEXITCODE -ne 0) { throw 'Access token failed' }
$resultUrl = "https://firestore.googleapis.com/v1/projects/$project/databases/(default)/documents/investigations/$($uploaded.id)"
$completed = $false
for ($attempt=0; $attempt -lt 30; $attempt++) {
    try {
        $result = Invoke-RestMethod -Uri $resultUrl -Headers @{Authorization="Bearer $accessToken"}
        if ($result.fields.status.stringValue -eq 'completed') { $completed=$true; break }
    } catch {
        if ([int]$_.Exception.Response.StatusCode -ne 404) { throw }
    }
    Start-Sleep -Seconds 5
}
if (!$completed) { throw "Investigation incomplete. Inspect Firestore and agent logs for $($uploaded.id)" }
$sdkBin=Split-Path $gcpCli
$env:PATH="$sdkBin;$env:PATH"
$query = "SELECT log_id, severity, model FROM ``$project.log_analyzer_dev.incidents`` WHERE log_id = '$($uploaded.id)'"
$rows = & "$sdkBin\bq.cmd" --project_id=$project --location=$region query --use_legacy_sql=false --maximum_bytes_billed=10000000 --format=json $query
if ($LASTEXITCODE -ne 0) { throw 'BigQuery verification failed' }
$parsed = ($rows -join "`n") | ConvertFrom-Json
if (@($parsed).Count -ne 1) { throw 'Expected exactly one incident row' }
Write-Output "VERIFIED upload -> Pub/Sub -> ADK/Gemini -> Firestore -> BigQuery. log_id=$($uploaded.id)"
Write-Output "Model=$($result.fields.model.stringValue); severity=$($parsed[0].severity)"
