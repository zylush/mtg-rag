resource "google_logging_metric" "ingestion_failures" {
  name        = "${local.prefix}/ingestion-failures"
  description = "Failed ingestion executions"
  filter      = "resource.type=\"cloud_run_job\" AND resource.labels.job_name=\"${google_cloud_run_v2_job.ingestion.name}\" AND severity>=ERROR"

  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "INT64"
  }
}

resource "google_logging_metric" "api_5xx" {
  name        = "${local.prefix}/api-5xx"
  description = "API responses with 5xx status codes at the selected public delivery layer"
  filter = var.public_delivery_mode == "load_balancer" ? (
    "resource.type=\"http_load_balancer\" AND resource.labels.backend_service_name=\"${google_compute_backend_service.api[0].name}\" AND httpRequest.status>=500"
    ) : (
    "resource.type=\"cloud_run_revision\" AND resource.labels.service_name=\"${google_cloud_run_v2_service.api.name}\" AND httpRequest.status>=500"
  )

  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "INT64"
  }
}

resource "google_monitoring_alert_policy" "ingestion_failures" {
  display_name = "${local.prefix}: ingestion failed"
  combiner     = "OR"
  enabled      = true

  conditions {
    display_name = "At least one failed ingestion execution"
    condition_threshold {
      filter          = "metric.type=\"logging.googleapis.com/user/${google_logging_metric.ingestion_failures.name}\" AND resource.type=\"cloud_run_job\""
      comparison      = "COMPARISON_GT"
      threshold_value = 0
      duration        = "0s"

      aggregations {
        alignment_period   = "300s"
        per_series_aligner = "ALIGN_SUM"
      }
    }
  }

  notification_channels = var.monitoring_notification_channels
}

resource "google_monitoring_alert_policy" "api_5xx" {
  display_name = "${local.prefix}: API 5xx"
  combiner     = "OR"
  enabled      = true

  conditions {
    display_name = "At least one API 5xx response in five minutes"
    condition_threshold {
      filter          = "metric.type=\"logging.googleapis.com/user/${google_logging_metric.api_5xx.name}\" AND resource.type=\"${var.public_delivery_mode == "load_balancer" ? "http_load_balancer" : "cloud_run_revision"}\""
      comparison      = "COMPARISON_GT"
      threshold_value = 0
      duration        = "0s"

      aggregations {
        alignment_period   = "300s"
        per_series_aligner = "ALIGN_SUM"
      }
    }
  }

  notification_channels = var.monitoring_notification_channels
}

resource "google_billing_budget" "monthly" {
  count = var.billing_account_id != null && var.monthly_budget_usd != null ? 1 : 0

  billing_account = var.billing_account_id
  display_name    = "${local.prefix} monthly budget"

  budget_filter {
    projects = ["projects/${data.google_project.current.number}"]
  }

  amount {
    specified_amount {
      currency_code = "USD"
      units         = tostring(coalesce(var.monthly_budget_usd, 0))
    }
  }

  dynamic "threshold_rules" {
    for_each = toset(["0.50", "0.80", "1.00"])
    content {
      threshold_percent = tonumber(threshold_rules.value)
    }
  }

  all_updates_rule {
    monitoring_notification_channels = var.monitoring_notification_channels
    disable_default_iam_recipients   = false
  }

  depends_on = [google_project_service.required]
}
