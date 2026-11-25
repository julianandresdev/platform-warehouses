output "endpoint" {
  description = "host:puerto de RDS"
  value       = aws_db_instance.wh001.endpoint
}

output "address" {
  value = aws_db_instance.wh001.address
}

output "db_name" {
  value = aws_db_instance.wh001.db_name
}

output "username" {
  value = aws_db_instance.wh001.username
}
