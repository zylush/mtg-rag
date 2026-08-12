variable "project_id" {
  description = "Existing Google Cloud project to deploy into."
  type        = string
}

variable "environment" {
  description = "Deployment environment."
  type        = string

  validation {
    condition     = contains(["dev", "prod"], var.environment)
    error_message = "environment must be dev or prod."
  }
}

variable "region" {
  description = "Google Cloud region for the application."
  type        = string
  default     = "asia-east1"
}

variable "api_domain" {
  description = "DNS name served by the global HTTPS load balancer."
  type        = string
}

variable "frontend_origin" {
  description = "Exact HTTPS origin allowed by the API CORS policy."
  type        = string

  validation {
    condition     = can(regex("^https://[^/]+$", var.frontend_origin))
    error_message = "frontend_origin must be one HTTPS origin without a path."
  }
}

variable "api_image" {
  description = "Immutable or versioned Artifact Registry image for both API and ingestion."
  type        = string

  validation {
    condition     = can(regex("(@sha256:[0-9a-f]{64}|:[^/:]+)$", var.api_image)) && !endswith(var.api_image, ":latest")
    error_message = "api_image must use a digest or a non-latest tag."
  }
}

variable "openai_secret_version" {
  description = "Secret Manager version mounted as MTG_RAG_OPENAI_API_KEY."
  type        = string
  default     = "latest"
}

variable "database_url_secret_version" {
  description = "Secret Manager version mounted as MTG_RAG_DATABASE_URL."
  type        = string
  default     = "latest"
}

variable "generation_model" {
  description = "OpenAI model used for grounded answer generation."
  type        = string
  default     = "gpt-5.6-luna"
}

variable "embedding_model" {
  description = "OpenAI embeddings model."
  type        = string
  default     = "text-embedding-3-small"
}

variable "embedding_dimensions" {
  description = "Vector dimensions stored in pgvector."
  type        = number
  default     = 1536
}

variable "cloud_run_max_instances" {
  description = "Maximum API instances; the application also enforces per-user quotas."
  type        = number
  default     = 10
}

variable "cloud_run_concurrency" {
  description = "Maximum concurrent requests per API instance."
  type        = number
  default     = 20
}

variable "database_tier" {
  description = "Cloud SQL machine tier."
  type        = string
  default     = "db-custom-2-7680"
}

variable "database_disk_size_gb" {
  description = "Initial Cloud SQL SSD size."
  type        = number
  default     = 25
}

variable "billing_account_id" {
  description = "Billing account used for budget alerts; required in prod."
  type        = string
  default     = null
  nullable    = true

  validation {
    condition     = var.environment != "prod" || var.billing_account_id != null
    error_message = "billing_account_id is required for prod."
  }
}

variable "monthly_budget_usd" {
  description = "Monthly budget alert amount; required in prod."
  type        = number
  default     = null
  nullable    = true

  validation {
    condition     = var.environment != "prod" || (var.monthly_budget_usd != null && var.monthly_budget_usd > 0)
    error_message = "monthly_budget_usd must be positive in prod."
  }
}

variable "monitoring_notification_channels" {
  description = "Existing Monitoring notification-channel resource names."
  type        = list(string)
  default     = []

  validation {
    condition     = var.environment != "prod" || length(var.monitoring_notification_channels) > 0
    error_message = "At least one monitoring notification channel is required in prod."
  }
}

variable "labels" {
  description = "Additional labels applied to supported resources."
  type        = map(string)
  default     = {}
}
