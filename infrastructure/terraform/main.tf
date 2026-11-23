data "archive_file" "lambda_zip" {
  type        = "zip"
  source_file = "${path.module}/../../services/lambda/handler.py"
  output_path = "${path.module}/lambda-handler.zip"
}

resource "aws_s3_bucket" "reports" {
  bucket        = var.bucket_name
  force_destroy = var.force_destroy_bucket
  tags          = { Project = var.project_prefix, ManagedBy = "terraform" }
}
resource "aws_s3_bucket_public_access_block" "reports" {
  bucket                  = aws_s3_bucket.reports.id
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
  name_prefix        = "${var.project_prefix}-lambda-"
  assume_role_policy = data.aws_iam_policy_document.assume_lambda.json
}
resource "aws_iam_role_policy_attachment" "logs" {
  role       = aws_iam_role.lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}
data "aws_iam_policy_document" "lambda_access" {
  statement {
    actions   = ["s3:GetObject", "s3:PutObject"]
    resources = ["${aws_s3_bucket.reports.arn}/exports/*", "${aws_s3_bucket.reports.arn}/processed/*"]
  }
  statement {
    actions   = ["events:PutEvents"]
    resources = ["arn:aws:events:${var.aws_region}:${data.aws_caller_identity.current.account_id}:event-bus/default"]
  }
}
data "aws_caller_identity" "current" {}
resource "aws_iam_role_policy" "lambda_access" {
  role   = aws_iam_role.lambda.id
  policy = data.aws_iam_policy_document.lambda_access.json
}
resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${var.project_prefix}-export-handler"
  retention_in_days = 7
}
resource "aws_lambda_function" "export_handler" {
  function_name    = "${var.project_prefix}-export-handler"
  filename         = data.archive_file.lambda_zip.output_path
  source_code_hash = data.archive_file.lambda_zip.output_base64sha256
  role             = aws_iam_role.lambda.arn
  runtime          = "python3.12"
  handler          = "handler.lambda_handler"
  timeout          = 30
  memory_size      = 128
  environment { variables = { EVENT_BUS_NAME = "default" } }
  depends_on = [aws_cloudwatch_log_group.lambda, aws_iam_role_policy_attachment.logs, aws_iam_role_policy.lambda_access]
}
resource "aws_lambda_permission" "allow_s3" {
  statement_id   = "AllowExecutionFromS3"
  action         = "lambda:InvokeFunction"
  function_name  = aws_lambda_function.export_handler.function_name
  principal      = "s3.amazonaws.com"
  source_arn     = aws_s3_bucket.reports.arn
  source_account = data.aws_caller_identity.current.account_id
}
resource "aws_s3_bucket_notification" "trigger" {
  bucket = aws_s3_bucket.reports.id
  lambda_function {
    lambda_function_arn = aws_lambda_function.export_handler.arn
    events              = ["s3:ObjectCreated:*"]
    filter_prefix       = "exports/"
  }
  depends_on = [aws_lambda_permission.allow_s3]
}
