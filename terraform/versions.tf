terraform {
  required_version = ">= 1.5"
  
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
  
  backend "s3" {
    # Configure S3 backend for state management
    # bucket = "your-terraform-state-bucket"
    # key    = "multi-tenant-swarm-agent/terraform.tfstate"
    # region = "us-east-1"
    # dynamodb_table = "terraform-locks"
    # encrypt = true
  }
}

provider "aws" {
  region = var.aws_region
  
  default_tags {
    tags = {
      Project     = "multi-tenant-swarm-agent"
      Environment = var.environment
      CreatedBy   = "Terraform"
      CreatedAt   = timestamp()
    }
  }
}
