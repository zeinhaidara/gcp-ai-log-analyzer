param([switch]$AttachServices)
$ErrorActionPreference = 'Stop'
$gcpCli = Join-Path $env:LOCALAPPDATA 'Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd'
$project = 'ai-log-analyzer-511017'
$region = 'us-central1'
$network = 'log-analyzer-dev-vpc'
$subnet = 'log-analyzer-dev-subnet'
function Invoke-Gcloud {
    & $gcpCli @args
    if ($LASTEXITCODE -ne 0) { throw "gcloud failed: $($args[0]) $($args[1])" }
}
function Exists-Gcloud {
    & $gcpCli @args --project=$project --quiet 2>$null | Out-Null
    return $LASTEXITCODE -eq 0
}
Invoke-Gcloud services enable compute.googleapis.com dns.googleapis.com --project=$project --quiet
if (!(Exists-Gcloud compute networks describe $network)) {
    Invoke-Gcloud compute networks create $network --subnet-mode=custom --bgp-routing-mode=regional --project=$project --quiet
}
if (!(Exists-Gcloud compute networks subnets describe $subnet --region=$region)) {
    Invoke-Gcloud compute networks subnets create $subnet --network=$network --region=$region --range=10.42.0.0/24 --enable-private-ip-google-access --project=$project --quiet
}
Invoke-Gcloud compute networks subnets update $subnet --region=$region --enable-private-ip-google-access --project=$project --quiet
if (!(Exists-Gcloud dns managed-zones describe log-analyzer-dev-googleapis)) {
    Invoke-Gcloud dns managed-zones create log-analyzer-dev-googleapis --dns-name=googleapis.com. --description='Private Google APIs for log analyzer' --visibility=private --networks=$network --project=$project --quiet
}
$recordAction = if (Exists-Gcloud dns record-sets describe private.googleapis.com. --zone=log-analyzer-dev-googleapis --type=A) { 'update' } else { 'create' }
Invoke-Gcloud dns record-sets $recordAction private.googleapis.com. --zone=log-analyzer-dev-googleapis --type=A --ttl=300 '--rrdatas=199.36.153.8,199.36.153.9,199.36.153.10,199.36.153.11' --project=$project --quiet
$recordAction = if (Exists-Gcloud dns record-sets describe '*.googleapis.com.' --zone=log-analyzer-dev-googleapis --type=CNAME) { 'update' } else { 'create' }
Invoke-Gcloud dns record-sets $recordAction '*.googleapis.com.' --zone=log-analyzer-dev-googleapis --type=CNAME --ttl=300 --rrdatas=private.googleapis.com. --project=$project --quiet
if (!(Exists-Gcloud compute routes describe log-analyzer-dev-googleapis)) {
    Invoke-Gcloud compute routes create log-analyzer-dev-googleapis --network=$network --destination-range=199.36.153.8/30 --next-hop-gateway=default-internet-gateway --priority=100 --project=$project --quiet
}
if (!(Exists-Gcloud compute firewall-rules describe log-analyzer-dev-googleapis-allow)) {
    Invoke-Gcloud compute firewall-rules create log-analyzer-dev-googleapis-allow --network=$network --direction=EGRESS --priority=900 --action=ALLOW --rules=tcp:443 --destination-ranges=199.36.153.8/30 --target-tags=log-analyzer-dev --project=$project --quiet
}
if (!(Exists-Gcloud compute firewall-rules describe log-analyzer-dev-egress-deny)) {
    Invoke-Gcloud compute firewall-rules create log-analyzer-dev-egress-deny --network=$network --direction=EGRESS --priority=1000 --action=DENY --rules=all --destination-ranges=0.0.0.0/0 --target-tags=log-analyzer-dev --project=$project --quiet
}
if ($AttachServices) {
    foreach ($service in @('log-analyzer-dev', 'log-analyzer-dev-agent')) {
        Invoke-Gcloud run services update $service --network=$network --subnet=$subnet --vpc-egress=all-traffic --network-tags=log-analyzer-dev --region=$region --project=$project --quiet
    }
}
