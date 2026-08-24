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

variable "public_delivery_mode" {
  description = "Public API delivery path: an external load balancer or Firebase Hosting proxy."
  type        = string
  default     = "load_balancer"

  validation {
    condition     = contains(["load_balancer", "firebase_hosting_proxy"], var.public_delivery_mode)
    error_message = "public_delivery_mode must be load_balancer or firebase_hosting_proxy."
  }
}

variable "api_domain" {
  description = "DNS name served by the global HTTPS load balancer when that delivery mode is used."
  type        = string
  default     = null
  nullable    = true

  validation {
    condition = var.public_delivery_mode != "load_balancer" || (
      var.api_domain != null && can(regex("^[a-z0-9.-]+$", var.api_domain))
    )
    error_message = "api_domain must be a DNS name when public_delivery_mode is load_balancer."
  }
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
  description = "Immutable or versioned Artifact Registry image for the API and non-migration jobs."
  type        = string

  validation {
    condition     = can(regex("(@sha256:[0-9a-f]{64}|:[^/:]+)$", var.api_image)) && !endswith(var.api_image, ":latest")
    error_message = "api_image must use a digest or a non-latest tag."
  }
}

variable "migration_image" {
  description = "Optional migration-job image used for a migration-first rollout; defaults to api_image."
  type        = string
  default     = null
  nullable    = true

  validation {
    condition = var.migration_image == null ? true : (
      can(regex("(@sha256:[0-9a-f]{64}|:[^/:]+)$", var.migration_image)) &&
      !endswith(var.migration_image, ":latest")
    )
    error_message = "migration_image must be null or use a digest or a non-latest tag."
  }
}

variable "openai_secret_version" {
  description = "Secret Manager version mounted as MTG_RAG_OPENAI_API_KEY."
  type        = string
  default     = "latest"

  validation {
    condition     = var.environment != "prod" || can(regex("^[1-9][0-9]*$", var.openai_secret_version))
    error_message = "openai_secret_version must be a positive numeric Secret Manager version in prod."
  }
}

variable "database_url_secret_version" {
  description = "Secret Manager version mounted as MTG_RAG_DATABASE_URL."
  type        = string
  default     = "latest"

  validation {
    condition     = var.environment != "prod" || can(regex("^[1-9][0-9]*$", var.database_url_secret_version))
    error_message = "database_url_secret_version must be a positive numeric Secret Manager version in prod."
  }
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

variable "conversation_context_enabled" {
  description = "Enable bounded prior-message context for follow-up questions."
  type        = bool
  default     = false
}

variable "conversation_context_max_messages" {
  description = "Maximum prior messages loaded for a contextual follow-up."
  type        = number
  default     = 6

  validation {
    condition     = var.conversation_context_max_messages > 0
    error_message = "conversation_context_max_messages must be positive."
  }
}

variable "conversation_context_max_characters" {
  description = "Maximum serialized characters of prior conversation context."
  type        = number
  default     = 6000

  validation {
    condition     = var.conversation_context_max_characters > 0
    error_message = "conversation_context_max_characters must be positive."
  }
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
    condition     = var.environment != "prod" ? true : try(var.monthly_budget_usd > 0, false)
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
