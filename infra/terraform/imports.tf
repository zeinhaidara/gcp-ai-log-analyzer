# Plan-only bootstrap: describes the existing dev project so `terraform plan`
# converges to zero changes. Nothing here is applied or imported into state.

import {
  to = google_cloud_run_v2_service.dashboard
  id = "projects/${var.project_id}/locations/${var.region}/services/${local.dashboard_service}"
}

import {
  to = google_cloud_run_v2_service.agent
  id = "projects/${var.project_id}/locations/${var.region}/services/${local.agent_service}"
}

import {
  to = google_compute_network.dev_vpc
  id = "projects/${var.project_id}/global/networks/${local.vpc_network}"
}

import {
  to = google_compute_subnetwork.dev_subnet
  id = "projects/${var.project_id}/regions/${var.region}/subnetworks/${local.vpc_subnet}"
}

import {
  to = google_compute_firewall.egress_deny
  id = "projects/${var.project_id}/global/firewalls/${local.egress_deny_fw}"
}

import {
  to = google_compute_firewall.googleapis_allow
  id = "projects/${var.project_id}/global/firewalls/${local.googleapis_allow_fw}"
}

import {
  to = google_compute_route.googleapis
  id = "projects/${var.project_id}/global/routes/${local.googleapis_route}"
}

import {
  to = google_dns_managed_zone.googleapis
  id = "projects/${var.project_id}/managedZones/${local.dns_zone}"
}

import {
  to = google_dns_record_set.googleapis_cname
  id = "projects/${var.project_id}/managedZones/${local.dns_zone}/rrsets/*.googleapis.com./CNAME"
}

import {
  to = google_dns_record_set.googleapis_a
  id = "projects/${var.project_id}/managedZones/${local.dns_zone}/rrsets/private.googleapis.com./A"
}

import {
  to = google_firestore_database.default
  id = "projects/${var.project_id}/databases/${local.firestore_database}"
}

import {
  to = google_pubsub_topic.investigations
  id = "projects/${var.project_id}/topics/${local.investigations_topic}"
}

import {
  to = google_pubsub_topic.investigations_dlq
  id = "projects/${var.project_id}/topics/${local.investigations_dlq_topic}"
}

import {
  to = google_pubsub_subscription.investigations_sub
  id = "projects/${var.project_id}/subscriptions/${local.investigations_sub}"
}

import {
  to = google_pubsub_subscription.investigations_dlq_sub
  id = "projects/${var.project_id}/subscriptions/${local.investigations_dlq_sub}"
}

import {
  to = google_bigquery_dataset.log_analyzer_dev
  id = "projects/${var.project_id}/datasets/${local.bq_dataset}"
}

import {
  to = google_bigquery_table.incidents
  id = "projects/${var.project_id}/datasets/${local.bq_dataset}/tables/${local.bq_table}"
}

import {
  to = google_storage_bucket.raw_logs
  id = local.raw_logs_bucket
}

import {
  to = google_service_account.agent
  id = "projects/${var.project_id}/serviceAccounts/${local.agent_sa}@${var.project_id}.iam.gserviceaccount.com"
}

import {
  to = google_service_account.dashboard
  id = "projects/${var.project_id}/serviceAccounts/${local.dashboard_sa}@${var.project_id}.iam.gserviceaccount.com"
}

import {
  to = google_service_account.push
  id = "projects/${var.project_id}/serviceAccounts/${local.push_sa}@${var.project_id}.iam.gserviceaccount.com"
}

import {
  to = google_service_account.build
  id = "projects/${var.project_id}/serviceAccounts/${local.build_sa}@${var.project_id}.iam.gserviceaccount.com"
}

import {
  to = google_service_account.ci
  id = "projects/${var.project_id}/serviceAccounts/${local.ci_sa}@${var.project_id}.iam.gserviceaccount.com"
}

import {
  to = google_service_account.terraform
  id = "projects/${var.project_id}/serviceAccounts/${local.terraform_sa}@${var.project_id}.iam.gserviceaccount.com"
}

import {
  to = google_project_iam_custom_role.gemini_invoker
  id = "projects/${var.project_id}/roles/${local.gemini_invoker_role}"
}

import {
  to = google_storage_bucket_iam_member.agent_object_viewer
  id = "b/${local.raw_logs_bucket} roles/storage.objectViewer serviceAccount:${local.agent_sa}@${var.project_id}.iam.gserviceaccount.com"
}

import {
  to = google_storage_bucket_iam_member.dashboard_object_user
  id = "b/${local.raw_logs_bucket} roles/storage.objectUser serviceAccount:${local.dashboard_sa}@${var.project_id}.iam.gserviceaccount.com"
}

import {
  to = google_project_iam_member.agent_bigquery_job_user
  id = "${var.project_id} roles/bigquery.jobUser serviceAccount:${local.agent_sa}@${var.project_id}.iam.gserviceaccount.com"
}

import {
  to = google_project_iam_member.dashboard_bigquery_job_user
  id = "${var.project_id} roles/bigquery.jobUser serviceAccount:${local.dashboard_sa}@${var.project_id}.iam.gserviceaccount.com"
}

import {
  to = google_project_iam_member.agent_datastore_user
  id = "${var.project_id} roles/datastore.user serviceAccount:${local.agent_sa}@${var.project_id}.iam.gserviceaccount.com"
}

import {
  to = google_project_iam_member.dashboard_datastore_user
  id = "${var.project_id} roles/datastore.user serviceAccount:${local.dashboard_sa}@${var.project_id}.iam.gserviceaccount.com"
}

import {
  to = google_project_iam_member.agent_gemini_invoker
  id = "${var.project_id} projects/${var.project_id}/roles/${local.gemini_invoker_role} serviceAccount:${local.agent_sa}@${var.project_id}.iam.gserviceaccount.com"
}

import {
  to = google_cloud_run_v2_service_iam_member.agent_invoker
  id = "projects/${var.project_id}/locations/${var.region}/services/${local.agent_service} roles/run.invoker serviceAccount:${local.push_sa}@${var.project_id}.iam.gserviceaccount.com"
}

import {
  to = google_cloud_run_v2_service_iam_member.dashboard_public
  id = "projects/${var.project_id}/locations/${var.region}/services/${local.dashboard_service} roles/run.invoker allUsers"
}
