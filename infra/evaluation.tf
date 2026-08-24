resource "google_cloud_run_v2_job" "evaluation" {
  count = var.environment == "prod" ? 0 : 1

  name                = "${local.prefix}-evaluation"
  location            = var.region
  deletion_protection = false

  template {
    task_count = 1

    template {
      service_account = google_service_account.evaluation[0].email
      timeout         = "3600s"
      max_retries     = 0

      containers {
        image   = var.api_image
        command = ["mtg-rag-capture"]
        args = [
          "--suite",
          "/app/evals/mtg_rules_v1.json",
          "--output-gcs-bucket",
          google_storage_bucket.snapshots.name,
          "--output-gcs-prefix",
          "evaluation-captures",
          "--confirm-non-production",
        ]

        resources {
          limits = {
            cpu    = "1"
            memory = "1Gi"
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
    google_secret_manager_secret_iam_member.evaluation_database,
    google_secret_manager_secret_iam_member.evaluation_openai,
    google_storage_bucket_iam_member.evaluation_captures,
  ]
}
