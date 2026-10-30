resource "google_service_account" "agent" {
  account_id                   = "log-analyzer-dev-agent"
  create_ignore_already_exists = null
  deletion_policy              = "DELETE"
  description                  = null
  disabled                     = false
  display_name                 = "Log Analyzer Dev ADK Agent"
  project                      = "ai-log-analyzer-511017"
}

resource "google_service_account" "dashboard" {
  account_id                   = "log-analyzer-dev-dashboard"
  create_ignore_already_exists = null
  deletion_policy              = "DELETE"
  description                  = null
  disabled                     = false
  display_name                 = "Log Analyzer Dev Dashboard"
  project                      = "ai-log-analyzer-511017"
}

resource "google_service_account" "push" {
  account_id                   = "log-analyzer-dev-push"
  create_ignore_already_exists = null
  deletion_policy              = "DELETE"
  description                  = null
  disabled                     = false
  display_name                 = "Log Analyzer Dev PubSub Push"
  project                      = "ai-log-analyzer-511017"
}

resource "google_service_account" "build" {
  account_id                   = "log-analyzer-dev-build"
  create_ignore_already_exists = null
  deletion_policy              = "DELETE"
  description                  = null
  disabled                     = false
  display_name                 = "Log Analyzer Dev Build"
  project                      = "ai-log-analyzer-511017"
}

resource "google_service_account" "ci" {
  account_id                   = "log-analyzer-dev-ci"
  create_ignore_already_exists = null
  deletion_policy              = "DELETE"
  description                  = null
  disabled                     = false
  display_name                 = "Log Analyzer Dev PR Validation"
  project                      = "ai-log-analyzer-511017"
}

resource "google_service_account" "terraform" {
  account_id                   = "terraform-dev"
  create_ignore_already_exists = null
  deletion_policy              = "DELETE"
  description                  = null
  disabled                     = false
  display_name                 = "Terraform dev"
  project                      = "ai-log-analyzer-511017"
}

resource "google_project_iam_custom_role" "gemini_invoker" {
  deletion_policy = "DELETE"
  description     = "Only model inference; no Vertex AI administration or resource creation"
  permissions     = ["aiplatform.endpoints.predict"]
  project         = "ai-log-analyzer-511017"
  role_id         = "logAnalyzerGeminiInvoker"
  stage           = "GA"
  title           = "Log Analyzer Gemini Invoker"
}

resource "google_project_iam_member" "agent_bigquery_job_user" {
  member  = "serviceAccount:log-analyzer-dev-agent@ai-log-analyzer-511017.iam.gserviceaccount.com"
  project = "ai-log-analyzer-511017"
  role    = "roles/bigquery.jobUser"
}

resource "google_project_iam_member" "dashboard_bigquery_job_user" {
  member  = "serviceAccount:log-analyzer-dev-dashboard@ai-log-analyzer-511017.iam.gserviceaccount.com"
  project = "ai-log-analyzer-511017"
  role    = "roles/bigquery.jobUser"
}

resource "google_project_iam_member" "agent_datastore_user" {
  member  = "serviceAccount:log-analyzer-dev-agent@ai-log-analyzer-511017.iam.gserviceaccount.com"
  project = "ai-log-analyzer-511017"
  role    = "roles/datastore.user"
  condition {
    description = "Agent can read and write only the existing default Firestore database."
    expression  = "resource.name == \"projects/ai-log-analyzer-511017/databases/(default)\""
    title       = "agent-default-firestore"
  }
}

resource "google_project_iam_member" "dashboard_datastore_user" {
  member  = "serviceAccount:log-analyzer-dev-dashboard@ai-log-analyzer-511017.iam.gserviceaccount.com"
  project = "ai-log-analyzer-511017"
  role    = "roles/datastore.user"
}

resource "google_project_iam_member" "agent_gemini_invoker" {
  member  = "serviceAccount:log-analyzer-dev-agent@ai-log-analyzer-511017.iam.gserviceaccount.com"
  project = "ai-log-analyzer-511017"
  role    = "projects/ai-log-analyzer-511017/roles/logAnalyzerGeminiInvoker"
}

resource "google_storage_bucket_iam_member" "agent_object_viewer" {
  bucket = "b/ai-log-analyzer-511017-raw-logs-dev"
  member = "serviceAccount:log-analyzer-dev-agent@ai-log-analyzer-511017.iam.gserviceaccount.com"
  role   = "roles/storage.objectViewer"
}

resource "google_storage_bucket_iam_member" "dashboard_object_user" {
  bucket = "b/ai-log-analyzer-511017-raw-logs-dev"
  member = "serviceAccount:log-analyzer-dev-dashboard@ai-log-analyzer-511017.iam.gserviceaccount.com"
  role   = "roles/storage.objectUser"
}

resource "google_cloud_run_v2_service_iam_member" "agent_invoker" {
  location = "us-central1"
  member   = "serviceAccount:log-analyzer-dev-push@ai-log-analyzer-511017.iam.gserviceaccount.com"
  name     = "projects/ai-log-analyzer-511017/locations/us-central1/services/log-analyzer-dev-agent"
  project  = "ai-log-analyzer-511017"
  role     = "roles/run.invoker"
}

resource "google_cloud_run_v2_service_iam_member" "dashboard_public" {
  location = "us-central1"
  member   = "allUsers"
  name     = "projects/ai-log-analyzer-511017/locations/us-central1/services/log-analyzer-dev"
  project  = "ai-log-analyzer-511017"
  role     = "roles/run.invoker"
}
