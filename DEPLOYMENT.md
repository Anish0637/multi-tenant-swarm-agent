# Deployment Configuration

## Prerequisites

1. AWS Account with appropriate permissions
2. GitHub repository with secrets configured:
   - `AWS_ACCOUNT_ID`: Your AWS account ID
   - `EC2_PRIVATE_KEY`: EC2 instance private key

## AWS Setup

### 1. Create S3 Bucket for Terraform State

```bash
aws s3 mb s3://your-terraform-state-bucket --region us-east-1
aws s3api put-bucket-versioning \
  --bucket your-terraform-state-bucket \
  --versioning-configuration Status=Enabled
```

### 2. Create DynamoDB Table for Terraform Locks

```bash
aws dynamodb create-table \
  --table-name terraform-locks \
  --attribute-definitions AttributeName=LockID,AttributeType=S \
  --key-schema AttributeName=LockID,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST
```

### 3. Configure Terraform Backend

Edit `terraform/versions.tf`:

```hcl
backend "s3" {
  bucket         = "your-terraform-state-bucket"
  key            = "multi-tenant-swarm-agent/terraform.tfstate"
  region         = "us-east-1"
  dynamodb_table = "terraform-locks"
  encrypt        = true
}
```

## GitHub Actions Setup

### 1. Create GitHub Secrets

```bash
# In GitHub repo settings → Secrets and variables → Actions

AWS_ACCOUNT_ID=123456789012
EC2_PRIVATE_KEY=-----BEGIN RSA PRIVATE KEY-----
...
-----END RSA PRIVATE KEY-----
```

### 2. Create IAM Role for GitHub Actions

```bash
# Create trust policy file: trust-policy.json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::AWS_ACCOUNT_ID:oidc-provider/token.actions.githubusercontent.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
          "token.actions.githubusercontent.com:sub": "repo:Anish0637/multi-tenant-swarm-agent:ref:refs/heads/main"
        }
      }
    }
  ]
}

# Create role
aws iam create-role \
  --role-name GitHubActionsRole \
  --assume-role-policy-document file://trust-policy.json

# Attach policies
aws iam attach-role-policy \
  --role-name GitHubActionsRole \
  --policy-arn arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryPowerUser

aws iam attach-role-policy \
  --role-name GitHubActionsRole \
  --policy-arn arn:aws:iam::aws:policy/AmazonEC2FullAccess
```

## Deployment Steps

### Local Terraform Deployment

```bash
cd terraform

# Initialize
terraform init

# Plan
terraform plan \
  -var="aws_region=us-east-1" \
  -var="instance_type=t3.medium" \
  -var="instance_count=2"

# Apply
terraform apply \
  -var="aws_region=us-east-1" \
  -var="instance_type=t3.medium" \
  -var="instance_count=2"
```

### Docker Compose Local Development

```bash
docker-compose up -d
docker-compose logs -f
docker-compose down
```

### GitHub Actions Deployment

1. Push to `main` branch
2. Build & Test workflow runs
3. Push to ECR workflow runs
4. Deploy to EC2 workflow runs

## Monitoring

### CloudWatch Logs

```bash
aws logs tail /aws/ec2/swarm-agents --follow
```

### EC2 Instance Metrics

```bash
aws cloudwatch get-metric-statistics \
  --namespace AWS/EC2 \
  --metric-name CPUUtilization \
  --dimensions Name=InstanceId,Value=i-xxxxxxxx \
  --start-time 2024-01-01T00:00:00Z \
  --end-time 2024-01-02T00:00:00Z \
  --period 3600 \
  --statistics Average
```

## Troubleshooting

### Instance not healthy

```bash
# SSH into instance
ssh -i your-key.pem ec2-user@your-instance-ip

# Check Docker
docker ps
docker logs swarm-agent

# Check services
curl http://localhost:8000/health
curl http://localhost:8001/health
```

### ECR login fails

```bash
# Verify IAM permissions
aws ecr get-authorization-token

# Re-login
aws ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin YOUR_ACCOUNT.dkr.ecr.us-east-1.amazonaws.com
```

## Cleanup

```bash
# Destroy AWS resources
cd terraform
terraform destroy

# Delete ECR repositories
aws ecr delete-repository --repository-name multi-tenant-swarm-agent --force
aws ecr delete-repository --repository-name mcp-server --force
```

## Security Considerations

1. Always use IAM roles instead of access keys
2. Enable ECR image scanning
3. Use private subnets for sensitive workloads
4. Implement network ACLs for defense-in-depth
5. Rotate credentials regularly
6. Enable VPC Flow Logs for monitoring
7. Use AWS Secrets Manager for sensitive data
