#!/bin/bash
set -e

# Update system
apt-get update
apt-get install -y curl docker.io python3-pip git

# Start Docker
systemctl start docker
systemctl enable docker

# Login to ECR
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin ${ecr_registry}

# Clone the repository (or pull pre-built image)
# For now, we'll create a simple startup script
cat > /opt/start-agent.sh <<'EOF'
#!/bin/bash
docker pull ${ecr_registry}:latest
docker run -d \
  -p 8000:8000 \
  -p 8001:8001 \
  -e AWS_REGION=us-east-1 \
  --name swarm-agent \
  ${ecr_registry}:latest
EOF

chmod +x /opt/start-agent.sh

# Log startup
echo "EC2 instance initialized at $(date)" > /var/log/startup.log
