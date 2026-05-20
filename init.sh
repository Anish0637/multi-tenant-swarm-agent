#!/bin/bash
set -e

# Initialize git repository
git init

# Add remote
git remote add origin https://github.com/Anish0637/multi-tenant-swarm-agent.git

# Create initial commit
git add .
git commit -m "Initial commit: Multi-tenant swarm agent platform

- Supervisor agent orchestration
- Tenant-specific agents (HR, Finance, Medical)
- RBAC/ABAC/CBAC access control
- MCP server integration
- Service registry and discovery
- Terraform infrastructure
- GitHub Actions CI/CD pipeline
- Docker containerization
- Comprehensive test suite"

# Push to remote (optional - comment out if not ready)
# git push -u origin main

echo "✅ Git repository initialized successfully!"
echo ""
echo "To push to GitHub, run:"
echo "  git push -u origin main"
