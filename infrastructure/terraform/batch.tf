
# ============================================
# FASE 8 - AWS BATCH FARGATE
# Configuracion basada en recursos AWS existentes
# ============================================

# 1. Entorno de computo Fargate

resource "aws_batch_compute_environment" "warehouse_fargate" {
  compute_environment_name = "warehouse-platform-fargate"
  type                     = "MANAGED"
  state                    = "ENABLED"

  service_role = "arn:aws:iam::140340522043:role/aws-service-role/batch.amazonaws.com/AWSServiceRoleForBatch"

  compute_resources {
    type      = "FARGATE"
    max_vcpus = 4

    subnets = [
      "subnet-007766dbcad866597"
    ]

    security_group_ids = [
      "sg-02b4a7b90f8c87207"
    ]
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
    image = "140340522043.dkr.ecr.us-east-1.amazonaws.com/warehouse-platform-batch@sha256:680638e07d866bccc726195dbd02072912760084da7e7c45fe6139dfaaaba8e4"

    jobRoleArn       = "arn:aws:iam::140340522043:role/LabRole"
    executionRoleArn = "arn:aws:iam::140340522043:role/LabRole"

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
