# IAM Role for EC2 Instances
resource "aws_iam_role" "swarm_agents" {
  name = "swarm-agents-role"
  
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ec2.amazonaws.com"
        }
      }
    ]
  })
  
  tags = {
    Name = "swarm-agents-role"
  }
}

# IAM Policy for ECR Access
resource "aws_iam_role_policy" "ecr_access" {
  name = "swarm-agents-ecr-policy"
  role = aws_iam_role.swarm_agents.id
  
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ecr:GetAuthorizationToken",
          "ecr:BatchGetImage",
          "ecr:GetDownloadUrlForLayer"
        ]
        Resource = "*"
      }
    ]
  })
}

# IAM Policy for CloudWatch
resource "aws_iam_role_policy" "cloudwatch" {
  name = "swarm-agents-cloudwatch-policy"
  role = aws_iam_role.swarm_agents.id
  
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "cloudwatch:PutMetricData",
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "*"
      }
    ]
  })
}

# IAM Policy for Secrets Manager
resource "aws_iam_role_policy" "secrets_manager" {
  name = "swarm-agents-secrets-policy"
  role = aws_iam_role.swarm_agents.id
  
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue",
          "secretsmanager:ListSecrets"
        ]
        Resource = "*"
      }
    ]
  })
}

# IAM Instance Profile
resource "aws_iam_instance_profile" "swarm_agents" {
  name = "swarm-agents-profile"
  role = aws_iam_role.swarm_agents.name
}
