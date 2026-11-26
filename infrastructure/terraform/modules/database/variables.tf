variable "project_prefix" {
  type        = string
  description = "Prefijo para nombrar los recursos"
}

variable "subnet_ids" {
  type        = list(string)
  description = "Subredes del grupo de subredes de RDS"
}

variable "security_group_id" {
  type        = string
  description = "Security group de RDS (solo acepta la EC2)"
}

variable "password" {
  type        = string
  description = "Clave del usuario administrador de RDS"
  sensitive   = true
}

variable "db_name" {
  type        = string
  description = "Nombre de la base de WH-001"
  default     = "platform"
}

variable "username" {
  type        = string
  description = "Usuario administrador de la base (RDS PostgreSQL no admite `admin`: es una palabra reservada del motor)"
  default     = "warehouse"
}

variable "allocated_storage" {
  type        = number
  description = "Almacenamiento en GB"
  default     = 20
}
