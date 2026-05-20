"""
Agents module main entry point.
"""

import asyncio
import logging
import os
import sys

from agents.supervisor import SupervisorAgent
from agents.hr_agent import HRAgent
from agents.finance_agent import FinanceAgent
from agents.medical_agent import MedicalAgent

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def main():
    """Main entry point for agents"""
    agent_type = os.getenv("AGENT_TYPE", "supervisor").lower()
    
    logger.info(f"Starting {agent_type} agent...")
    
    try:
        if agent_type == "supervisor":
            agent = SupervisorAgent()
        elif agent_type == "hr":
            agent = HRAgent()
        elif agent_type == "finance":
            agent = FinanceAgent()
        elif agent_type == "medical":
            agent = MedicalAgent()
        else:
            logger.error(f"Unknown agent type: {agent_type}")
            sys.exit(1)
        
        # Start the agent
        await agent.start()
    except KeyboardInterrupt:
        logger.info("Agent interrupted")
    except Exception as e:
        logger.error(f"Agent error: {str(e)}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
