variable "region" {
  type        = string
  description = "Region donde se crea el bucket"
}

variable "project_prefix" {
  type        = string
  description = "Prefijo del proyecto (solo para las etiquetas)"
}

variable "bucket_name" {
  type        = string
  description = "Nombre S3 globalmente unico, en minusculas"
}

variable "force_destroy" {
  type        = bool
  description = "Permite destruir el bucket aunque tenga objetos (solo demos con datos descartables)"
  default     = false
}

variable "lambda_function_arn" {
  type        = string
  description = "Lambda que recibe las notificaciones de reports/"
}
