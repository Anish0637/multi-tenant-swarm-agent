output "vpc_id" {
  description = "VPC ID"
  value       = aws_vpc.main.id
}

output "ecr_repository_url_swarm_agents" {
  description = "ECR repository URL for swarm agents"
  value       = aws_ecr_repository.swarm_agents.repository_url
}

output "ecr_repository_url_mcp_server" {
  description = "ECR repository URL for MCP server"
  value       = aws_ecr_repository.mcp_server.repository_url
}

output "ec2_instance_ids" {
  description = "EC2 instance IDs"
  value       = aws_instance.swarm_agents[*].id
}

output "ec2_public_ips" {
  description = "EC2 public IPs"
  value       = aws_eip.swarm_agents[*].public_ip
}

output "ec2_private_ips" {
  description = "EC2 private IPs"
  value       = aws_instance.swarm_agents[*].private_ip
}

output "security_group_id" {
  description = "Security group ID"
  value       = aws_security_group.swarm_agents.id
}
