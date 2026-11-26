data "aws_caller_identity" "current" {}

# En el Learner Lab no se pueden crear roles IAM: se usa el rol existente.
data "aws_iam_role" "lab" {
  name = var.role_name
}

data "archive_file" "zip" {
  type        = "zip"
  source_dir  = var.source_dir
  output_path = "${path.module}/${var.function_name}.zip"
}

resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${var.function_name}"
  retention_in_days = 7
}

resource "aws_lambda_function" "export_handler" {
  function_name    = var.function_name
  filename         = data.archive_file.zip.output_path
  source_code_hash = data.archive_file.zip.output_base64sha256
  role             = data.aws_iam_role.lab.arn
  runtime          = "python3.12"
  handler          = "handler.lambda_handler"
  timeout          = 30
  memory_size      = 128

  environment {
    variables = var.environment_variables
  }

  depends_on = [aws_cloudwatch_log_group.lambda]
}

# S3 puede invocar la funcion, pero solo desde este bucket y esta cuenta.
resource "aws_lambda_permission" "allow_s3" {
  statement_id   = "AllowExecutionFromS3"
  action         = "lambda:InvokeFunction"
  function_name  = aws_lambda_function.export_handler.function_name
  principal      = "s3.amazonaws.com"
  source_arn     = var.bucket_arn
  source_account = data.aws_caller_identity.current.account_id
}
