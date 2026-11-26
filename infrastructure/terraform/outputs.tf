output "s3_bucket" {
  value = module.storage.bucket_name
}

output "lambda_name" {
  value = module.lambda.function_name
}

output "region" {
  value = var.aws_region
}

output "eventbridge_bus" {
  value = "default"
}

output "ec2_public_ip" {
  description = "IP pública (elástica) de la EC2 de la plataforma"
  value       = aws_eip.platform.public_ip
}

output "rds_endpoint" {
  description = "host:puerto de RDS (WH-001)"
  value       = module.database.endpoint
}

output "ecr_repository_urls" {
  value = module.ecr.repository_urls
}
