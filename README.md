# GCP AI Log Analyzer

Upload a synthetic log, replay the incident it records, and review a Gemini investigation of it.

- **Dashboard** (public Cloud Run service `log-analyzer-dev`): uploads, ERROR/WARN counts, incident replay, seven-day reports.
- **Agent** (private Cloud Run service `log-analyzer-dev-agent`): receives a log ID from Pub/Sub, makes one Gemini call through ADK, and saves structured findings.

Findings are tentative suggestions. Use synthetic logs without credentials.

## Incident replay

Upload UTF-8 `.txt`, `.log` or `.jsonl` files (up to 1 MiB), or try one of three built-in scenarios (retry storm, token expiry, payment recovery). Previewing a scenario saves nothing and calls no model.

The replay parser (`dashboard/replay.py`) reads structured text, JSON Lines and Cloud Logging JSON. It builds a timeline and a service map from recorded fields only. A shared trace ID alone does not create a connection, and the first failure shown is not necessarily the root cause. It scans up to 12,000 lines, samples to 1,200 events and maps at most 20 services. Replay makes no model calls.

## Architecture

The dashboard saves the raw log to Cloud Storage and its metadata to Firestore, then publishes only the log ID to Pub/Sub. Pub/Sub pushes it to the private agent, which reads the log, looks up recent BigQuery incidents, makes one Gemini call and writes findings to Firestore and a summary to BigQuery. Both services use Direct VPC egress restricted to Google APIs.

Diagrams: [docs/architecture.md](docs/architecture.md).

## Layout

```
dashboard/                  public dashboard (WSGI): app.py, storage.py, analytics.py, investigations.py,
                            replay.py, static/ (UI and demo logs), tests/, Dockerfile, requirements.txt
agent_service/              agent: service.py, tests/, Dockerfile, bigquery-schema.json,
                            deploy-agent.ps1 (one-time bootstrap), smoke-test*.ps1 (live checks)
evals/                      golden-log eval: fixtures/, golden_logs.py, test_golden_logs.py, adk/
infra/                      scripts/configure-network.ps1, terraform/ (notes, not applied)
docs/                       architecture.md, api.md, analytics-vpc-handoff.md
cloudbuild/                 deploy-dev.yaml, pr-validation.yaml (pipelines)
```

## Run locally

```powershell
cd dashboard
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -c "from wsgiref.simple_server import make_server; from app import application; make_server('127.0.0.1', 8080, application).serve_forever()"
```

Locally the dashboard uses SQLite (`dashboard/data/logs.db`) and shows AI as disabled. Cloud Run sets `STORAGE_BACKEND=gcp` and the resource variables in `cloudbuild/deploy-dev.yaml`.

## Tests

| Component | Command | Notes |
| --- | --- | --- |
| Dashboard | `cd dashboard && python -m unittest discover -s tests -v` | `dashboard/requirements.txt` |
| Agent | `cd agent_service && python -m unittest discover -s tests -v` | separate venv with `agent_service/requirements.txt` |
| Eval scorer and judge | `python -m unittest discover -s evals -v` | needs only `pydantic`; the judge is mocked, no cloud access |

Security checks, as CI runs them: from `dashboard`, `bandit -q app.py storage.py analytics.py investigations.py replay.py`; from `agent_service`, `bandit -q service.py`.

## Golden-log eval

Four synthetic logs in `evals/fixtures/` each have an `.expected.json` with a minimum (and optional maximum) severity and keywords the summary or likely cause must mention. These calls reach Vertex AI and cost money. They need the agent dependencies and `GOOGLE_GENAI_USE_VERTEXAI`, `GOOGLE_CLOUD_PROJECT` and `GOOGLE_CLOUD_LOCATION`.

```
python evals/golden_logs.py --threshold 0.8
adk eval evals/adk/log_investigator evals/adk/golden-logs.evalset.json --config_file_path evals/adk/eval-config.json
```

A fixture passes only if the rule-based scorer passes and a Gemini judge on Vertex AI agrees the findings fit the log and expectations. The judge uses the model set in `evals/adk/eval-config.json`; any judge error counts as a failure. `--no-judge` runs the scorer alone. `golden_logs.py` exits non-zero below the threshold, and a crash counts as a failure. The ADK eval uses rubric-based scoring with a judge model. Regenerate its eval set from the fixtures with `python evals/golden_logs.py --write-adk-evalset`. Neither eval runs in CI yet.

## Endpoints

The dashboard serves the UI and a JSON API. The agent exposes `GET /health` (liveness), `GET /ready` (Firestore, Storage and BigQuery checks) and `POST /pubsub`, all behind IAM. Full list: [docs/api.md](docs/api.md).

## Deployment

| File | Trigger | Does |
| --- | --- | --- |
| `cloudbuild/pr-validation.yaml` | PR into `dev` or `main` | tests, Bandit, pip-audit, image build and Trivy scan for both services |
| `cloudbuild/deploy-dev.yaml` | push to `dev` | same checks, then publish both images and deploy the agent, then the dashboard |

Work on a `zein/...` branch, PR into `dev` (merging deploys), then promote to protected `main`. No production pipeline exists. Mahmoud owns both pipeline files. Runtime identities authenticate through ADC; there are no key files.

## Infrastructure

Project `ai-log-analyzer-511017`, region `us-central1`.

| Resource | Name |
| --- | --- |
| Cloud Run | `log-analyzer-dev`, `log-analyzer-dev-agent` |
| Artifact Registry | `log-analyzer-dev` |
| Raw-log bucket | `ai-log-analyzer-511017-raw-logs-dev` |
| Firestore | `(default)`: `logs`, `investigations` |
| Pub/Sub topic | `log-analyzer-dev-investigations` |
| BigQuery | `ai-log-analyzer-511017.log_analyzer_dev.incidents`, partitions expire after 7 days |

Terraform state: bucket `ai-log-analyzer-511017-tfstate`, prefix `dev`. Nothing is applied yet; planned changes are in [infra/terraform](infra/terraform/README.md). Details: [agent](agent_service/README.md), [analytics and VPC](docs/analytics-vpc-handoff.md).

## Known gaps

- The dashboard is public and unauthenticated. `GET /logs` lists recent uploads and `GET /logs/{id}` returns any upload's content.
- No upload rate limit or budget alert. Instance limits cap parallelism, not spend.
- Identical uploads each trigger a Gemini call; content-hash reuse is planned.
- Service and category detection (`classify_log`) is keyword-based with three categories. Unmatched logs are `unclassified` and get less history.
- Agent ingress is `all`; internal-only is documented but not applied.
- No VPC Service Controls perimeter.
- Firestore documents and raw logs have no retention cleanup.
- A crash after the model responds but before findings are saved repeats a paid call.
- The golden-log evals have not been run against Vertex AI and are not in CI.
