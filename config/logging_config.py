"""
Production logging configuration with AWS CloudWatch integration.
Implements structured logging for observability and debugging.
"""

import json
import logging
import sys
from logging.handlers import RotatingFileHandler
from typing import Optional

from pythonjsonlogger import jsonlogger

from config.production import get_app_config, get_aws_config

try:
    import watchtower

    WATCHTOWER_AVAILABLE = True
except ImportError:
    WATCHTOWER_AVAILABLE = False


class CustomJsonFormatter(jsonlogger.JsonFormatter):
    """Custom JSON formatter with additional fields"""

    def add_fields(self, log_record, record, message_dict):
        super().add_fields(log_record, record, message_dict)
        log_record["timestamp"] = self.format_time(record)
        log_record["level"] = record.levelname
        log_record["logger"] = record.name
        log_record["module"] = record.module
        log_record["function"] = record.funcName
        log_record["line"] = record.lineno

        # Add correlation ID if available
        if hasattr(record, "correlation_id"):
            log_record["correlation_id"] = record.correlation_id
        if hasattr(record, "tenant_id"):
            log_record["tenant_id"] = record.tenant_id
        if hasattr(record, "agent_id"):
            log_record["agent_id"] = record.agent_id

    @staticmethod
    def format_time(record):
        """Format timestamp"""
        import datetime

        ct = datetime.datetime.fromtimestamp(record.created)
        return ct.isoformat()


def setup_logging(logger_name: Optional[str] = None) -> logging.Logger:
    """
    Setup production logging with CloudWatch integration.

    Args:
        logger_name: Name of logger (defaults to root)

    Returns:
        Configured logger instance
    """
    app_config = get_app_config()
    aws_config = get_aws_config()

    logger = logging.getLogger(logger_name or "swarm-agent")
    logger.setLevel(getattr(logging, app_config.log_level.upper()))

    # Remove existing handlers
    logger.handlers.clear()

    # Console handler with JSON formatting (for container logs)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, app_config.log_level.upper()))
    json_formatter = CustomJsonFormatter()
    console_handler.setFormatter(json_formatter)
    logger.addHandler(console_handler)

    # File handler with rotation (local development/debugging)
    if app_config.env != "production":
        import os

        os.makedirs("logs", exist_ok=True)
        file_handler = RotatingFileHandler(
            f"logs/{logger_name or 'swarm-agent'}.log",
            maxBytes=10485760,  # 10MB
            backupCount=5,
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(json_formatter)
        logger.addHandler(file_handler)

    # CloudWatch handler (production)
    if (
        app_config.env == "production"
        and WATCHTOWER_AVAILABLE
        and aws_config.xray_enabled
    ):
        try:
            cw_handler = watchtower.CloudWatchLogHandler(
                log_group=aws_config.cloudwatch_log_group,
                stream_name=logger_name or "swarm-agent",
                boto3_client=None,  # Uses default credentials
                use_queues=True,  # Async logging
            )
            cw_handler.setLevel(getattr(logging, app_config.log_level.upper()))
            cw_handler.setFormatter(json_formatter)
            logger.addHandler(cw_handler)
        except Exception as e:
            logger.warning(f"CloudWatch handler setup failed: {e}")

    return logger


def get_logger(name: str) -> logging.Logger:
    """Get a named logger"""
    return logging.getLogger(name)


# Root logger setup
root_logger = setup_logging("swarm-agent")
