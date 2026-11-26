# Bucket privado (bloqueo de acceso publico y cifrado) con notificacion a la Lambda.
#
# El bucket NO se declara con `aws_s3_bucket`: en el Learner Lab una politica de la
# organizacion (SCP) niega s3:GetBucketObjectLockConfiguration y el proveedor de AWS la
# llama siempre al leer ese recurso (falla con AccessDenied en las versiones 4.67, 5.0,
# 5.31 y 5.100). Se crea con la CLI de AWS; lo demas (acceso publico, cifrado y
# notificacion) sigue siendo Terraform. Necesita `aws` y credenciales en el entorno.
resource "terraform_data" "bucket" {
  input = {
    name   = var.bucket_name
    region = var.region
    force  = var.force_destroy
  }

  provisioner "local-exec" {
    command = <<-EOT
      aws s3api head-bucket --bucket "${self.input.name}" 2>/dev/null || \
        aws s3api create-bucket --bucket "${self.input.name}" --region "${self.input.region}"
    EOT
  }

  provisioner "local-exec" {
    when    = destroy
    command = <<-EOT
      if [ "${self.input.force}" = "true" ]; then aws s3 rm "s3://${self.input.name}" --recursive; fi
      aws s3api delete-bucket --bucket "${self.input.name}" --region "${self.input.region}"
    EOT
  }
}

resource "aws_s3_bucket_public_access_block" "reports" {
  depends_on = [terraform_data.bucket]

  bucket = var.bucket_name

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "reports" {
  depends_on = [terraform_data.bucket]

  bucket = var.bucket_name

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# Solo `reports/*.json` dispara la Lambda. Los metadatos van a `metadata/` para que
# la propia Lambda no se vuelva a invocar.
resource "aws_s3_bucket_notification" "trigger" {
  depends_on = [terraform_data.bucket]

  bucket = var.bucket_name

  lambda_function {
    lambda_function_arn = var.lambda_function_arn
    events              = ["s3:ObjectCreated:*"]
    filter_prefix       = "reports/"
    filter_suffix       = ".json"
  }
}
