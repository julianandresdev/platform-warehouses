# PostgreSQL de WH-001 en RDS. Solo para el laboratorio: sin snapshot final.
resource "aws_db_subnet_group" "this" {
  name       = "${var.project_prefix}-db-subnets"
  subnet_ids = var.subnet_ids
}

resource "aws_db_instance" "wh001" {
  identifier             = "${var.project_prefix}-wh001"
  engine                 = "postgres"
  engine_version         = "16"
  instance_class         = "db.t3.micro"
  allocated_storage      = var.allocated_storage
  db_name                = var.db_name
  username               = var.username
  password               = var.password
  db_subnet_group_name   = aws_db_subnet_group.this.name
  vpc_security_group_ids = [var.security_group_id]
  publicly_accessible    = false
  skip_final_snapshot    = true

  tags = { Name = "${var.project_prefix}-wh001", Project = var.project_prefix, ManagedBy = "terraform" }
}
