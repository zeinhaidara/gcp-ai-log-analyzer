resource "google_firestore_database" "default" {
  app_engine_integration_mode       = "DISABLED"
  concurrency_mode                  = "PESSIMISTIC"
  database_edition                  = "STANDARD"
  delete_protection_state           = "DELETE_PROTECTION_DISABLED"
  deletion_policy                   = "ABANDON"
  location_id                       = "us-central1"
  name                              = "(default)"
  point_in_time_recovery_enablement = "POINT_IN_TIME_RECOVERY_DISABLED"
  project                           = "ai-log-analyzer-511017"
  realtime_updates_mode             = "REALTIME_UPDATES_MODE_ENABLED"
  tags                              = null
  type                              = "FIRESTORE_NATIVE"
}

resource "google_pubsub_topic" "investigations" {
  deletion_policy            = "DELETE"
  kms_key_name               = null
  labels                     = {}
  message_retention_duration = null
  name                       = "log-analyzer-dev-investigations"
  project                    = "ai-log-analyzer-511017"
  tags                       = null
}

resource "google_pubsub_topic" "investigations_dlq" {
  deletion_policy            = "DELETE"
  kms_key_name               = null
  labels                     = {}
  message_retention_duration = null
  name                       = "log-analyzer-dev-investigations-dlq"
  project                    = "ai-log-analyzer-511017"
  tags                       = null
}

resource "google_pubsub_subscription" "investigations_sub" {
  ack_deadline_seconds         = 180
  deletion_policy              = "DELETE"
  enable_exactly_once_delivery = false
  enable_message_ordering      = false
  filter                       = null
  labels                       = {}
  message_retention_duration   = "86400s"
  name                         = "log-analyzer-dev-investigations-sub"
  project                      = "ai-log-analyzer-511017"
  retain_acked_messages        = false
  tags                         = null
  topic                        = "projects/ai-log-analyzer-511017/topics/log-analyzer-dev-investigations"
  dead_letter_policy {
    dead_letter_topic     = "projects/ai-log-analyzer-511017/topics/log-analyzer-dev-investigations-dlq"
    max_delivery_attempts = 5
  }
  expiration_policy {
    ttl = ""
  }
  push_config {
    attributes    = {}
    push_endpoint = "https://log-analyzer-dev-agent-imm5hb2vlq-uc.a.run.app/pubsub"
    oidc_token {
      audience              = "https://log-analyzer-dev-agent-imm5hb2vlq-uc.a.run.app"
      service_account_email = "log-analyzer-dev-push@ai-log-analyzer-511017.iam.gserviceaccount.com"
    }
  }
  retry_policy {
    maximum_backoff = "600s"
    minimum_backoff = "10s"
  }
}

resource "google_pubsub_subscription" "investigations_dlq_sub" {
  ack_deadline_seconds         = 10
  deletion_policy              = "DELETE"
  enable_exactly_once_delivery = false
  enable_message_ordering      = false
  filter                       = null
  labels                       = {}
  message_retention_duration   = "86400s"
  name                         = "log-analyzer-dev-investigations-dlq-sub"
  project                      = "ai-log-analyzer-511017"
  retain_acked_messages        = false
  tags                         = null
  topic                        = "projects/ai-log-analyzer-511017/topics/log-analyzer-dev-investigations-dlq"
  expiration_policy {
    ttl = ""
  }
}

resource "google_bigquery_dataset" "log_analyzer_dev" {
  dataset_id                      = "log_analyzer_dev"
  default_collation               = null
  default_partition_expiration_ms = 0
  default_table_expiration_ms     = 604800000
  delete_contents_on_destroy      = false
  deletion_policy                 = "DELETE"
  description                     = "Log analyzer development incident analytics"
  friendly_name                   = null
  is_case_insensitive             = false
  labels                          = {}
  location                        = "us-central1"
  max_time_travel_hours           = "168"
  project                         = "ai-log-analyzer-511017"
  resource_tags                   = {}
  access {
    domain         = null
    group_by_email = null
    iam_member     = null
    role           = "OWNER"
    special_group  = "projectOwners"
    user_by_email  = null
  }
  access {
    domain         = null
    group_by_email = null
    iam_member     = null
    role           = "OWNER"
    special_group  = null
    user_by_email  = "zeinhaidara@gmail.com"
  }
  access {
    domain         = null
    group_by_email = null
    iam_member     = null
    role           = "READER"
    special_group  = "projectReaders"
    user_by_email  = null
  }
  access {
    domain         = null
    group_by_email = null
    iam_member     = null
    role           = "READER"
    special_group  = null
    user_by_email  = "log-analyzer-dev-dashboard@ai-log-analyzer-511017.iam.gserviceaccount.com"
  }
  access {
    domain         = null
    group_by_email = null
    iam_member     = null
    role           = "WRITER"
    special_group  = "projectWriters"
    user_by_email  = null
  }
  access {
    domain         = null
    group_by_email = null
    iam_member     = null
    role           = "WRITER"
    special_group  = null
    user_by_email  = "log-analyzer-dev-agent@ai-log-analyzer-511017.iam.gserviceaccount.com"
  }
}

resource "google_bigquery_table" "incidents" {
  clustering                   = null
  dataset_id                   = "log_analyzer_dev"
  deletion_policy              = "DELETE"
  deletion_protection          = true
  description                  = null
  friendly_name                = null
  ignore_auto_generated_schema = false
  ignore_schema_changes        = null
  labels                       = {}
  project                      = "ai-log-analyzer-511017"
  require_partition_filter     = null
  resource_tags                = {}
  schema = jsonencode([{
    mode = "REQUIRED"
    name = "log_id"
    type = "STRING"
    }, {
    mode = "REQUIRED"
    name = "completed_at"
    type = "TIMESTAMP"
    }, {
    mode = "REQUIRED"
    name = "severity"
    type = "STRING"
    }, {
    mode = "REQUIRED"
    name = "summary"
    type = "STRING"
    }, {
    mode = "REQUIRED"
    name = "model"
    type = "STRING"
    }, {
    mode = "NULLABLE"
    name = "service_name"
    type = "STRING"
    }, {
    mode = "NULLABLE"
    name = "failure_category"
    type = "STRING"
  }])
  table_id            = "incidents"
  table_metadata_view = null
  time_partitioning {
    expiration_ms = 604800000
    field         = "completed_at"
    type          = "DAY"
  }
}

resource "google_storage_bucket" "raw_logs" {
  default_event_based_hold    = false
  deletion_policy             = "DELETE"
  enable_object_retention     = false
  force_destroy               = false
  labels                      = {}
  location                    = "US-CENTRAL1"
  name                        = "ai-log-analyzer-511017-raw-logs-dev"
  public_access_prevention    = "enforced"
  requester_pays              = false
  storage_class               = "STANDARD"
  uniform_bucket_level_access = true
  hierarchical_namespace {
    enabled = false
  }
  soft_delete_policy {
    retention_duration_seconds = 604800
  }
}
