param([string]$Tag = 'dev', [string]$Model = 'gemini-3.1-flash-lite')
$ErrorActionPreference = 'Stop'
$gcpCli = (Get-Command gcloud.cmd -ErrorAction SilentlyContinue).Source
if (!$gcpCli) { $gcpCli = Join-Path $env:LOCALAPPDATA 'Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd' }
if (!(Test-Path -LiteralPath $gcpCli)) { throw 'Install Google Cloud SDK first' }
$sdkBin = Split-Path $gcpCli
$env:PATH = "$sdkBin;$env:PATH"
$project = 'ai-log-analyzer-511017'
$region = 'us-central1'
$service = 'log-analyzer-dev-agent'
$agentAccount = "$service@$project.iam.gserviceaccount.com"
$pushAccount = "log-analyzer-dev-push@$project.iam.gserviceaccount.com"
$image = "$region-docker.pkg.dev/$project/log-analyzer-dev/adk-agent:$Tag"
function Run-Gcloud {
    & $gcpCli @args
    if ($LASTEXITCODE -ne 0) { throw "gcloud failed: $($args[0]) $($args[1])" }
}

Push-Location $PSScriptRoot
try {
    docker build -t $image .
    if ($LASTEXITCODE -ne 0) { throw 'Image build failed' }
    docker run --rm --mount "type=bind,source=$PSScriptRoot\tests,target=/app/tests,readonly" $image python -m unittest discover -s tests -v
    if ($LASTEXITCODE -ne 0) { throw 'Agent tests failed' }
    & $gcpCli auth print-access-token | docker login -u oauth2accesstoken --password-stdin "https://$region-docker.pkg.dev"
    if ($LASTEXITCODE -ne 0) { throw 'Registry login failed' }
    try {
        docker push $image
        if ($LASTEXITCODE -ne 0) { throw 'Image push failed' }
    } finally { docker logout "https://$region-docker.pkg.dev" }

    & "$sdkBin\bq.cmd" show --format=prettyjson "$project`:log_analyzer_dev.incidents" 2>$null
    if ($LASTEXITCODE -ne 0) {
        & "$sdkBin\bq.cmd" --project_id=$project --location=$region mk --table --expiration=0 --time_partitioning_field=completed_at --time_partitioning_type=DAY --time_partitioning_expiration=604800 "$project`:log_analyzer_dev.incidents" bigquery-schema.json
        if ($LASTEXITCODE -ne 0) { throw 'Table creation failed' }
    }
    # Dataset write access already exists; load jobs additionally require jobs.create.
    Run-Gcloud projects add-iam-policy-binding $project "--member=serviceAccount:$agentAccount" --role=roles/bigquery.jobUser --condition=None --quiet
    Run-Gcloud run deploy $service --project=$project --region=$region --image=$image --service-account=$agentAccount --no-allow-unauthenticated --min-instances=0 --max-instances=1 --concurrency=1 --cpu=1 --memory=1Gi --timeout=180 --set-env-vars="GOOGLE_CLOUD_PROJECT=$project,GOOGLE_GENAI_USE_VERTEXAI=true,GOOGLE_CLOUD_LOCATION=global,GEMINI_MODEL=$Model,LOG_BUCKET=$project-raw-logs-dev,FIRESTORE_DATABASE=(default),FIRESTORE_COLLECTION=logs,BIGQUERY_TABLE=$project.log_analyzer_dev.incidents,BIGQUERY_LOCATION=$region" --quiet
    Run-Gcloud run services add-iam-policy-binding $service --project=$project --region=$region "--member=serviceAccount:$pushAccount" --role=roles/run.invoker --quiet
    $serviceUrl = & $gcpCli run services describe $service --project=$project --region=$region --format='value(status.url)'
    if ($LASTEXITCODE -ne 0 -or !$serviceUrl) { throw 'Service URL lookup failed' }
    Run-Gcloud pubsub subscriptions modify-push-config log-analyzer-dev-investigations-sub --project=$project "--push-endpoint=$serviceUrl/pubsub" "--push-auth-service-account=$pushAccount" "--push-auth-token-audience=$serviceUrl"
    Run-Gcloud pubsub subscriptions update log-analyzer-dev-investigations-sub --project=$project --ack-deadline=180
    Write-Output "Deployed private ADK service: $serviceUrl"
    Write-Output "BigQuery table: $project.log_analyzer_dev.incidents"
} finally { Pop-Location }
