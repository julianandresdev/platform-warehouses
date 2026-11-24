
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
variable "batch_subnet_ids" {
  description = "Subredes donde se ejecutaran los trabajos AWS Batch Fargate"
  type        = list(string)

  default = [
    "subnet-007766dbcad866597"
  ]
}

variable "batch_security_group_ids" {
  description = "Grupos de seguridad para AWS Batch Fargate"
  type        = list(string)

  default = [
    "sg-02b4a7b90f8c87207"
  ]
}
variable "batch_service_role_arn" {
  description = "ARN del rol de servicio de AWS Batch"
  type        = string
}

variable "batch_job_role_arn" {
  description = "ARN del rol IAM utilizado por el trabajo Batch"
  type        = string
}

variable "batch_execution_role_arn" {
  description = "ARN del rol IAM de ejecucion de AWS Batch"
  type        = string
}

variable "batch_image_uri" {
  description = "URI de la imagen Docker almacenada en Amazon ECR"
  type        = string
}