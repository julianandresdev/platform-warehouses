
# ============================================
# FASE 8 - AWS BATCH FARGATE
# Configuracion basada en recursos AWS existentes
# ============================================

# 1. Entorno de computo Fargate

resource "aws_batch_compute_environment" "warehouse_fargate" {
  compute_environment_name = "warehouse-platform-fargate"
  type                     = "MANAGED"
  state                    = "ENABLED"

  service_role = var.batch_service_role_arn

  compute_resources {
    type      = "FARGATE"
    max_vcpus = 4

    subnets            = var.batch_subnet_ids
    security_group_ids = var.batch_security_group_ids
  }
}

# 2. Cola de trabajos

resource "aws_batch_job_queue" "warehouse_queue" {
  name     = "warehouse-platform-queue"
  state    = "ENABLED"
  priority = 1

  compute_environment_order {
    order               = 1
    compute_environment = aws_batch_compute_environment.warehouse_fargate.arn
  }
}

# 3. Definicion del trabajo

resource "aws_batch_job_definition" "warehouse_inventory" {
  name                       = "warehouse-platform-inventory"
  type                       = "container"
  platform_capabilities      = ["FARGATE"]
  deregister_on_new_revision = false

  container_properties = jsonencode({
    image = var.batch_image_uri

    jobRoleArn       = var.batch_job_role_arn
    executionRoleArn = var.batch_execution_role_arn

    resourceRequirements = [
      {
        type  = "VCPU"
        value = "0.25"
      },
      {
        type  = "MEMORY"
        value = "512"
      }
    ]

    environment = [
      {
        name  = "REPORT_BUCKET"
        value = aws_s3_bucket.reports.bucket
      },
      {
        name  = "BATCH_REGISTRY_BACKEND"
        value = "s3"
      }
    ]

    networkConfiguration = {
      assignPublicIp = "ENABLED"
    }

    fargatePlatformConfiguration = {
      platformVersion = "LATEST"
    }
  })
}
