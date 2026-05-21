"""
Production configuration for AWS deployment.
Handles environment-based config, AWS service setup, and validation.
"""

import logging
from functools import lru_cache
from typing import Any, Dict, Optional

from pydantic import AliasChoices, ConfigDict, Field, field_validator
from pydantic_settings import BaseSettings


class AWSConfig(BaseSettings):
    """AWS service configuration"""

    model_config = ConfigDict(env_file=".env", case_sensitive=False, extra="ignore")

    aws_region: str = Field(default="us-east-1", env="AWS_REGION")
    aws_account_id: str = Field(default="", env="AWS_ACCOUNT_ID")
    xray_enabled: bool = Field(default=True, env="XRAY_ENABLED")
    cloudwatch_log_group: str = Field(
        default="/aws/swarm-agent", env="CLOUDWATCH_LOG_GROUP"
    )
    dynamodb_table: str = Field(default="swarm-agent-state", env="DYNAMODB_TABLE")
    s3_bucket: str = Field(default="swarm-agent-logs", env="S3_BUCKET")


class RedisConfig(BaseSettings):
    """Redis/ElastiCache configuration"""

    model_config = ConfigDict(env_file=".env", case_sensitive=False, extra="ignore")

    redis_host: str = Field(default="localhost", env="REDIS_HOST")
    redis_port: int = Field(default=6379, env="REDIS_PORT")
    redis_db: int = Field(default=0, env="REDIS_DB")
    redis_password: Optional[str] = Field(default=None, env="REDIS_PASSWORD")
    redis_ssl: bool = Field(default=False, env="REDIS_SSL")

    @property
    def redis_url(self) -> str:
        """Generate Redis URL"""
        protocol = "rediss" if self.redis_ssl else "redis"
        auth = f":{self.redis_password}@" if self.redis_password else ""
        return f"{protocol}://{auth}{self.redis_host}:{self.redis_port}/{self.redis_db}"


class BedrockConfig(BaseSettings):
    """AWS Bedrock LLM + Knowledge Base configuration"""

    model_config = ConfigDict(env_file=".env", case_sensitive=False, extra="ignore")

    bedrock_region: str = Field(default="us-east-1", env="BEDROCK_REGION")
    bedrock_model_id: str = Field(
        default="us.amazon.nova-2-lite-v1:0",
        env="BEDROCK_MODEL_ID",
    )
    # Optional — leave empty to disable Knowledge Base RAG
    bedrock_kb_id: Optional[str] = Field(default=None, env="BEDROCK_KB_ID")
    bedrock_kb_model_arn: Optional[str] = Field(default=None, env="BEDROCK_KB_MODEL_ARN")
    # Number of KB chunks to retrieve per query
    bedrock_kb_results: int = Field(default=3, env="BEDROCK_KB_RESULTS")


class DatabaseConfig(BaseSettings):
    """PostgreSQL database configuration"""

    model_config = ConfigDict(env_file=".env", case_sensitive=False, extra="ignore")

    db_host: str = Field(default="localhost", env="DB_HOST")
    db_port: int = Field(default=5432, env="DB_PORT")
    db_user: str = Field(default="postgres", env="DB_USER")
    db_password: str = Field(default="", env="DB_PASSWORD")
    db_name: str = Field(default="swarm_agent", env="DB_NAME")
    db_pool_size: int = Field(default=20, env="DB_POOL_SIZE")
    db_max_overflow: int = Field(default=10, env="DB_MAX_OVERFLOW")

    @property
    def db_url(self) -> str:
        """Generate database URL"""
        return (
            f"postgresql+psycopg2://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )


class SecurityConfig(BaseSettings):
    """Security configuration"""

    model_config = ConfigDict(env_file=".env", case_sensitive=False, extra="ignore")

    api_key_enabled: bool = Field(default=True, env="API_KEY_ENABLED")
    api_key_header: str = Field(default="X-API-Key", env="API_KEY_HEADER")
    # API_KEYS env var is a plain comma-separated string, NOT JSON, so we must
    # NOT let pydantic-settings auto-parse it as Dict[str, str] (it would crash).
    # Auth uses _VALID_KEYS built from os.getenv("API_KEYS") directly.
    # We point validation_alias to a never-set var so pydantic-settings skips it;
    # tests inject this dict via MagicMock attribute assignment.
    api_keys: Dict[str, str] = Field(
        default_factory=dict,
        validation_alias=AliasChoices('API_KEYS_JSON_DICT'),
    )
    rate_limit_enabled: bool = Field(default=True, env="RATE_LIMIT_ENABLED")
    rate_limit_requests: int = Field(default=1000, env="RATE_LIMIT_REQUESTS")
    rate_limit_period: int = Field(default=60, env="RATE_LIMIT_PERIOD")
    cors_enabled: bool = Field(default=True, env="CORS_ENABLED")
    cors_origins: list = Field(default_factory=lambda: ["*"], env="CORS_ORIGINS")


class AppConfig(BaseSettings):
    """Application configuration"""

    model_config = ConfigDict(env_file=".env", case_sensitive=False, extra="ignore")

    env: str = Field(default="development", env="ENV")
    debug: bool = Field(default=False, env="DEBUG")
    log_level: str = Field(default="INFO", env="LOG_LEVEL")
    workers: int = Field(default=4, env="WORKERS")
    host: str = Field(default="0.0.0.0", env="HOST")
    port: int = Field(default=9000, env="PORT")
    request_timeout: int = Field(default=30, env="REQUEST_TIMEOUT")

    # Service endpoints
    mcp_server_host: str = Field(default="0.0.0.0", env="MCP_SERVER_HOST")
    mcp_server_port: int = Field(default=9000, env="MCP_SERVER_PORT")
    mcp_server_url: str = Field(default="http://localhost:9000", env="MCP_SERVER_URL")

    # Feature flags
    enable_traces: bool = Field(default=True, env="ENABLE_TRACES")
    enable_metrics: bool = Field(default=True, env="ENABLE_METRICS")
    enable_profiling: bool = Field(default=False, env="ENABLE_PROFILING")

    @field_validator("env", mode="before")
    @classmethod
    def validate_env(cls, v):
        allowed = ["development", "staging", "production"]
        if v not in allowed:
            raise ValueError(f"env must be one of {allowed}")
        return v


@lru_cache(maxsize=1)
def get_aws_config() -> AWSConfig:
    """Get AWS configuration (singleton)"""
    return AWSConfig()


@lru_cache(maxsize=1)
def get_redis_config() -> RedisConfig:
    """Get Redis configuration (singleton)"""
    return RedisConfig()


@lru_cache(maxsize=1)
def get_db_config() -> DatabaseConfig:
    """Get database configuration (singleton)"""
    return DatabaseConfig()


@lru_cache(maxsize=1)
def get_security_config() -> SecurityConfig:
    """Get security configuration (singleton)"""
    return SecurityConfig()


@lru_cache(maxsize=1)
def get_app_config() -> AppConfig:
    """Get app configuration (singleton)"""
    return AppConfig()


@lru_cache(maxsize=1)
def get_bedrock_config() -> BedrockConfig:
    """Get Bedrock configuration (singleton)"""
    return BedrockConfig()
