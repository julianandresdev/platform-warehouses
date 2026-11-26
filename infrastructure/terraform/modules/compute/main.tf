data "aws_ssm_parameter" "ami" {
  name = var.ami_ssm_parameter
}

resource "aws_instance" "platform" {
  ami                         = data.aws_ssm_parameter.ami.value
  instance_type               = var.instance_type
  subnet_id                   = var.subnet_id
  vpc_security_group_ids      = [var.security_group_id]
  iam_instance_profile        = var.instance_profile_name
  associate_public_ip_address = true

  user_data = templatefile("${path.module}/userdata.sh.tftpl", {
    region          = var.region
    ecr_registry    = var.ecr_registry
    compose_dir     = var.compose_dir
    compose_version = var.compose_version
    env_vars        = var.env_vars
    bundle_s3_uri   = var.bundle_s3_uri
  })

  tags = { Name = "${var.project_prefix}-platform", Project = var.project_prefix, ManagedBy = "terraform" }
}

resource "aws_eip_association" "platform" {
  count         = var.associate_eip ? 1 : 0
  instance_id   = aws_instance.platform.id
  allocation_id = var.eip_allocation_id
}
