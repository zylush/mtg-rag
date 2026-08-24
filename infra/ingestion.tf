resource "google_cloud_run_v2_job" "ingestion" {
  name                = "${local.prefix}-ingestion"
  location            = var.region
  deletion_protection = var.environment == "prod"

  template {
    task_count = 1

    template {
      service_account = google_service_account.ingestion.email
      timeout         = "3600s"
      max_retries     = 0

      containers {
        image   = var.api_image
        command = ["mtg-rag-ingest"]
        args    = var.environment == "prod" ? [] : ["cards"]

        resources {
          limits = {
            cpu    = "2"
            memory = "4Gi"
          }
        }

        dynamic "env" {
          for_each = local.runtime_environment
          content {
            name  = env.key
            value = env.value
          }
        }

        env {
          name = "MTG_RAG_DATABASE_URL"
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.database_url.secret_id
              version = var.database_url_secret_version
            }
          }
        }

        env {
          name = "MTG_RAG_OPENAI_API_KEY"
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.openai_api_key.secret_id
              version = var.openai_secret_version
            }
          }
        }

        volume_mounts {
          name       = "cloudsql"
          mount_path = "/cloudsql"
        }
      }

      volumes {
        name = "cloudsql"
        cloud_sql_instance {
          instances = [google_sql_database_instance.postgres.connection_name]
        }
      }
    }
  }

  depends_on = [
    google_project_service.required,
    google_secret_manager_secret_iam_member.ingestion_database,
    google_secret_manager_secret_iam_member.ingestion_openai,
    google_storage_bucket_iam_member.ingestion_snapshots,
  ]
}

resource "google_cloud_run_v2_job_iam_member" "scheduler_invoker" {
  project  = var.project_id
  location = google_cloud_run_v2_job.ingestion.location
  name     = google_cloud_run_v2_job.ingestion.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.scheduler.email}"
}

resource "google_cloud_scheduler_job" "ingestion" {
  name             = "${local.prefix}-ingestion"
  description      = "Daily refresh of WotC and Scryfall corpora"
  region           = var.region
  schedule         = "0 18 * * *"
  time_zone        = "Etc/UTC"
  attempt_deadline = "180s"

  retry_config {
    retry_count          = 1
    min_backoff_duration = "30s"
    max_backoff_duration = "300s"
    max_retry_duration   = "600s"
  }

  http_target {
    http_method = "POST"
    uri         = "https://run.googleapis.com/v2/projects/${var.project_id}/locations/${var.region}/jobs/${google_cloud_run_v2_job.ingestion.name}:run"

    oauth_token {
      service_account_email = google_service_account.scheduler.email
      scope                 = "https://www.googleapis.com/auth/cloud-platform"
    }
  }

  depends_on = [
    google_cloud_run_v2_job_iam_member.scheduler_invoker,
    google_project_service.required,
  ]
}
