# ============================================
# FASE 9 - EVENTBRIDGE Y CLOUDWATCH LOGS
# ============================================

resource "aws_cloudwatch_log_group" "eventbridge" {
  name              = "/aws/events/warehouse-platform-report-created"
  retention_in_days = 7

  tags = {
    Project = var.project_prefix
  }
}

resource "aws_cloudwatch_event_rule" "report_created" {
  name        = "warehouse-platform-report-created"
  description = "Detectar reportes de inventario publicados por Lambda"
  state       = "ENABLED"

  event_bus_name = "default"

  event_pattern = jsonencode({
    source        = ["warehouse.platform"]
    "detail-type" = ["InventoryReportCreated"]
  })
}
# Permitir que EventBridge escriba en CloudWatch Logs

resource "aws_cloudwatch_log_resource_policy" "eventbridge" {
  policy_name = "${var.project_prefix}-eventbridge-logs"

  policy_document = jsonencode({
    Version = "2012-10-17"

    Statement = [
      {
        Sid    = "AllowEventBridgeToWriteLogs"
        Effect = "Allow"

        Principal = {
          Service = [
            "events.amazonaws.com",
            "delivery.logs.amazonaws.com"
          ]
        }

        Action = [
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]

        Resource = "${aws_cloudwatch_log_group.eventbridge.arn}:*"
      }
    ]
  })
}

# Conectar la regla de EventBridge con CloudWatch Logs

resource "aws_cloudwatch_event_target" "report_logs" {
  rule           = aws_cloudwatch_event_rule.report_created.name
  event_bus_name = "default"
  target_id      = "warehouse-report-cloudwatch"

  arn = aws_cloudwatch_log_group.eventbridge.arn

  depends_on = [
    aws_cloudwatch_log_resource_policy.eventbridge
  ]
}