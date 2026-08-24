locals {
  runtime_environment = {
    MTG_RAG_ENVIRONMENT                         = var.environment
    MTG_RAG_FRONTEND_ORIGIN                     = var.frontend_origin
    MTG_RAG_OPENAI_GENERATION_MODEL             = var.generation_model
    MTG_RAG_OPENAI_EMBEDDING_MODEL              = var.embedding_model
    MTG_RAG_EMBEDDING_DIMENSIONS                = tostring(var.embedding_dimensions)
    MTG_RAG_CONVERSATION_CONTEXT_ENABLED        = tostring(var.conversation_context_enabled)
    MTG_RAG_CONVERSATION_CONTEXT_MAX_MESSAGES   = tostring(var.conversation_context_max_messages)
    MTG_RAG_CONVERSATION_CONTEXT_MAX_CHARACTERS = tostring(var.conversation_context_max_characters)
    MTG_RAG_GCP_PROJECT_ID                      = var.project_id
    MTG_RAG_GCS_SNAPSHOT_BUCKET                 = google_storage_bucket.snapshots.name
    MTG_RAG_LOG_LEVEL                           = "INFO"
  }
}

resource "google_cloud_run_v2_service" "api" {
  name                = "${local.prefix}-api"
  location            = var.region
  ingress             = var.public_delivery_mode == "load_balancer" ? "INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER" : "INGRESS_TRAFFIC_ALL"
  deletion_protection = var.environment == "prod"

  template {
    service_account                  = google_service_account.api.email
    timeout                          = "40s"
    max_instance_request_concurrency = var.cloud_run_concurrency

    scaling {
      min_instance_count = 0
      max_instance_count = var.cloud_run_max_instances
    }

    containers {
      image = var.api_image

      resources {
        limits = {
          cpu    = "1"
          memory = "1Gi"
        }
        cpu_idle = true
      }

      ports {
        container_port = 8080
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

      startup_probe {
        initial_delay_seconds = 2
        timeout_seconds       = 3
        period_seconds        = 5
        failure_threshold     = 12

        http_get {
          path = "/healthz"
          port = 8080
        }
      }

      liveness_probe {
        timeout_seconds   = 3
        period_seconds    = 30
        failure_threshold = 3

        http_get {
          path = "/healthz"
          port = 8080
        }
      }
    }

    volumes {
      name = "cloudsql"
      cloud_sql_instance {
        instances = [google_sql_database_instance.postgres.connection_name]
      }
    }
  }

  depends_on = [
    google_project_service.required,
    google_secret_manager_secret_iam_member.api_database,
    google_secret_manager_secret_iam_member.api_openai,
  ]
}

resource "google_cloud_run_v2_service_iam_member" "public_through_load_balancer" {
  project  = var.project_id
  location = google_cloud_run_v2_service.api.location
  name     = google_cloud_run_v2_service.api.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}
