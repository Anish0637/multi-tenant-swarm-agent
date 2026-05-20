"""
AWS CDK Stack for Multi-Tenant Swarm Agent.
Alternative to Terraform — pure Python IaC.

Deploy:
  pip install aws-cdk-lib constructs
  cdk bootstrap
  cdk deploy
"""

import os
import aws_cdk as cdk
from aws_cdk import (
    Stack,
    aws_ec2 as ec2,
    aws_ecs as ecs,
    aws_ecs_patterns as ecs_patterns,
    aws_ecr as ecr,
    aws_iam as iam,
    aws_logs as logs,
    aws_secretsmanager as secretsmanager,
    aws_elasticloadbalancingv2 as elbv2,
    Duration,
    RemovalPolicy,
)
from constructs import Construct


class SwarmAgentStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        env_name = os.getenv("DEPLOY_ENV", "production")

        # ── VPC ─────────────────────────────────────────────────────────────
        vpc = ec2.Vpc(
            self, "SwarmVpc",
            max_azs=2,
            nat_gateways=1,
            subnet_configuration=[
                ec2.SubnetConfiguration(name="Public",  subnet_type=ec2.SubnetType.PUBLIC,  cidr_mask=24),
                ec2.SubnetConfiguration(name="Private", subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS, cidr_mask=24),
            ],
        )

        # ── ECS Cluster ──────────────────────────────────────────────────────
        cluster = ecs.Cluster(
            self, "SwarmCluster",
            vpc=vpc,
            container_insights=True,
        )

        # ── ECR Repositories ─────────────────────────────────────────────────
        mcp_repo = ecr.Repository(
            self, "McpServerRepo",
            repository_name="mcp-server",
            removal_policy=RemovalPolicy.RETAIN,
            image_scan_on_push=True,
        )
        agents_repo = ecr.Repository(
            self, "AgentsRepo",
            repository_name="multi-tenant-swarm-agent",
            removal_policy=RemovalPolicy.RETAIN,
            image_scan_on_push=True,
        )

        # ── Secrets ──────────────────────────────────────────────────────────
        app_secret = secretsmanager.Secret.from_secret_name_v2(
            self, "AppSecrets", "swarm-agent/prod"
        )

        # ── IAM Task Role ─────────────────────────────────────────────────────
        task_role = iam.Role(
            self, "EcsTaskRole",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("CloudWatchAgentServerPolicy"),
            ],
        )
        app_secret.grant_read(task_role)

        # ── Shared log group ─────────────────────────────────────────────────
        log_group = logs.LogGroup(
            self, "SwarmLogs",
            log_group_name="/ecs/swarm-agent",
            retention=logs.RetentionDays.ONE_MONTH,
            removal_policy=RemovalPolicy.DESTROY,
        )

        def _logging(prefix: str) -> ecs.LogDriver:
            return ecs.LogDrivers.aws_logs(
                stream_prefix=prefix,
                log_group=log_group,
            )

        def _secret(field: str) -> ecs.Secret:
            return ecs.Secret.from_secrets_manager(app_secret, field)

        # ── MCP Server (internal, behind internal ALB) ────────────────────────
        mcp_task = ecs.FargateTaskDefinition(
            self, "McpTaskDef",
            cpu=512, memory_limit_mib=1024,
            task_role=task_role,
        )
        mcp_container = mcp_task.add_container(
            "mcp-server",
            image=ecs.ContainerImage.from_ecr_repository(mcp_repo, "latest"),
            environment={"ENV": env_name, "PORT": "8000", "LOG_LEVEL": "INFO"},
            secrets={
                "OPENAI_API_KEY": _secret("OPENAI_API_KEY"),
                "API_KEYS": _secret("API_KEYS"),
            },
            logging=_logging("mcp-server"),
            health_check=ecs.HealthCheck(
                command=["CMD-SHELL", "curl -f http://localhost:8000/health || exit 1"],
                interval=Duration.seconds(30),
                retries=3,
            ),
        )
        mcp_container.add_port_mappings(ecs.PortMapping(container_port=8000))

        mcp_service = ecs_patterns.ApplicationLoadBalancedFargateService(
            self, "McpService",
            cluster=cluster,
            task_definition=mcp_task,
            desired_count=2,
            public_load_balancer=False,     # internal only
            listener_port=9000,
            target_protocol=elbv2.ApplicationProtocol.HTTP,
        )
        mcp_service.target_group.configure_health_check(path="/health")
        mcp_url = f"http://{mcp_service.load_balancer.load_balancer_dns_name}:9000"

        # ── Public REST API ───────────────────────────────────────────────────
        api_task = ecs.FargateTaskDefinition(
            self, "ApiTaskDef",
            cpu=512, memory_limit_mib=1024,
            task_role=task_role,
        )
        api_container = api_task.add_container(
            "public-api",
            image=ecs.ContainerImage.from_ecr_repository(agents_repo, "api"),
            environment={"ENV": env_name, "PORT": "8000", "MCP_SERVER_URL": mcp_url},
            secrets={
                "API_KEYS": _secret("API_KEYS"),
                "OPENAI_API_KEY": _secret("OPENAI_API_KEY"),
            },
            logging=_logging("public-api"),
        )
        api_container.add_port_mappings(ecs.PortMapping(container_port=8000))

        api_service = ecs_patterns.ApplicationLoadBalancedFargateService(
            self, "ApiService",
            cluster=cluster,
            task_definition=api_task,
            desired_count=2,
            public_load_balancer=True,
            listener_port=80,
            target_protocol=elbv2.ApplicationProtocol.HTTP,
        )
        api_service.target_group.configure_health_check(path="/api/health")

        # ── Streamlit Webapp ──────────────────────────────────────────────────
        webapp_task = ecs.FargateTaskDefinition(
            self, "WebappTaskDef",
            cpu=256, memory_limit_mib=512,
            task_role=task_role,
        )
        webapp_container = webapp_task.add_container(
            "webapp",
            image=ecs.ContainerImage.from_ecr_repository(agents_repo, "webapp"),
            environment={
                "ENV": env_name,
                "MCP_SERVER_URL": mcp_url,
                "PUBLIC_API_URL": f"http://{api_service.load_balancer.load_balancer_dns_name}/api",
            },
            logging=_logging("webapp"),
        )
        webapp_container.add_port_mappings(ecs.PortMapping(container_port=8501))

        webapp_service = ecs_patterns.ApplicationLoadBalancedFargateService(
            self, "WebappService",
            cluster=cluster,
            task_definition=webapp_task,
            desired_count=1,
            public_load_balancer=True,
            listener_port=8501,
            target_protocol=elbv2.ApplicationProtocol.HTTP,
        )
        webapp_service.target_group.configure_health_check(path="/_stcore/health")

        # ── Agent Worker Tasks ─────────────────────────────────────────────────
        for agent_type in ("hr", "finance", "medical"):
            t = ecs.FargateTaskDefinition(
                self, f"{agent_type.capitalize()}AgentTask",
                cpu=512, memory_limit_mib=1024,
                task_role=task_role,
            )
            t.add_container(
                f"{agent_type}-agent",
                image=ecs.ContainerImage.from_ecr_repository(agents_repo, "latest"),
                environment={"ENV": env_name, "AGENT_TYPE": agent_type, "MCP_SERVER_URL": mcp_url},
                secrets={"OPENAI_API_KEY": _secret("OPENAI_API_KEY")},
                logging=_logging(f"{agent_type}-agent"),
            )
            ecs.FargateService(
                self, f"{agent_type.capitalize()}AgentService",
                cluster=cluster,
                task_definition=t,
                desired_count=1,
                vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
            )

        # ── Outputs ───────────────────────────────────────────────────────────
        cdk.CfnOutput(self, "WebAppUrl",    value=f"http://{webapp_service.load_balancer.load_balancer_dns_name}:8501")
        cdk.CfnOutput(self, "ApiUrl",       value=f"http://{api_service.load_balancer.load_balancer_dns_name}/api")
        cdk.CfnOutput(self, "SwaggerUrl",   value=f"http://{api_service.load_balancer.load_balancer_dns_name}/docs")
        cdk.CfnOutput(self, "McpServerUrl", value=mcp_url)


# ── App entry point ──────────────────────────────────────────────────────────
app = cdk.App()
SwarmAgentStack(
    app, "SwarmAgentStack",
    env=cdk.Environment(
        account=os.getenv("CDK_DEFAULT_ACCOUNT"),
        region=os.getenv("CDK_DEFAULT_REGION", "us-east-1"),
    ),
)
app.synth()
