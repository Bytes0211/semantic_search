output "cluster_id" {
  description = "ECS cluster hosting the semantic search service."
  value       = aws_ecs_cluster.this.id
}

output "service_name" {
  description = "Name of the ECS service managing runtime tasks."
  value       = aws_ecs_service.this.name
}

output "task_role_arn" {
  description = "IAM role ARN assumed by ECS tasks."
  value       = aws_iam_role.task.arn
}

output "execution_role_arn" {
  description = "IAM execution role ARN used for image pulls and logging."
  value       = aws_iam_role.task_execution.arn
}

output "load_balancer_dns" {
  description = "DNS name of the Application Load Balancer fronting the runtime."
  value       = aws_lb.this.dns_name
}

output "endpoint" {
  description = "HTTP endpoint clients can use to reach the semantic search API."
  value       = format("http://%s", aws_lb.this.dns_name)
}

output "target_group_arn" {
  description = "ARN of the target group forwarding traffic to the service."
  value       = aws_lb_target_group.this.arn
}

output "log_group_name" {
  description = "CloudWatch Log Group capturing application output."
  value       = aws_cloudwatch_log_group.this.name
}

output "load_balancer_arn" {
  description = "ARN of the Application Load Balancer."
  value       = aws_lb.this.arn
}

output "load_balancer_arn_suffix" {
  description = "ARN suffix for the Application Load Balancer (used in metrics dimensions)."
  value       = aws_lb.this.arn_suffix
}

output "target_group_arn_suffix" {
  description = "ARN suffix for the target group (used in metrics dimensions)."
  value       = aws_lb_target_group.this.arn_suffix
}

output "autoscaling_resource_id" {
  description = "Resource ID used by Application Auto Scaling for the ECS service."
  value       = aws_appautoscaling_target.ecs.resource_id
}
