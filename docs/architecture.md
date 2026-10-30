# Architecture

## Data flow

```mermaid
flowchart TB
  User[User uploads log] --> Dashboard[Cloud Run dashboard]
  Dashboard -->|raw file| Storage[Cloud Storage]
  Dashboard -->|metadata and counts| Logs[Firestore logs]
  Dashboard -->|log ID only| Topic[Pub/Sub]
  Topic -->|authenticated push| Agent[Private Cloud Run agent]
  Storage -->|raw log| Agent
  BQ[BigQuery incidents] -->|up to five recent matches| Agent
  Agent -->|log and history| Gemini[Gemini on Vertex AI]
  Gemini -->|structured findings| Agent
  Agent -->|status and findings| Findings[Firestore investigations]
  Agent -->|incident summary| BQ
  Findings -->|API polling| Dashboard
  BQ -->|seven-day aggregates| Dashboard
```

The dashboard stores the file and metadata before it publishes `{"log_id": "UUID"}`. Raw text never enters the queue. The agent sends Gemini the first 24,000 characters, with numbered lines. The model has no tools; application code does every read and write. A Firestore lease and a deterministic BigQuery job ID make repeated Pub/Sub deliveries safe.

## Network

```mermaid
flowchart TB
  User[User browser] -->|public HTTPS| Dashboard[Cloud Run dashboard]
  PubSub[Pub/Sub push] -->|IAM-authenticated| Agent[Cloud Run agent]
  Dashboard -->|Direct VPC egress| Subnet
  Agent -->|Direct VPC egress| Subnet
  subgraph VPC[log-analyzer-dev-vpc]
    Subnet["log-analyzer-dev-subnet 10.42.0.0/24"]
    Firewall["Egress: allow TCP 443 to 199.36.153.8/30, deny other IPv4"]
    Subnet --> Firewall
  end
  Firewall -->|private.googleapis.com| APIs["Storage · Firestore · BigQuery · Pub/Sub · Vertex AI"]
```

Private DNS zone `log-analyzer-dev-googleapis` resolves Google API names to `private.googleapis.com`. No NAT or VPC connector is used. IAM controls data access; this is not a VPC Service Controls perimeter. Provisioned by `infra/scripts/configure-network.ps1`.

Details: [analytics and VPC handoff](analytics-vpc-handoff.md), [planned ingress change](../infra/terraform/README.md).
