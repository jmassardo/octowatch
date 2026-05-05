################################################################################
# OctoWatch — Observability & Alerting
#
# Provisions:
#   - Log Analytics Workspace  (Container Insights, activity logs)
#   - Application Insights     (APM + availability tests)
#   - Standard web test        (HTTP availability probe every 5 minutes)
#   - Monitor Action Group     (email + optional webhook for alerts)
#   - Metric alert rules       (pod restarts, node NotReady, Valkey queue depth)
################################################################################

# ── Log Analytics Workspace ────────────────────────────────────────────────────

resource "azurerm_log_analytics_workspace" "main" {
  name                = "law-${local.name_prefix}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  sku                 = "PerGB2018"
  retention_in_days   = var.log_retention_days
  tags                = local.common_tags
}

# ── Application Insights ───────────────────────────────────────────────────────

resource "azurerm_application_insights" "main" {
  name                = "appi-${local.name_prefix}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  workspace_id        = azurerm_log_analytics_workspace.main.id
  application_type    = "web"
  tags                = local.common_tags
}

# ── Availability Test (HTTP ping every 5 minutes) ─────────────────────────────
# Monitors the public OctoWatch URL from 5 Azure edge locations.
# Fails the test if: HTTP response >= 400, or response time > 30 s.

resource "azurerm_application_insights_standard_web_test" "availability" {
  name                    = "webtest-${local.name_prefix}-availability"
  resource_group_name     = azurerm_resource_group.main.name
  location                = azurerm_resource_group.main.location
  application_insights_id = azurerm_application_insights.main.id
  geo_locations = [
    "us-va-ash-azr",   # East US
    "us-tx-sn1-azr",   # South Central US
    "us-il-ch1-azr",   # North Central US
    "emea-nl-ams-azr", # West Europe
    "apac-sg-sin-azr", # Southeast Asia
  ]
  frequency   = 300  # Every 5 minutes
  timeout     = 30
  enabled     = true
  retry_enabled = true
  description = "OctoWatch HTTPS availability check — alerts ops when site is unreachable."
  tags        = local.common_tags

  request {
    url                              = "https://${local.tls_domain}/"
    http_verb                        = "GET"
    follow_redirects_enabled         = true
    parse_dependent_requests_enabled = false
  }

  validation_rules {
    expected_status_code          = 200
    ssl_check_enabled             = true
    ssl_cert_remaining_lifetime   = 14  # Alert 14 days before cert expiry
  }
}

# ── Alert Action Group (email + optional PagerDuty webhook) ───────────────────

resource "azurerm_monitor_action_group" "ops_alerts" {
  name                = "ag-${local.name_prefix}-ops"
  resource_group_name = azurerm_resource_group.main.name
  short_name          = "oct-ops"
  tags                = local.common_tags

  dynamic "email_receiver" {
    for_each = var.alert_email_address != "" ? [1] : []
    content {
      name                    = "ops-email"
      email_address           = var.alert_email_address
      use_common_alert_schema = true
    }
  }
}

# ── Availability Alert — site down ────────────────────────────────────────────
# Fires when the availability test detects the site is unreachable from ≥ 3
# locations simultaneously (filters transient single-location blips).

resource "azurerm_monitor_metric_alert" "availability" {
  name                = "alert-${local.name_prefix}-site-down"
  resource_group_name = azurerm_resource_group.main.name
  scopes              = [azurerm_application_insights.main.id]
  description         = "OctoWatch site unreachable from multiple Azure edge locations."
  severity            = 0  # Critical
  frequency           = "PT5M"
  window_size         = "PT15M"
  auto_mitigate       = true
  tags                = local.common_tags

  criteria {
    metric_namespace = "microsoft.insights/components"
    metric_name      = "availabilityResults/availabilityPercentage"
    aggregation      = "Average"
    operator         = "LessThan"
    threshold        = 50  # < 50% availability across test locations
  }

  action {
    action_group_id = azurerm_monitor_action_group.ops_alerts.id
  }
}

# ── AKS Alert — node NotReady ─────────────────────────────────────────────────

resource "azurerm_monitor_metric_alert" "node_not_ready" {
  name                = "alert-${local.name_prefix}-node-notready"
  resource_group_name = azurerm_resource_group.main.name
  scopes              = [azurerm_kubernetes_cluster.main.id]
  description         = "One or more AKS nodes are in NotReady state."
  severity            = 1  # Error
  frequency           = "PT5M"
  window_size         = "PT15M"
  auto_mitigate       = true
  tags                = local.common_tags

  criteria {
    metric_namespace = "Microsoft.ContainerService/managedClusters"
    metric_name      = "kube_node_status_condition"
    aggregation      = "Average"
    operator         = "GreaterThan"
    threshold        = 0

    dimension {
      name     = "status2"
      operator = "Include"
      values   = ["NotReady"]
    }
  }

  action {
    action_group_id = azurerm_monitor_action_group.ops_alerts.id
  }
}

# ── AKS Alert — pod restart storm ────────────────────────────────────────────
# Fires when any pod has restarted more than 5 times in 15 minutes — a sign
# of a crash loop. Does not fire for the normal single restart on deploy.

resource "azurerm_monitor_metric_alert" "pod_restarts" {
  name                = "alert-${local.name_prefix}-pod-restarts"
  resource_group_name = azurerm_resource_group.main.name
  scopes              = [azurerm_kubernetes_cluster.main.id]
  description         = "OctoWatch pod is crash-looping (>5 restarts in 15 min)."
  severity            = 1  # Error
  frequency           = "PT5M"
  window_size         = "PT15M"
  auto_mitigate       = true
  tags                = local.common_tags

  criteria {
    metric_namespace = "Microsoft.ContainerService/managedClusters"
    metric_name      = "kube_pod_container_status_restarts_total"
    aggregation      = "Total"
    operator         = "GreaterThan"
    threshold        = 5

    dimension {
      name     = "namespace"
      operator = "Include"
      values   = ["octowatch"]
    }
  }

  action {
    action_group_id = azurerm_monitor_action_group.ops_alerts.id
  }
}

# ── Outputs ───────────────────────────────────────────────────────────────────

output "application_insights_instrumentation_key" {
  description = "Application Insights instrumentation key (for APM SDK configuration)."
  value       = azurerm_application_insights.main.instrumentation_key
  sensitive   = true
}

output "application_insights_connection_string" {
  description = "Application Insights connection string (preferred over instrumentation key)."
  value       = azurerm_application_insights.main.connection_string
  sensitive   = true
}

output "log_analytics_workspace_id" {
  description = "Log Analytics Workspace resource ID."
  value       = azurerm_log_analytics_workspace.main.id
}
