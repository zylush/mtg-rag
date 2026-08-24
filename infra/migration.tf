resource "google_cloud_run_v2_job" "migration" {
  name                = "${local.prefix}-migration"
  location            = var.region
  deletion_protection = var.environment == "prod"

  template {
    task_count = 1

    template {
      service_account = google_service_account.ingestion.email
      timeout         = "900s"
      max_retries     = 0

      containers {
        image   = coalesce(var.migration_image, var.api_image)
        command = ["alembic"]
        args    = ["upgrade", "head"]

        resources {
          limits = {
            cpu    = "1"
            memory = "1Gi"
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
          name  = "MTG_RAG_FRONTEND_ORIGIN"
          value = var.frontend_origin
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
  ]
}
