variable "function_name" {
  type        = string
  description = "Nombre de la funcion Lambda"
}

variable "source_dir" {
  type        = string
  description = "Carpeta con el codigo de la Lambda (handler.py); se empaqueta con archive_file"
}

variable "bucket_arn" {
  type        = string
  description = "ARN del bucket que puede invocar la funcion"
}

variable "role_name" {
  type        = string
  description = "Rol IAM existente que usa la Lambda"
  default     = "LabRole"
}

variable "environment_variables" {
  type        = map(string)
  description = "Variables de entorno de la funcion"
  default     = {}
}
