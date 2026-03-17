output "function_arn" {
  description = "ARN of the Lambda search runtime function."
  value       = aws_lambda_function.search.arn
}

output "function_name" {
  description = "Logical name of the Lambda function."
  value       = aws_lambda_function.search.function_name
}

output "api_endpoint" {
  description = "HTTPS endpoint exposed by API Gateway for the semantic search runtime."
  value       = "${aws_apigatewayv2_api.http_api.api_endpoint}${var.api_gateway_stage == "$default" ? "" : "/${var.api_gateway_stage}"}"
}

output "endpoint" {
  description = "Alias of the API Gateway endpoint for compatibility with environment stacks."
  value       = "${aws_apigatewayv2_api.http_api.api_endpoint}${var.api_gateway_stage == "$default" ? "" : "/${var.api_gateway_stage}"}"
}

output "api_id" {
  description = "Identifier of the API Gateway HTTP API."
  value       = aws_apigatewayv2_api.http_api.id
}

output "api_execution_arn" {
  description = "Execution ARN for invoking the API Gateway stage."
  value       = aws_apigatewayv2_api.http_api.execution_arn
}

output "api_stage_name" {
  description = "Deployed stage name for the API Gateway HTTP API."
  value       = aws_apigatewayv2_stage.default.name
}

output "api_log_group_name" {
  description = "CloudWatch Log Group capturing API Gateway access logs."
  value       = aws_cloudwatch_log_group.api_gw.name
}

output "function_qualified_arn" {
  description = "Qualified ARN of the published Lambda function version."
  value       = aws_lambda_function.search.qualified_arn
}

output "function_version" {
  description = "Latest published version of the Lambda function."
  value       = aws_lambda_function.search.version
}

output "function_alias_arn" {
  description = "ARN of the Lambda alias used for provisioned concurrency, if enabled."
  value       = length(aws_lambda_alias.current) > 0 ? aws_lambda_alias.current[0].arn : null
}

output "log_group_name" {
  description = "CloudWatch Log Group capturing Lambda execution logs."
  value       = aws_cloudwatch_log_group.lambda.name
}

output "security_group_id" {
  description = "Security group attached to Lambda ENIs when VPC networking is enabled."
  value       = aws_security_group.lambda.id
}

output "role_name" {
  description = "Name of the IAM role assumed by the Lambda function."
  value       = aws_iam_role.lambda.name
}

output "role_arn" {
  description = "ARN of the IAM role assumed by the Lambda function."
  value       = aws_iam_role.lambda.arn
}
