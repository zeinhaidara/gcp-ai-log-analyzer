resource "google_cloud_run_v2_service" "dashboard" {
  annotations          = {}
  client               = "gcloud"
  client_version       = "591.0.0"
  custom_audiences     = []
  default_uri_disabled = false
  deletion_policy      = "DELETE"
  deletion_protection  = true
  description          = null
  iap_enabled          = false
  ingress              = "INGRESS_TRAFFIC_ALL"
  invoker_iam_disabled = false
  labels               = {}
  launch_stage         = "GA"
  location             = "us-central1"
  name                 = "log-analyzer-dev"
  project              = "ai-log-analyzer-511017"
  ssh_enabled          = false
  tags                 = null
  scaling {
    manual_instance_count = 0
    max_instance_count    = 3
    min_instance_count    = 0
    scaling_mode          = null
  }
  template {
    annotations                   = {}
    encryption_key                = null
    execution_environment         = null
    gpu_zonal_redundancy_disabled = false
    health_check_disabled         = false
    labels = {
      app         = "log-analyzer"
      environment = "dev"
      managed-by  = "cloud-build"
      owner       = "mahmoud"
    }
    max_instance_request_concurrency = 80
    revision                         = null
    service_account                  = "log-analyzer-dev-dashboard@ai-log-analyzer-511017.iam.gserviceaccount.com"
    session_affinity                 = false
    timeout                          = "300s"
    containers {
      args             = []
      base_image_uri   = null
      command          = []
      depends_on       = []
      image            = "us-central1-docker.pkg.dev/ai-log-analyzer-511017/log-analyzer-dev/log-analyzer:d9206f62-3f2e-479e-82ca-b9d14619fc3b"
      name             = null
      sandbox_launcher = false
      working_dir      = null
      env {
        name  = "BIGQUERY_LOCATION"
        value = "us-central1"
      }
      env {
        name  = "BIGQUERY_TABLE"
        value = "ai-log-analyzer-511017.log_analyzer_dev.incidents"
      }
      env {
        name  = "FIRESTORE_COLLECTION"
        value = "logs"
      }
      env {
        name  = "FIRESTORE_DATABASE"
        value = "(default)"
      }
      env {
        name  = "GOOGLE_CLOUD_PROJECT"
        value = "ai-log-analyzer-511017"
      }
      env {
        name  = "INVESTIGATION_TOPIC"
        value = "log-analyzer-dev-investigations"
      }
      env {
        name  = "LOG_BUCKET"
        value = "ai-log-analyzer-511017-raw-logs-dev"
      }
      env {
        name  = "STORAGE_BACKEND"
        value = "gcp"
      }
      ports {
        container_port = 8080
        name           = "http1"
      }
      resources {
        cpu_idle = true
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
        startup_cpu_boost = true
      }
      startup_probe {
        failure_threshold     = 1
        initial_delay_seconds = 0
        period_seconds        = 240
        timeout_seconds       = 240
        tcp_socket {
          port = 8080
        }
      }
    }
    scaling {
      concurrency_utilization = 0
      cpu_utilization         = 0
      max_instance_count      = 1
      min_instance_count      = 0
    }
    vpc_access {
      connector = null
      egress    = "ALL_TRAFFIC"
      network_interfaces {
        network    = "log-analyzer-dev-vpc"
        subnetwork = "log-analyzer-dev-subnet"
        tags       = ["log-analyzer-dev"]
      }
    }
  }
  traffic {
    percent  = 100
    revision = null
    tag      = null
    type     = "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST"
  }
}

resource "google_cloud_run_v2_service" "agent" {
  annotations          = {}
  client               = "gcloud"
  client_version       = "591.0.0"
  custom_audiences     = []
  default_uri_disabled = false
  deletion_policy      = "DELETE"
  deletion_protection  = true
  description          = null
  iap_enabled          = false
  ingress              = "INGRESS_TRAFFIC_ALL"
  invoker_iam_disabled = false
  labels               = {}
  launch_stage         = "GA"
  location             = "us-central1"
  name                 = "log-analyzer-dev-agent"
  project              = "ai-log-analyzer-511017"
  ssh_enabled          = false
  tags                 = null
  scaling {
    manual_instance_count = 0
    max_instance_count    = 3
    min_instance_count    = 0
    scaling_mode          = null
  }
  template {
    annotations                   = {}
    encryption_key                = null
    execution_environment         = null
    gpu_zonal_redundancy_disabled = false
    health_check_disabled         = false
    labels = {
      app         = "log-analyzer"
      environment = "dev"
      managed-by  = "cloud-build"
      owner       = "zein"
    }
    max_instance_request_concurrency = 1
    revision                         = null
    service_account                  = "log-analyzer-dev-agent@ai-log-analyzer-511017.iam.gserviceaccount.com"
    session_affinity                 = false
    timeout                          = "180s"
    containers {
      args             = []
      base_image_uri   = null
      command          = []
      depends_on       = []
      image            = "us-central1-docker.pkg.dev/ai-log-analyzer-511017/log-analyzer-dev/adk-agent:d9206f62-3f2e-479e-82ca-b9d14619fc3b"
      name             = null
      sandbox_launcher = false
      working_dir      = null
      env {
        name  = "BIGQUERY_LOCATION"
        value = "us-central1"
      }
      env {
        name  = "BIGQUERY_TABLE"
        value = "ai-log-analyzer-511017.log_analyzer_dev.incidents"
      }
      env {
        name  = "FIRESTORE_COLLECTION"
        value = "logs"
      }
      env {
        name  = "FIRESTORE_DATABASE"
        value = "(default)"
      }
      env {
        name  = "GEMINI_MODEL"
        value = "gemini-3.1-flash-lite"
      }
      env {
        name  = "GOOGLE_CLOUD_LOCATION"
        value = "global"
      }
      env {
        name  = "GOOGLE_CLOUD_PROJECT"
        value = "ai-log-analyzer-511017"
      }
      env {
        name  = "GOOGLE_GENAI_USE_VERTEXAI"
        value = "true"
      }
      env {
        name  = "LOG_BUCKET"
        value = "ai-log-analyzer-511017-raw-logs-dev"
      }
      ports {
        container_port = 8080
        name           = "http1"
      }
      resources {
        cpu_idle = true
        limits = {
          cpu    = "1"
          memory = "1Gi"
        }
        startup_cpu_boost = true
      }
      startup_probe {
        failure_threshold     = 1
        initial_delay_seconds = 0
        period_seconds        = 240
        timeout_seconds       = 240
        tcp_socket {
          port = 8080
        }
      }
    }
    scaling {
      concurrency_utilization = 0
      cpu_utilization         = 0
      max_instance_count      = 1
      min_instance_count      = 0
    }
    vpc_access {
      connector = null
      egress    = "ALL_TRAFFIC"
      network_interfaces {
        network    = "log-analyzer-dev-vpc"
        subnetwork = "log-analyzer-dev-subnet"
        tags       = ["log-analyzer-dev"]
      }
    }
  }
  traffic {
    percent  = 100
    revision = null
    tag      = null
    type     = "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST"
  }
}
