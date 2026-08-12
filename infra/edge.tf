resource "google_compute_security_policy" "api" {
  name        = "${local.prefix}-api"
  description = "Country allowlist and default deny for the public API"
  type        = "CLOUD_ARMOR"

  rule {
    action      = "allow"
    priority    = 1000
    description = "Allow supported launch countries"

    match {
      expr {
        expression = "origin.region_code == 'TW' || origin.region_code == 'JP' || origin.region_code == 'KR' || origin.region_code == 'SG'"
      }
    }
  }

  rule {
    action      = "deny(403)"
    priority    = 2147483647
    description = "Default deny"

    match {
      versioned_expr = "SRC_IPS_V1"
      config {
        src_ip_ranges = ["*"]
      }
    }
  }

  depends_on = [google_project_service.required]
}

resource "google_compute_region_network_endpoint_group" "api" {
  name                  = "${local.prefix}-api"
  region                = var.region
  network_endpoint_type = "SERVERLESS"

  cloud_run {
    service = google_cloud_run_v2_service.api.name
  }
}

resource "google_compute_backend_service" "api" {
  name                  = "${local.prefix}-api"
  protocol              = "HTTP"
  load_balancing_scheme = "EXTERNAL_MANAGED"
  timeout_sec           = 40
  enable_cdn            = false
  security_policy       = google_compute_security_policy.api.id

  backend {
    group = google_compute_region_network_endpoint_group.api.id
  }

  log_config {
    enable      = true
    sample_rate = 1
  }
}

resource "google_compute_managed_ssl_certificate" "api" {
  name = "${local.prefix}-api"

  managed {
    domains = [var.api_domain]
  }
}

resource "google_compute_global_address" "api" {
  name = "${local.prefix}-api"
}

resource "google_compute_url_map" "https" {
  name            = "${local.prefix}-https"
  default_service = google_compute_backend_service.api.id
}

resource "google_compute_target_https_proxy" "api" {
  name             = "${local.prefix}-api"
  url_map          = google_compute_url_map.https.id
  ssl_certificates = [google_compute_managed_ssl_certificate.api.id]
}

resource "google_compute_global_forwarding_rule" "https" {
  name                  = "${local.prefix}-https"
  ip_address            = google_compute_global_address.api.id
  port_range            = "443"
  target                = google_compute_target_https_proxy.api.id
  load_balancing_scheme = "EXTERNAL_MANAGED"
}

resource "google_compute_url_map" "http_redirect" {
  name = "${local.prefix}-http-redirect"

  default_url_redirect {
    https_redirect         = true
    strip_query            = false
    redirect_response_code = "MOVED_PERMANENTLY_DEFAULT"
  }
}

resource "google_compute_target_http_proxy" "redirect" {
  name    = "${local.prefix}-http-redirect"
  url_map = google_compute_url_map.http_redirect.id
}

resource "google_compute_global_forwarding_rule" "http" {
  name                  = "${local.prefix}-http"
  ip_address            = google_compute_global_address.api.id
  port_range            = "80"
  target                = google_compute_target_http_proxy.redirect.id
  load_balancing_scheme = "EXTERNAL_MANAGED"
}
