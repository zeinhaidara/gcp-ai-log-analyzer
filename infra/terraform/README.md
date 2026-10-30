# Terraform notes

Not applied. Cloud Build (`gcloud run deploy`) still owns both Cloud Run services, so nothing here is a live resource yet.

State, once used: GCS bucket `ai-log-analyzer-511017-tfstate`, prefix `dev`.

```hcl
terraform {
  backend "gcs" {
    bucket = "ai-log-analyzer-511017-tfstate"
    prefix = "dev"
  }
}
```

## Agent ingress: internal only

Change `log-analyzer-dev-agent` ingress from `all` to `internal`. Cloud Run IAM (`run.invoker` for the push identity) stays as a second layer.

Why: the agent's only caller is the Pub/Sub push subscription. Its URL does not need to be reachable from the internet.

Still works:
- Pub/Sub push. Cloud Run treats Pub/Sub subscriptions as internal when they are in the same project and target the default `run.app` URL. Both hold here. Source: [Cloud Run ingress](https://docs.cloud.google.com/run/docs/securing/ingress), checked 2026-10-29.
- Dashboard to agent. The dashboard never calls the agent; it publishes the log ID to Pub/Sub.
- `smoke-test.ps1` and `smoke-test-app.ps1`. They call the dashboard, Pub/Sub, Firestore and BigQuery, not the agent.

Stops working:
- Direct requests to the agent URL from a developer machine, including `gcloud run services proxy` to reach `/ready` or `/docs`.

When the service moves under Terraform:

```hcl
resource "google_cloud_run_v2_service" "agent" {
  name     = "log-analyzer-dev-agent"
  location = "us-central1"
  ingress  = "INGRESS_TRAFFIC_INTERNAL_ONLY"
  # remaining settings as deployed by cloudbuild/deploy-dev.yaml
}
```

Until then, an operator applies it once:

```
gcloud run services update log-analyzer-dev-agent --region us-central1 --project ai-log-analyzer-511017 --ingress internal
```

Rollback: the same command with `--ingress all`.

CI: add `--ingress=internal` to the `deploy-agent` step in `cloudbuild/deploy-dev.yaml` so every release states it explicitly (owner: Mahmoud).
