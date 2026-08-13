data "google_project" "current" {
  project_id = var.project_id
}

locals {
  prefix = "mtg-rag-${var.environment}"
  labels = merge(
    {
      application = "mtg-rag"
      environment = var.environment
      managed-by  = "terraform"
    },
    var.labels,
  )

  required_services = toset([
    "artifactregistry.googleapis.com",
    "billingbudgets.googleapis.com",
    "cloudbuild.googleapis.com",
    "cloudresourcemanager.googleapis.com",
    "compute.googleapis.com",
    "iam.googleapis.com",
    "identitytoolkit.googleapis.com",
    "logging.googleapis.com",
    "monitoring.googleapis.com",
    "run.googleapis.com",
    "secretmanager.googleapis.com",
    "sqladmin.googleapis.com",
    "storage.googleapis.com",
    "cloudscheduler.googleapis.com",
  ])
}

resource "google_project_service" "required" {
  for_each = local.required_services

  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}

resource "google_artifact_registry_repository" "containers" {
  location      = var.region
  repository_id = local.prefix
  description   = "Versioned MTG RAG application containers"
  format        = "DOCKER"

  cleanup_policies {
    id     = "keep-recent"
    action = "KEEP"
    most_recent_versions {
      keep_count = 10
    }
  }

  depends_on = [google_project_service.required]
}

resource "google_storage_bucket" "snapshots" {
  name                        = "${var.project_id}-${local.prefix}-snapshots"
  location                    = var.region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = false

  versioning {
    enabled = true
  }

  retention_policy {
    retention_period = 31536000
    is_locked        = var.environment == "prod"
  }

  depends_on = [google_project_service.required]
}

resource "google_secret_manager_secret" "openai_api_key" {
  secret_id = "${local.prefix}-openai-api-key"

  replication {
    user_managed {
      replicas {
        location = var.region
      }
    }
  }

  depends_on = [google_project_service.required]
}

resource "google_secret_manager_secret" "database_url" {
  secret_id = "${local.prefix}-database-url"

  replication {
    user_managed {
      replicas {
        location = var.region
      }
    }
  }

  depends_on = [google_project_service.required]
}

resource "google_sql_database_instance" "postgres" {
  name             = local.prefix
  region           = var.region
  database_version = "POSTGRES_16"

  deletion_protection = var.environment == "prod"

  settings {
    tier              = var.database_tier
    availability_type = var.environment == "prod" ? "REGIONAL" : "ZONAL"
    disk_type         = "PD_SSD"
    disk_size         = var.database_disk_size_gb
    disk_autoresize   = true

    ip_configuration {
      ipv4_enabled = true
      ssl_mode     = "ENCRYPTED_ONLY"
    }

    backup_configuration {
      enabled                        = true
      point_in_time_recovery_enabled = true
      start_time                     = "17:00"
      transaction_log_retention_days = 7

      backup_retention_settings {
        retained_backups = var.environment == "prod" ? 30 : 7
        retention_unit   = "COUNT"
      }
    }

    maintenance_window {
      day          = 7
      hour         = 16
      update_track = "stable"
    }

    insights_config {
      query_insights_enabled  = true
      query_string_length     = 1024
      record_application_tags = true
      record_client_address   = false
    }
  }

  depends_on = [google_project_service.required]
}

resource "google_sql_database" "application" {
  name     = "mtg_rag"
  instance = google_sql_database_instance.postgres.name
}

resource "google_service_account" "api" {
  account_id   = "${local.prefix}-api"
  display_name = "MTG RAG ${var.environment} API"
}

resource "google_service_account" "ingestion" {
  account_id   = "${local.prefix}-ingest"
  display_name = "MTG RAG ${var.environment} ingestion"
}

resource "google_service_account" "scheduler" {
  account_id   = "${local.prefix}-schedule"
  display_name = "MTG RAG ${var.environment} scheduler"
}

resource "google_project_iam_custom_role" "api_firebase_account_deletion" {
  project     = var.project_id
  role_id     = "${replace(local.prefix, "-", "_")}_firebase_account_deletion"
  title       = "MTG RAG API Firebase account deletion"
  description = "Allows the API to delete the currently authenticated Firebase user."
  permissions = ["firebaseauth.users.delete"]
  stage       = "GA"

  depends_on = [google_project_service.required]
}

locals {
  api_project_roles = toset([
    "roles/cloudsql.client",
    "roles/logging.logWriter",
    "roles/monitoring.metricWriter",
  ])
  ingestion_project_roles = toset([
    "roles/cloudsql.client",
    "roles/logging.logWriter",
    "roles/monitoring.metricWriter",
  ])
}

resource "google_project_iam_member" "api" {
  for_each = local.api_project_roles

  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.api.email}"
}

resource "google_project_iam_member" "api_firebase_account_deletion" {
  project = var.project_id
  role    = google_project_iam_custom_role.api_firebase_account_deletion.name
  member  = "serviceAccount:${google_service_account.api.email}"
}

resource "google_project_iam_member" "ingestion" {
  for_each = local.ingestion_project_roles

  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.ingestion.email}"
}

resource "google_secret_manager_secret_iam_member" "api_openai" {
  secret_id = google_secret_manager_secret.openai_api_key.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.api.email}"
}

resource "google_secret_manager_secret_iam_member" "api_database" {
  secret_id = google_secret_manager_secret.database_url.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.api.email}"
}

resource "google_secret_manager_secret_iam_member" "ingestion_openai" {
  secret_id = google_secret_manager_secret.openai_api_key.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.ingestion.email}"
}

resource "google_secret_manager_secret_iam_member" "ingestion_database" {
  secret_id = google_secret_manager_secret.database_url.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.ingestion.email}"
}

resource "google_storage_bucket_iam_member" "ingestion_snapshots" {
  bucket = google_storage_bucket.snapshots.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.ingestion.email}"
}
