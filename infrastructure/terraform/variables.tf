variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "bucket_name" {
  type        = string
  description = "Nombre S3 globalmente único, en minúsculas"
}

variable "project_prefix" {
  type    = string
  default = "warehouse-platform"
}

variable "force_destroy_bucket" {
  type    = bool
  default = false
}

variable "team_cidr_blocks" {
  type        = list(string)
  description = "IP del equipo (CIDR /32) con acceso a SSH, 15672 y 3000"
}

variable "public_api_ports" {
  type        = list(number)
  description = "Puertos de las APIs abiertos a Internet para la demo"
}

variable "instance_type" {
  type        = string
  description = "Tipo de instancia EC2; confirmar cuál permite el Learner Lab (S-01)"
}

variable "instance_profile_name" {
  type    = string
  default = "LabInstanceProfile"
}

variable "lab_role_name" {
  type        = string
  description = "Rol IAM existente de la Lambda (el Learner Lab no deja crear roles)"
  default     = "LabRole"
}

variable "db_password" {
  type        = string
  description = "Clave del usuario administrador de RDS (WH-001). Va dentro de DATABASE_URL: evitar : / ? # @"
  sensitive   = true
}

variable "extra_env_vars" {
  type        = map(string)
  description = "Variables adicionales para el .env de la EC2"
  default     = {}
  sensitive   = true
}
