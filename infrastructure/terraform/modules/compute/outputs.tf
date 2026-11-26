output "public_ip" {
  value = aws_instance.platform.public_ip
}

output "instance_id" {
  value = aws_instance.platform.id
}
