data "aws_caller_identity" "current" {}

locals {
  ecr_registry = "${data.aws_caller_identity.current.account_id}.dkr.ecr.${var.aws_region}.amazonaws.com"
  # El ARN de un bucket S3 solo depende de su nombre: asi la Lambda (permiso) y el bucket
  # (notificacion) no se esperan mutuamente.
  bucket_arn = "arn:aws:s3:::${var.bucket_name}"
}

module "network" {
  source = "./modules/network"

  project_prefix   = var.project_prefix
  public_api_ports = var.public_api_ports
  team_cidr_blocks = var.team_cidr_blocks
}

module "ecr" {
  source = "./modules/ecr"

  project_prefix = var.project_prefix
}

module "database" {
  source = "./modules/database"

  project_prefix    = var.project_prefix
  subnet_ids        = module.network.subnet_ids
  security_group_id = module.network.db_security_group_id
  password          = var.db_password
}

module "lambda" {
  source = "./modules/lambda"

  function_name         = "${var.project_prefix}-export-handler"
  source_dir            = "${path.root}/../../services/lambda/report_validator"
  bucket_arn            = local.bucket_arn
  role_name             = var.lab_role_name
  environment_variables = { EVENT_BUS_NAME = "default" }
}

module "storage" {
  source = "./modules/storage"

  project_prefix      = var.project_prefix
  bucket_name         = var.bucket_name
  force_destroy       = var.force_destroy_bucket
  lambda_function_arn = module.lambda.function_arn

  # S3 valida el permiso de la Lambda al crear la notificacion.
  depends_on = [module.lambda]
}

module "compute" {
  source = "./modules/compute"

  project_prefix        = var.project_prefix
  region                = var.aws_region
  instance_type         = var.instance_type
  subnet_id             = module.network.subnet_ids[0]
  security_group_id     = module.network.app_security_group_id
  instance_profile_name = var.instance_profile_name
  ecr_registry          = local.ecr_registry

  env_vars = merge(
    {
      DATABASE_URL       = "postgresql+psycopg2://${module.database.username}:${var.db_password}@${module.database.endpoint}/${module.database.db_name}"
      S3_BUCKET          = module.storage.bucket_name
      AWS_DEFAULT_REGION = var.aws_region
      ECR_REGISTRY       = local.ecr_registry
    },
    var.extra_env_vars,
  )
}

# El estado ya existente (bucket, Lambda y permiso) se conserva al pasar a modulos.
# El rol IAM propio que creaba la version anterior se reemplaza por LabRole.
moved {
  from = aws_s3_bucket.reports
  to   = module.storage.aws_s3_bucket.reports
}

moved {
  from = aws_s3_bucket_public_access_block.reports
  to   = module.storage.aws_s3_bucket_public_access_block.reports
}

moved {
  from = aws_s3_bucket_server_side_encryption_configuration.reports
  to   = module.storage.aws_s3_bucket_server_side_encryption_configuration.reports
}

moved {
  from = aws_s3_bucket_notification.trigger
  to   = module.storage.aws_s3_bucket_notification.trigger
}

moved {
  from = aws_cloudwatch_log_group.lambda
  to   = module.lambda.aws_cloudwatch_log_group.lambda
}

moved {
  from = aws_lambda_function.export_handler
  to   = module.lambda.aws_lambda_function.export_handler
}

moved {
  from = aws_lambda_permission.allow_s3
  to   = module.lambda.aws_lambda_permission.allow_s3
}
