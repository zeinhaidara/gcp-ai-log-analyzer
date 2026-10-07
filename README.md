# GCP AI Log Analyzer

AI log analyzer and incident investigation agent built in phases with Google ADK and Gemini on Vertex AI, Cloud Run, Firestore, Cloud Storage, Pub/Sub, and BigQuery. GitHub hosts the source; Cloud Build tests, scans, and publishes container images to Artifact Registry.

## Working today

- Browser dashboard: upload UTF-8 `.txt` files and view recent logs and content.
- UTC upload timestamps, processing status, and ERROR/WARN line counts.
- Input validation, parameterized database queries, safe text rendering, and a 1 MiB request limit.
- SQLite storage for the local learning phase, a health endpoint, and a non-root Docker image.
- Cloud Build pipeline with API tests, Bandit source checks, pip-audit dependency checks, and Trivy image vulnerability/secret scanning.

ADK, Gemini, Firestore, Cloud Storage, Pub/Sub, and BigQuery are planned integrations, not implemented yet. The current analysis counts lines containing ERROR or WARN; it does not infer incident causes.

## Local run (PowerShell)

With Python 3.12 installed:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Gunicorn runs in the Linux container. For local Windows development, start the standard-library WSGI server:

```powershell
python -c "from wsgiref.simple_server import make_server; from app import application; make_server('127.0.0.1', 8080, application).serve_forever()"
```

Open http://localhost:8080. Records are stored in `data/logs.db`. Set `DATABASE_PATH` to change this location.

Alternatively, run the container with a persistent local volume:

```powershell
docker build -t log-analyzer .
docker run --rm -p 8080:8080 -v log-analyzer-data:/app/data log-analyzer
```

## API

| Endpoint | Purpose |
| --- | --- |
| `GET /health` | Health check |
| `POST /logs` | JSON body: `filename` and `content` |
| `GET /logs` | Latest 100 records, excluding raw content |
| `GET /logs/{id}` | Record and full content |

```powershell
$body = @{ filename = 'api.txt'; content = "ERROR database timeout`nWARN retrying" } | ConvertTo-Json
Invoke-RestMethod http://localhost:8080/logs -Method Post -ContentType 'application/json' -Body $body
```

## Test and security checks

```powershell
python -m unittest discover -s tests -v
pip install bandit pip-audit
bandit -q app.py
pip-audit -r requirements.txt
```

## Cloud Build: CI and image publication

```text
GitHub push to main
  -> API tests -> Bandit -> pip-audit
  -> Docker build -> Trivy image scan
  -> Artifact Registry (unique BUILD_ID tag)
```

Every step must succeed before publishing. Trivy blocks HIGH and CRITICAL vulnerabilities and matching secret findings, including vulnerabilities without available fixes. No failure is ignored. The image is exported to a tar file so the scanner can inspect it before it is pushed. Scanner images and audit tools currently use current releases for simplicity; pin tested versions/digests and lock dependencies when hardening the pipeline.

Use **Artifact Registry**, Google's current container image registry. Publishing an image is artifact delivery; deploying a Cloud Run revision is the next CD step.

### One-time GCP setup

Install the Google Cloud CLI, sign in, and use a billing-enabled project. Replace `YOUR_PROJECT_ID`:

```powershell
$projectId = 'YOUR_PROJECT_ID'
$region = 'us-central1'
gcloud auth login
gcloud config set project $projectId
gcloud services enable cloudbuild.googleapis.com artifactregistry.googleapis.com logging.googleapis.com run.googleapis.com
gcloud artifacts repositories create log-analyzer --repository-format=docker --location=$region
gcloud iam service-accounts create log-analyzer-build --display-name='Log Analyzer Cloud Build'
$buildAccount = "log-analyzer-build@$projectId.iam.gserviceaccount.com"
gcloud artifacts repositories add-iam-policy-binding log-analyzer --location=$region --member="serviceAccount:$buildAccount" --role=roles/artifactregistry.writer
gcloud projects add-iam-policy-binding $projectId --member="serviceAccount:$buildAccount" --role=roles/logging.logWriter
```

In **Cloud Build > Repositories**, connect this GitHub repository. Create a push trigger for branch `^main$`, select `cloudbuild.yaml`, and select the `log-analyzer-build` service account. The person creating the trigger needs permission to act as that account. Cloud Build API/service-agent permissions and organization policies must also allow builds. Limit the trigger to trusted branches; PR validation should use a separate pipeline without publishing credentials.

For a manual build, source staging also needs storage permissions. Use a dedicated bucket:

```powershell
$sourceBucket = "$projectId-log-analyzer-build-source"
gcloud storage buckets create "gs://$sourceBucket" --location=$region --uniform-bucket-level-access
gcloud storage buckets add-iam-policy-binding "gs://$sourceBucket" --member="serviceAccount:$buildAccount" --role=roles/storage.objectViewer
gcloud builds submit --config=cloudbuild.yaml --region=$region --gcs-source-staging-dir="gs://$sourceBucket/source" --service-account="projects/$projectId/serviceAccounts/$buildAccount"
```

The submitting user needs build creation, source upload, and service-account impersonation permissions. Successful builds publish:

```text
us-central1-docker.pkg.dev/PROJECT_ID/log-analyzer/log-analyzer:BUILD_ID
```

## Next layers

1. **Persistent cloud storage:** Firestore metadata and Cloud Storage raw files. SQLite on Cloud Run is ephemeral and cannot coordinate multiple instances; complete this before a persistent cloud deployment.
2. **Cloud Run CD:** deploy the scanned image after publishing, using a dedicated runtime service account, then check `/health`. Add narrowly scoped deployment and service-account permissions to the build account.
3. **Pub/Sub processing:** asynchronous jobs with idempotency, retries, and a dead-letter queue.
4. **ADK investigation agent:** Gemini through Vertex AI, with tools to read a log, find related logs, and look up runbooks. Save evidence and suggested checks in Firestore.
5. **BigQuery:** historical severity/error trends and an additional read-only agent investigation tool.
6. **Access and operations:** authentication before real log uploads, Secret Manager for external credentials, Cloud Logging/Monitoring and failure alerts.
7. **Networking lab:** add a private processing VM and VPC connectivity only when that learning phase needs them.

Treat uploaded logs as untrusted input, including when adding agent tools. The agent should initially investigate with read-only permissions. This demo has no authentication; use synthetic logs during development.

## References

- [Cloud Build container builds and publication](https://docs.cloud.google.com/build/docs/building/build-containers)
- [Gemini on Vertex AI](https://docs.cloud.google.com/vertex-ai/generative-ai/docs)
- [Google ADK](https://google.github.io/adk-docs/)
- [Trivy image scanning](https://trivy.dev/docs/dev/references/configuration/cli/trivy_image/)
