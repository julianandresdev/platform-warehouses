variable "project_prefix" {
  type        = string
  description = "Prefijo del proyecto (solo para las etiquetas)"
}

variable "repositories" {
  type        = list(string)
  description = "Repositorios ECR a crear"
  default     = ["warehouse", "central", "batch", "iot"]
}
