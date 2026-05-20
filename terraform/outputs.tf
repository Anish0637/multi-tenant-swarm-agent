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

output "public_url" {
  description = "Public URL for the webapp and API"
  value       = "https://app.${var.domain_name}"
}

output "api_url" {
  description = "REST API base URL"
  value       = "https://app.${var.domain_name}/api"
}

output "swagger_url" {
  description = "Swagger UI URL"
  value       = "https://app.${var.domain_name}/docs"
}

output "alb_dns_name" {
  description = "Public ALB DNS name (before DNS propagation)"
  value       = aws_lb.main.dns_name
}

output "internal_alb_dns_name" {
  description = "Internal ALB DNS (used by agents to reach MCP server)"
  value       = aws_lb.internal.dns_name
}

output "ecs_cluster_name" {
  description = "ECS Cluster name"
  value       = aws_ecs_cluster.main.name
}
