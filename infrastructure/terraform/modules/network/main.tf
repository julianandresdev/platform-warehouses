# VPC por defecto (data) y security groups.
data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

# EC2 de la plataforma.
resource "aws_security_group" "app" {
  name_prefix = "${var.project_prefix}-app-"
  description = "EC2 de la plataforma: APIs abiertas para la demo; administracion solo desde el equipo"
  vpc_id      = data.aws_vpc.default.id

  tags = { Name = "${var.project_prefix}-app", Project = var.project_prefix, ManagedBy = "terraform" }
}

# APIs abiertas para la demo.
resource "aws_vpc_security_group_ingress_rule" "api" {
  for_each = toset([for port in var.public_api_ports : tostring(port)])

  security_group_id = aws_security_group.app.id
  description       = "API ${each.value} (demo)"
  ip_protocol       = "tcp"
  from_port         = tonumber(each.value)
  to_port           = tonumber(each.value)
  cidr_ipv4         = "0.0.0.0/0"
}

# SSH, consola de RabbitMQ (15672) y Grafana (3000): solo la IP del equipo.
resource "aws_vpc_security_group_ingress_rule" "team" {
  for_each = {
    for pair in setproduct(var.team_admin_ports, var.team_cidr_blocks) :
    "${pair[0]}-${pair[1]}" => { port = pair[0], cidr = pair[1] }
  }

  security_group_id = aws_security_group.app.id
  description       = "Administracion ${each.value.port} (equipo)"
  ip_protocol       = "tcp"
  from_port         = each.value.port
  to_port           = each.value.port
  cidr_ipv4         = each.value.cidr
}

resource "aws_vpc_security_group_egress_rule" "app_all" {
  security_group_id = aws_security_group.app.id
  description       = "Salida libre"
  ip_protocol       = "-1"
  cidr_ipv4         = "0.0.0.0/0"
}

# RDS: solo desde la EC2.
resource "aws_security_group" "db" {
  name_prefix = "${var.project_prefix}-db-"
  description = "RDS PostgreSQL: solo desde la EC2 de la plataforma"
  vpc_id      = data.aws_vpc.default.id

  tags = { Name = "${var.project_prefix}-db", Project = var.project_prefix, ManagedBy = "terraform" }
}

resource "aws_vpc_security_group_ingress_rule" "db_from_app" {
  security_group_id            = aws_security_group.db.id
  description                  = "PostgreSQL desde la EC2"
  ip_protocol                  = "tcp"
  from_port                    = 5432
  to_port                      = 5432
  referenced_security_group_id = aws_security_group.app.id
}
