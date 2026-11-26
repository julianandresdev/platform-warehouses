variable "project_prefix" {
  type        = string
  description = "Prefijo para nombrar los recursos"
}

variable "region" {
  type        = string
  description = "Region de AWS (para el login a ECR)"
}

variable "instance_type" {
  type        = string
  description = "Tipo de instancia EC2 (confirmar con lo que permite el Learner Lab, S-01)"
}

variable "subnet_id" {
  type        = string
  description = "Subred de la VPC por defecto donde corre la EC2"
}

variable "security_group_id" {
  type        = string
  description = "Security group de la EC2"
}

variable "instance_profile_name" {
  type        = string
  description = "Perfil de instancia con permisos de ECR y S3"
  default     = "LabInstanceProfile"
}

variable "ami_ssm_parameter" {
  type        = string
  description = "Parametro SSM con la AMI (Amazon Linux 2023)"
  default     = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"
}

variable "ecr_registry" {
  type        = string
  description = "Registro ECR (<cuenta>.dkr.ecr.<region>.amazonaws.com)"
}

variable "compose_dir" {
  type        = string
  description = "Carpeta de la EC2 donde se escribe .env y se espera el docker-compose.yaml"
  default     = "/opt/warehouse-platform"
}

variable "compose_version" {
  type        = string
  description = "Version del plugin docker compose que se descarga en el arranque"
  default     = "v2.29.7"
}

variable "env_vars" {
  type        = map(string)
  description = "Variables que se escriben en el .env de la EC2"
  sensitive   = true
}
