resource "aws_ecr_repository" "this" {
  for_each = toset(var.repositories)

  name                 = each.value
  image_tag_mutability = "MUTABLE"
  # Laboratorio: permite `terraform destroy` aunque el repositorio tenga imagenes.
  force_delete = true

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = { Project = var.project_prefix, ManagedBy = "terraform" }
}
