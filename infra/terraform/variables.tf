variable "project_id" {
  type    = string
  default = "ai-log-analyzer-511017"
}

variable "region" {
  type    = string
  default = "us-central1"
}

locals {
  dashboard_service = "log-analyzer-dev"
  agent_service     = "log-analyzer-dev-agent"

  vpc_network         = "log-analyzer-dev-vpc"
  vpc_subnet          = "log-analyzer-dev-subnet"
  egress_deny_fw      = "log-analyzer-dev-egress-deny"
  googleapis_allow_fw = "log-analyzer-dev-googleapis-allow"
  googleapis_route    = "log-analyzer-dev-googleapis"
  dns_zone            = "log-analyzer-dev-googleapis"

  firestore_database = "(default)"

  investigations_topic     = "log-analyzer-dev-investigations"
  investigations_dlq_topic = "log-analyzer-dev-investigations-dlq"
  investigations_sub       = "log-analyzer-dev-investigations-sub"
  investigations_dlq_sub   = "log-analyzer-dev-investigations-dlq-sub"

  bq_dataset = "log_analyzer_dev"
  bq_table   = "incidents"

  raw_logs_bucket = "ai-log-analyzer-511017-raw-logs-dev"

  agent_sa     = "log-analyzer-dev-agent"
  dashboard_sa = "log-analyzer-dev-dashboard"
  push_sa      = "log-analyzer-dev-push"
  build_sa     = "log-analyzer-dev-build"
  ci_sa        = "log-analyzer-dev-ci"
  terraform_sa = "terraform-dev"

  gemini_invoker_role = "logAnalyzerGeminiInvoker"
}
