# Bucket privado (bloqueo de acceso publico y cifrado) con notificacion a la Lambda.
resource "aws_s3_bucket" "reports" {
  bucket        = var.bucket_name
  force_destroy = var.force_destroy

  tags = { Project = var.project_prefix, ManagedBy = "terraform" }
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

# Solo `reports/*.json` dispara la Lambda. Los metadatos van a `metadata/` para que
# la propia Lambda no se vuelva a invocar.
resource "aws_s3_bucket_notification" "trigger" {
  bucket = aws_s3_bucket.reports.id

  lambda_function {
    lambda_function_arn = var.lambda_function_arn
    events              = ["s3:ObjectCreated:*"]
    filter_prefix       = "reports/"
    filter_suffix       = ".json"
  }
}
