output "bucket_name" {
  value      = var.bucket_name
  depends_on = [terraform_data.bucket]
}

output "bucket_arn" {
  value = "arn:aws:s3:::${var.bucket_name}"
}
