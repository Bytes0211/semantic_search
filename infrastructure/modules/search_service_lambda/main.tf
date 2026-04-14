terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0"
    }
  }
}

locals {
  name_prefix = var.name_prefix != "" ? var.name_prefix : "${var.project}-${var.environment}-lambda-search"

  common_tags = merge({
    Project     = var.project
    Environment = var.environment
    Module      = "search-service-lambda"
  }, var.tags)

  default_environment = {
    SEARCH_RUNTIME         = "lambda"
    VECTOR_STORE_ENDPOINT  = var.vector_store_endpoint
    EMBEDDING_ENDPOINT     = var.embedding_endpoint
    INGESTION_QUEUE_ARN    = var.ingestion_queue_arn
    REINDEX_TOPIC_ARN      = var.reindex_topic_arn
    LOG_LEVEL              = var.log_level
    METRICS_NAMESPACE      = var.metrics_namespace
    ENABLE_REQUEST_TRACING = tostring(var.enable_request_tracing)
    ENABLE_QUERY_LOGGING   = tostring(var.enable_query_logging)
    MAX_CONCURRENT_QUERIES = tostring(var.max_concurrent_queries)
    DEFAULT_TOP_K          = tostring(var.default_top_k)
    MAX_TOP_K              = tostring(var.max_top_k)
    CANDIDATE_MULTIPLIER   = tostring(var.candidate_multiplier)
    HEALTHCHECK_PATH       = var.healthcheck_path
    READINESS_PATH         = var.readiness_path
  }

  container_environment = merge(local.default_environment, var.environment_variables)
}

resource "aws_iam_role" "lambda" {
  name = "${local.name_prefix}-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })

  permissions_boundary = var.permissions_boundary_arn != "" ? var.permissions_boundary_arn : null

  tags = local.common_tags
}

resource "aws_iam_role_policy" "lambda_deny_guardrail" {
  count  = var.deny_guardrail_policy_json != "" ? 1 : 0
  name   = "${local.name_prefix}-deny-guardrail"
  role   = aws_iam_role.lambda.id
  policy = var.deny_guardrail_policy_json
}

resource "aws_iam_role_policy_attachment" "basic_execution" {
  role       = aws_iam_role.lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy_attachment" "vpc_access" {
  count      = length(var.subnet_ids) > 0 ? 1 : 0
  role       = aws_iam_role.lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
}

resource "aws_iam_role_policy" "secrets_access" {
  name = "${local.name_prefix}-secrets"
  role = aws_iam_role.lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["secretsmanager:GetSecretValue", "kms:Decrypt"]
        Resource = values(var.secret_arn_values)
      }
    ]
  })
}

resource "aws_security_group" "lambda" {
  name        = "${local.name_prefix}-sg"
  description = "Security group for Lambda search runtime"
  vpc_id      = var.vpc_id

  dynamic "egress" {
    for_each = var.restrict_egress ? [] : [1]
    content {
      description = "Allow outbound traffic (unrestricted)"
      from_port   = 0
      to_port     = 0
      protocol    = "-1"
      cidr_blocks = ["0.0.0.0/0"]
    }
  }

  dynamic "egress" {
    for_each = var.restrict_egress ? [1] : []
    content {
      description = "HTTPS egress (NAT gateway or VPC endpoints)"
      from_port   = 443
      to_port     = 443
      protocol    = "tcp"
      cidr_blocks = ["0.0.0.0/0"]
    }
  }

  tags = local.common_tags
}

resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${local.name_prefix}"
  retention_in_days = var.log_retention_in_days
  tags              = local.common_tags
}

resource "aws_lambda_function" "search" {
  function_name = "${local.name_prefix}-fn"
  role          = aws_iam_role.lambda.arn
  package_type  = "Image"
  image_uri     = var.container_image
  timeout       = var.timeout_seconds
  memory_size   = var.memory_mb
  architectures = [var.lambda_architecture]
  publish       = var.enable_provisioned_concurrency

  environment {
    variables = local.container_environment
  }

  dynamic "vpc_config" {
    for_each = length(var.subnet_ids) > 0 ? [1] : []
    content {
      subnet_ids         = var.subnet_ids
      security_group_ids = concat([aws_security_group.lambda.id], var.additional_security_group_ids)
    }
  }

  dynamic "ephemeral_storage" {
    for_each = var.enable_ephemeral_storage ? [1] : []
    content {
      size = var.ephemeral_storage_mb
    }
  }

  tracing_config {
    mode = var.xray_tracing_mode
  }

  tags = local.common_tags

  depends_on = [
    aws_cloudwatch_log_group.lambda
  ]
}

resource "aws_lambda_provisioned_concurrency_config" "search" {
  count = var.enable_provisioned_concurrency ? 1 : 0

  function_name                     = aws_lambda_function.search.function_name
  qualifier                         = aws_lambda_alias.current[0].name
  provisioned_concurrent_executions = var.provisioned_concurrency_count
}

resource "aws_lambda_alias" "current" {
  count            = var.enable_provisioned_concurrency ? 1 : 0
  name             = "live"
  description      = "Alias for provisioned concurrency management"
  function_name    = aws_lambda_function.search.function_name
  function_version = aws_lambda_function.search.version
}

resource "aws_apigatewayv2_api" "http_api" {
  name          = "${local.name_prefix}-api"
  protocol_type = "HTTP"
  tags          = local.common_tags
}

resource "aws_apigatewayv2_integration" "lambda" {
  api_id                 = aws_apigatewayv2_api.http_api.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.search.invoke_arn
  payload_format_version = "2.0"
  timeout_milliseconds   = var.api_gateway_timeout_ms
}

resource "aws_apigatewayv2_route" "search" {
  api_id    = aws_apigatewayv2_api.http_api.id
  route_key = "POST /v1/search"
  target    = "integrations/${aws_apigatewayv2_integration.lambda.id}"
}

resource "aws_apigatewayv2_route" "health" {
  api_id    = aws_apigatewayv2_api.http_api.id
  route_key = "GET ${var.healthcheck_path}"
  target    = "integrations/${aws_apigatewayv2_integration.lambda.id}"
}

resource "aws_apigatewayv2_route" "readiness" {
  api_id    = aws_apigatewayv2_api.http_api.id
  route_key = "GET ${var.readiness_path}"
  target    = "integrations/${aws_apigatewayv2_integration.lambda.id}"
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.http_api.id
  name        = var.api_gateway_stage
  auto_deploy = true

  tags = local.common_tags

  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.api_gw.arn
    format = jsonencode({
      requestId               = "$context.requestId"
      requestTime             = "$context.requestTime"
      httpMethod              = "$context.httpMethod"
      routeKey                = "$context.routeKey"
      status                  = "$context.status"
      responseLength          = "$context.responseLength"
      integrationErrorMessage = "$context.integrationErrorMessage"
    })
  }
}

resource "aws_cloudwatch_log_group" "api_gw" {
  name              = "/aws/apigateway/${local.name_prefix}"
  retention_in_days = var.log_retention_in_days
  tags              = local.common_tags
}

resource "aws_lambda_permission" "api_gateway" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.search.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.http_api.execution_arn}/*/*"
}

resource "aws_cloudwatch_metric_alarm" "lambda_throttle" {
  alarm_name          = "${local.name_prefix}-throttles"
  alarm_description   = "Alert when the Lambda search runtime throttles requests."
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "Throttles"
  namespace           = "AWS/Lambda"
  period              = 60
  statistic           = "Sum"
  threshold           = var.alarm_throttle_threshold
  treat_missing_data  = "notBreaching"

  dimensions = {
    FunctionName = aws_lambda_function.search.function_name
  }

  tags = local.common_tags
}
