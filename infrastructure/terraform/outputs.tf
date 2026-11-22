output "s3_bucket" { value = aws_s3_bucket.reports.bucket }
output "lambda_name" { value = aws_lambda_function.export_handler.function_name }
output "region" { value = var.aws_region }
output "eventbridge_bus" { value = "default" }
