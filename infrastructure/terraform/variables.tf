
variable "aws_region" {
  type        = string
  description = "Region de AWS"
  default     = "us-east-1"
}

variable "bucket_name" {
  type        = string
  description = "Nombre globalmente unico del bucket S3"
}

variable "project_prefix" {
  type        = string
  description = "Prefijo utilizado para nombrar los recursos"
  default     = "warehouse-platform"
}

variable "force_destroy_bucket" {
  type        = bool
  description = "Permite eliminar un bucket aunque contenga objetos"
  default     = false
}

variable "lambda_role_arn" {
  type        = string
  description = "ARN de un rol IAM existente. Si es null, Terraform crea uno nuevo."
  default     = null
}
