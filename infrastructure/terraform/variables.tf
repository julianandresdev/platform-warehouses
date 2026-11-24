
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
variable "create_lambda_role" {
  description = "Crear rol propio (false en AWS Academy Learner Lab)"
  type        = bool
  default     = false
}

variable "lambda_existing_role_name" {
  type    = string
  default = "LabRole"
}

variable "central_api_url" {
  description = "URL HTTPS de API central accesible desde Lambda"
  type        = string
  default     = ""
}

variable "central_api_key" {
  description = "Clave de API central; usar proveedor secreto fuera de demos"
  type        = string
  sensitive   = true
  default     = ""
}

variable "provision_platform_resources" {
  type        = bool
  default     = false
  description = "Opt-in a EC2, RDS, redes y repos ECR (costos y permisos)"
}
variable "team_cidr" {
  type        = string
  default     = "127.0.0.1/32"
  description = "IP publica del equipo /32 para puertos administrativos"
}
variable "platform_db_password" {
  type      = string
  sensitive = true
  default   = null
}
variable "platform_instance_type" {
  type    = string
  default = "t3.micro"
}
variable "platform_instance_profile" {
  type    = string
  default = "LabInstanceProfile"
}
variable "platform_git_url" {
  type    = string
  default = "https://github.com/julianandresdev/platform-warehouses.git"
}
variable "platform_git_branch" {
  type    = string
  default = "main"
}
