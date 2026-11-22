variable "aws_region" { type = string; default = "us-east-1" }
variable "bucket_name" { type = string; description = "Nombre S3 globalmente único, en minúsculas" }
variable "project_prefix" { type = string; default = "warehouse-platform" }
variable "force_destroy_bucket" { type = bool; default = false }
