output "api_ip_address" {
  description = "Create the API domain A record at this address before the certificate can become active."
  value       = var.public_delivery_mode == "load_balancer" ? google_compute_global_address.api[0].address : null
}

output "api_url" {
  description = "Public API base after the selected delivery path is provisioned."
  value       = var.public_delivery_mode == "load_balancer" ? "https://${var.api_domain}" : var.frontend_origin
}

output "artifact_repository" {
  description = "Artifact Registry repository used by the delivery pipeline."
  value       = google_artifact_registry_repository.containers.name
}

output "cloud_sql_connection_name" {
  description = "Cloud SQL instance connection name used when creating the database URL secret."
  value       = google_sql_database_instance.postgres.connection_name
}

output "database_name" {
  value = google_sql_database.application.name
}

output "openai_secret_name" {
  value = google_secret_manager_secret.openai_api_key.secret_id
}

output "database_url_secret_name" {
  value = google_secret_manager_secret.database_url.secret_id
}

output "snapshot_bucket" {
  value = google_storage_bucket.snapshots.name
}

output "migration_job_name" {
  description = "Execute this Cloud Run job before directing traffic to a new schema-dependent revision."
  value       = google_cloud_run_v2_job.migration.name
}

output "ingestion_job_name" {
  value = google_cloud_run_v2_job.ingestion.name
}

output "evaluation_job_name" {
  description = "Development-only same-region evaluation capture job."
  value       = try(google_cloud_run_v2_job.evaluation[0].name, null)
}
