
# ============================================
# WAREHOUSE CLOUD PLATFORM
# Infraestructura AWS - S3, Lambda, EventBridge
# ============================================

data "aws_caller_identity" "current" {}

locals {
  create_lambda_role = var.lambda_role_arn == null
}

# --------------------------------------------
# Empaquetado de Lambda
# --------------------------------------------

data "archive_file" "lambda_zip" {
  type        = "zip"
  source_file = "${path.module}/../../services/lambda/handler.py"
  output_path = "${path.module}/lambda-handler.zip"
}

# --------------------------------------------
# Amazon S3
# --------------------------------------------

resource "aws_s3_bucket" "reports" {
  bucket        = var.bucket_name
  force_destroy = var.force_destroy_bucket

  tags = {
    Project   = var.project_prefix
    ManagedBy = "terraform"
  }
}

resource "aws_s3_bucket_public_access_block" "reports" {
  bucket = aws_s3_bucket.reports.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "reports" {
  bucket = aws_s3_bucket.reports.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# --------------------------------------------
# IAM - Rol opcional para Lambda
# --------------------------------------------

data "aws_iam_policy_document" "assume_lambda" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda" {
  count = local.create_lambda_role ? 1 : 0

  name_prefix        = "${var.project_prefix}-lambda-"
  assume_role_policy = data.aws_iam_policy_document.assume_lambda.json

  tags = {
    Project = var.project_prefix
  }
}

# Permisos de CloudWatch para el rol creado
resource "aws_iam_role_policy_attachment" "logs" {
  count = local.create_lambda_role ? 1 : 0

  role       = aws_iam_role.lambda[0].name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# Permisos de S3 y EventBridge
data "aws_iam_policy_document" "lambda_access" {
  statement {
    sid = "ReadWriteReports"

    actions = [
      "s3:GetObject",
      "s3:PutObject"
    ]

    resources = [
      "${aws_s3_bucket.reports.arn}/exports/*",
      "${aws_s3_bucket.reports.arn}/processed/*"
    ]
  }

  statement {
    sid = "PublishEvents"

    actions = [
      "events:PutEvents"
    ]

    resources = [
      "arn:aws:events:${var.aws_region}:${data.aws_caller_identity.current.account_id}:event-bus/default"
    ]
  }
}

resource "aws_iam_role_policy" "lambda_access" {
  count = local.create_lambda_role ? 1 : 0

  name = "${var.project_prefix}-lambda-access"
  role = aws_iam_role.lambda[0].id

  policy = data.aws_iam_policy_document.lambda_access.json
}

# --------------------------------------------
# CloudWatch
# --------------------------------------------

resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${var.project_prefix}-export-handler"
  retention_in_days = 7

  tags = {
    Project = var.project_prefix
  }
}

# --------------------------------------------
# AWS Lambda
# --------------------------------------------

resource "aws_lambda_function" "export_handler" {
  function_name = "${var.project_prefix}-export-handler"

  filename         = data.archive_file.lambda_zip.output_path
  source_code_hash = data.archive_file.lambda_zip.output_base64sha256

  role = local.create_lambda_role ? aws_iam_role.lambda[0].arn : var.lambda_role_arn

  runtime = "python3.12"
  handler = "handler.lambda_handler"

  timeout     = 30
  memory_size = 128

  environment {
    variables = {
      EVENT_BUS_NAME = "default"
    }
  }

  depends_on = [
    aws_cloudwatch_log_group.lambda,
    aws_iam_role_policy_attachment.logs,
    aws_iam_role_policy.lambda_access
  ]

  tags = {
    Project = var.project_prefix
  }
}

# --------------------------------------------
# Permitir invocación desde S3
# --------------------------------------------

resource "aws_lambda_permission" "allow_s3" {
  statement_id  = "AllowExecutionFromS3"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.export_handler.function_name

  principal      = "s3.amazonaws.com"
  source_arn     = aws_s3_bucket.reports.arn
  source_account = data.aws_caller_identity.current.account_id
}

# --------------------------------------------
# Notificaciones S3 hacia Lambda
# --------------------------------------------

resource "aws_s3_bucket_notification" "trigger" {
  bucket = aws_s3_bucket.reports.id

  lambda_function {
    lambda_function_arn = aws_lambda_function.export_handler.arn
    events              = ["s3:ObjectCreated:*"]
    filter_prefix       = "exports/"
  }

  depends_on = [
    aws_lambda_permission.allow_s3
  ]
}
