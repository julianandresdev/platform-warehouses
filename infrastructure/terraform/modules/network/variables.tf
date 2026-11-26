variable "project_prefix" {
  type        = string
  description = "Prefijo para nombrar los recursos"
}

variable "public_api_ports" {
  type        = list(number)
  description = "Puertos de las APIs abiertos a Internet para la demo"
}

variable "team_cidr_blocks" {
  type        = list(string)
  description = "IP del equipo en notacion CIDR (p. ej. 203.0.113.7/32) para SSH, 15672 y 3000"
}

variable "team_admin_ports" {
  type        = list(number)
  description = "Puertos administrativos abiertos solo al equipo: SSH, consola de RabbitMQ y Grafana"
  default     = [22, 15672, 3000]
}
