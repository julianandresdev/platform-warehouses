# Issue #27: recursos adicionales, opt-in. Nunca habilitar sin revisar plan/costos/permisos.
data "aws_vpc" "default" {
  count   = var.provision_platform_resources ? 1 : 0
  default = true
}

data "aws_subnets" "default" {
  count = var.provision_platform_resources ? 1 : 0
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default[0].id]
  }
}

data "aws_ssm_parameter" "al2023" {
  count = var.provision_platform_resources ? 1 : 0
  name  = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"
}

resource "aws_security_group" "warehouse_api" {
  count       = var.provision_platform_resources ? 1 : 0
  name_prefix = "${var.project_prefix}-api-"
  vpc_id      = data.aws_vpc.default[0].id
  ingress {
    description = "Demo API"
    from_port   = 8000
    to_port     = 8000
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  ingress {
    description = "Puertos administrativos solo desde IP del equipo"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [var.team_cidr]
  }
  ingress {
    from_port   = 15672
    to_port     = 15672
    protocol    = "tcp"
    cidr_blocks = [var.team_cidr]
  }
  ingress {
    from_port   = 3000
    to_port     = 3000
    protocol    = "tcp"
    cidr_blocks = [var.team_cidr]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_security_group" "warehouse_db" {
  count       = var.provision_platform_resources ? 1 : 0
  name_prefix = "${var.project_prefix}-db-"
  vpc_id      = data.aws_vpc.default[0].id
  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.warehouse_api[0].id]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_ecr_repository" "platform" {
  for_each             = var.provision_platform_resources ? toset(["warehouse", "central", "batch", "iot"]) : toset([])
  name                 = "${var.project_prefix}-${each.key}"
  image_tag_mutability = "MUTABLE"
  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_db_subnet_group" "warehouse" {
  count      = var.provision_platform_resources ? 1 : 0
  name       = "${var.project_prefix}-db-subnets"
  subnet_ids = data.aws_subnets.default[0].ids
}

resource "aws_db_instance" "warehouse" {
  count                  = var.provision_platform_resources ? 1 : 0
  identifier             = "${var.project_prefix}-wh001"
  engine                 = "postgres"
  engine_version         = "16"
  instance_class         = "db.t3.micro"
  allocated_storage      = 20
  db_name                = "platform"
  username               = "admin"
  password               = var.platform_db_password
  db_subnet_group_name   = aws_db_subnet_group.warehouse[0].name
  vpc_security_group_ids = [aws_security_group.warehouse_db[0].id]
  publicly_accessible    = false
  skip_final_snapshot    = true
  deletion_protection    = false
}

resource "aws_instance" "warehouse" {
  count                  = var.provision_platform_resources ? 1 : 0
  ami                    = data.aws_ssm_parameter.al2023[0].value
  instance_type          = var.platform_instance_type
  subnet_id              = data.aws_subnets.default[0].ids[0]
  vpc_security_group_ids = [aws_security_group.warehouse_api[0].id]
  iam_instance_profile   = var.platform_instance_profile
  user_data = templatefile("${path.module}/userdata.sh.tftpl", {
    region   = var.aws_region
    repo_url = var.platform_git_url
    branch   = var.platform_git_branch
    prefix   = var.project_prefix
  })
  tags = { Name = "${var.project_prefix}-platform" }
}

output "platform_ec2_ip" {
  value = var.provision_platform_resources ? aws_instance.warehouse[0].public_ip : null
}
output "platform_rds_endpoint" {
  value = var.provision_platform_resources ? aws_db_instance.warehouse[0].endpoint : null
}
