# ============================================================
# ECS Cluster + Fargate Services for all agents
# ============================================================

# ECS Cluster
resource "aws_ecs_cluster" "main" {
  name = "swarm-agent-cluster"

  setting {
    name  = "containerInsights"
    value = "enabled"
  }

  tags = var.tags
}

resource "aws_ecs_cluster_capacity_providers" "main" {
  cluster_name       = aws_ecs_cluster.main.name
  capacity_providers = ["FARGATE", "FARGATE_SPOT"]

  default_capacity_provider_strategy {
    base              = 1
    weight            = 100
    capacity_provider = "FARGATE"
  }
}

# ============================================================
# CloudWatch Log Groups
# ============================================================

resource "aws_cloudwatch_log_group" "mcp_server" {
  name              = "/ecs/mcp-server"
  retention_in_days = 30
  tags              = var.tags
}

resource "aws_cloudwatch_log_group" "agents" {
  name              = "/ecs/swarm-agents"
  retention_in_days = 30
  tags              = var.tags
}

resource "aws_cloudwatch_log_group" "webapp" {
  name              = "/ecs/webapp"
  retention_in_days = 30
  tags              = var.tags
}

# ============================================================
# Task Definitions
# ============================================================

resource "aws_ecs_task_definition" "mcp_server" {
  family                   = "mcp-server"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 512
  memory                   = 1024
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([
    {
      name      = "mcp-server"
      image     = "${aws_ecr_repository.mcp_server.repository_url}:latest"
      essential = true

      portMappings = [
        {
          containerPort = 8000
          protocol      = "tcp"
        }
      ]

      environment = [
        { name = "ENV",              value = var.environment },
        { name = "PORT",             value = "8000" },
        { name = "MCP_SERVER_PORT",  value = "8000" },
        { name = "LOG_LEVEL",        value = "INFO" }
      ]

      secrets = [
        { name = "OPENAI_API_KEY",    valueFrom = "${aws_secretsmanager_secret.app_secrets.arn}:OPENAI_API_KEY::" },
        { name = "API_KEYS",          valueFrom = "${aws_secretsmanager_secret.app_secrets.arn}:API_KEYS::" }
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.mcp_server.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "ecs"
        }
      }

      healthCheck = {
        command     = ["CMD-SHELL", "curl -f http://localhost:8000/health || exit 1"]
        interval    = 30
        timeout     = 5
        retries     = 3
        startPeriod = 60
      }
    }
  ])

  tags = var.tags
}

resource "aws_ecs_task_definition" "hr_agent" {
  family                   = "hr-agent"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 512
  memory                   = 1024
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([
    {
      name      = "hr-agent"
      image     = "${aws_ecr_repository.swarm_agents.repository_url}:latest"
      essential = true

      environment = [
        { name = "ENV",        value = var.environment },
        { name = "AGENT_TYPE", value = "hr" },
        { name = "LOG_LEVEL",  value = "INFO" },
        { name = "MCP_SERVER_HOST", value = aws_lb.internal.dns_name },
        { name = "MCP_SERVER_PORT", value = "9000" }
      ]

      secrets = [
        { name = "OPENAI_API_KEY", valueFrom = "${aws_secretsmanager_secret.app_secrets.arn}:OPENAI_API_KEY::" }
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.agents.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "hr-agent"
        }
      }
    }
  ])

  tags = var.tags
}

resource "aws_ecs_task_definition" "finance_agent" {
  family                   = "finance-agent"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 512
  memory                   = 1024
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([
    {
      name      = "finance-agent"
      image     = "${aws_ecr_repository.swarm_agents.repository_url}:latest"
      essential = true

      environment = [
        { name = "ENV",        value = var.environment },
        { name = "AGENT_TYPE", value = "finance" },
        { name = "LOG_LEVEL",  value = "INFO" },
        { name = "MCP_SERVER_HOST", value = aws_lb.internal.dns_name },
        { name = "MCP_SERVER_PORT", value = "9000" }
      ]

      secrets = [
        { name = "OPENAI_API_KEY", valueFrom = "${aws_secretsmanager_secret.app_secrets.arn}:OPENAI_API_KEY::" }
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.agents.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "finance-agent"
        }
      }
    }
  ])

  tags = var.tags
}

resource "aws_ecs_task_definition" "medical_agent" {
  family                   = "medical-agent"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 512
  memory                   = 1024
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([
    {
      name      = "medical-agent"
      image     = "${aws_ecr_repository.swarm_agents.repository_url}:latest"
      essential = true

      environment = [
        { name = "ENV",        value = var.environment },
        { name = "AGENT_TYPE", value = "medical" },
        { name = "LOG_LEVEL",  value = "INFO" },
        { name = "MCP_SERVER_HOST", value = aws_lb.internal.dns_name },
        { name = "MCP_SERVER_PORT", value = "9000" }
      ]

      secrets = [
        { name = "OPENAI_API_KEY", valueFrom = "${aws_secretsmanager_secret.app_secrets.arn}:OPENAI_API_KEY::" }
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.agents.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "medical-agent"
        }
      }
    }
  ])

  tags = var.tags
}

resource "aws_ecs_task_definition" "webapp" {
  family                   = "webapp"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 256
  memory                   = 512
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([
    {
      name      = "webapp"
      image     = "${aws_ecr_repository.swarm_agents.repository_url}:webapp"
      essential = true

      portMappings = [
        {
          containerPort = 8501
          protocol      = "tcp"
        }
      ]

      environment = [
        { name = "ENV",                value = var.environment },
        { name = "MCP_SERVER_URL",     value = "http://${aws_lb.internal.dns_name}:9000" },
        { name = "PUBLIC_API_URL",     value = "http://${aws_lb.main.dns_name}/api" }
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.webapp.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "webapp"
        }
      }

      healthCheck = {
        command     = ["CMD-SHELL", "curl -f http://localhost:8501/_stcore/health || exit 1"]
        interval    = 30
        timeout     = 5
        retries     = 3
        startPeriod = 60
      }
    }
  ])

  tags = var.tags
}

# ============================================================
# ECS Services
# ============================================================

resource "aws_ecs_service" "mcp_server" {
  name            = "mcp-server"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.mcp_server.arn
  desired_count   = 2
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.ecs_tasks.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.mcp_server.arn
    container_name   = "mcp-server"
    container_port   = 8000
  }

  depends_on = [aws_lb_listener.mcp_server]

  tags = var.tags
}

resource "aws_ecs_service" "hr_agent" {
  name            = "hr-agent"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.hr_agent.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.ecs_tasks.id]
    assign_public_ip = false
  }

  tags = var.tags
}

resource "aws_ecs_service" "finance_agent" {
  name            = "finance-agent"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.finance_agent.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.ecs_tasks.id]
    assign_public_ip = false
  }

  tags = var.tags
}

resource "aws_ecs_service" "medical_agent" {
  name            = "medical-agent"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.medical_agent.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.ecs_tasks.id]
    assign_public_ip = false
  }

  tags = var.tags
}

resource "aws_ecs_service" "webapp" {
  name            = "webapp"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.webapp.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = aws_subnet.public[*].id
    security_groups  = [aws_security_group.webapp.id]
    assign_public_ip = true
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.webapp.arn
    container_name   = "webapp"
    container_port   = 8501
  }

  depends_on = [aws_lb_listener.https]

  tags = var.tags
}

# ============================================================
# Auto-scaling for MCP Server
# ============================================================

resource "aws_appautoscaling_target" "mcp_server" {
  max_capacity       = 10
  min_capacity       = 2
  resource_id        = "service/${aws_ecs_cluster.main.name}/${aws_ecs_service.mcp_server.name}"
  scalable_dimension = "ecs:service:DesiredCount"
  service_namespace  = "ecs"
}

resource "aws_appautoscaling_policy" "mcp_server_cpu" {
  name               = "mcp-server-cpu-scaling"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.mcp_server.resource_id
  scalable_dimension = aws_appautoscaling_target.mcp_server.scalable_dimension
  service_namespace  = aws_appautoscaling_target.mcp_server.service_namespace

  target_tracking_scaling_policy_configuration {
    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageCPUUtilization"
    }
    target_value = 70.0
  }
}
