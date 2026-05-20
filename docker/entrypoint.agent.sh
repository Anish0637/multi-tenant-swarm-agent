#!/bin/bash

# Entry point for agent containers
# Runs the specified agent type based on AGENT_TYPE environment variable

set -e

AGENT_TYPE=${AGENT_TYPE:-supervisor}

echo "Starting $AGENT_TYPE agent..."

export AGENT_TYPE=$AGENT_TYPE
python -m agents
