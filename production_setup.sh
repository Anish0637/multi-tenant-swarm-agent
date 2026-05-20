#!/bin/bash

# Production Setup Script
# Initializes the multi-tenant swarm agent system for AWS production deployment

set -e

echo "🚀 Multi-Tenant Swarm Agent - Production Setup"
echo "=============================================="

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Step 1: Python Environment
echo -e "${BLUE}Step 1: Setting up Python environment...${NC}"
python3 --version

# Step 2: Install Dependencies
echo -e "${BLUE}Step 2: Installing dependencies...${NC}"
pip install --upgrade pip
pip install -r requirements.txt

# Step 3: Create .env file
echo -e "${BLUE}Step 3: Creating .env file...${NC}"
if [ ! -f .env ]; then
    cat > .env << 'EOF'
# Environment
ENV=development
LOG_LEVEL=INFO
DEBUG=false

# AWS
AWS_REGION=us-east-1
AWS_ACCOUNT_ID=
XRAY_ENABLED=true
CLOUDWATCH_LOG_GROUP=/aws/swarm-agent

# Redis (ElastiCache)
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=
REDIS_SSL=false

# Database (RDS PostgreSQL)
DB_HOST=localhost
DB_PORT=5432
DB_USER=postgres
DB_PASSWORD=postgres
DB_NAME=swarm_agent
DB_POOL_SIZE=20
DB_MAX_OVERFLOW=10

# Security
API_KEY_ENABLED=true
API_KEYS={"prod_key": "sk-prod-demo-key-12345678"}
RATE_LIMIT_ENABLED=true
RATE_LIMIT_REQUESTS=1000
RATE_LIMIT_PERIOD=60

# CORS
CORS_ENABLED=true
CORS_ORIGINS=["*"]

# MCP Server
MCP_SERVER_HOST=0.0.0.0
MCP_SERVER_PORT=9000

EOF
    echo -e "${GREEN}✓ .env file created${NC}"
else
    echo -e "${YELLOW}⚠ .env file already exists${NC}"
fi

# Step 4: Create logs directory
echo -e "${BLUE}Step 4: Creating logs directory...${NC}"
mkdir -p logs

# Step 5: Setup .streamlit config
echo -e "${BLUE}Step 5: Setting up Streamlit...${NC}"
mkdir -p .streamlit

# Step 6: Verify installation
echo -e "${BLUE}Step 6: Verifying installation...${NC}"
python3 -c "
import langchain
import langgraph
import fastapi
import pydantic
from opentelemetry import trace
print('✓ All core packages installed')
"

# Step 7: Show next steps
echo ""
echo -e "${GREEN}✅ Production Setup Complete!${NC}"
echo ""
echo "Next Steps:"
echo "==========="
echo ""
echo "1. Update .env with your AWS credentials:"
echo "   - AWS_REGION: Your AWS region"
echo "   - AWS_ACCOUNT_ID: Your AWS account ID"
echo "   - Database connection strings"
echo "   - Redis endpoint (ElastiCache)"
echo "   - API keys for security"
echo ""
echo "2. Run the MCP Server:"
echo "   python3 -m mcp_server.production_server"
echo ""
echo "3. Run an Agent:"
echo "   AGENT_TYPE=hr python3 -m agents.hr_agent_production"
echo ""
echo "4. Run the Streamlit UI:"
echo "   streamlit run streamlit_app.py"
echo ""
echo "5. Deploy to AWS:"
echo "   docker-compose -f docker/docker-compose.yml up"
echo ""
echo "📚 Documentation:"
echo "   - PRODUCTION_GUIDE.md - Detailed upgrade guide"
echo "   - STREAMLIT_README.md - UI documentation"
echo "   - README.md - General information"
echo ""
