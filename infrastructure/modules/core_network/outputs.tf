#####################################################
# Core Network Module Outputs
#####################################################

output "vpc_id" {
  description = "Identifier of the created VPC."
  value       = aws_vpc.this.id
}

output "availability_zones" {
  description = "Availability zones in use by the module."
  value       = local.azs
}

output "public_subnet_ids" {
  description = "List of public subnet identifiers."
  value       = [for subnet in aws_subnet.public : subnet.id]
}

output "private_subnet_ids" {
  description = "List of private subnet identifiers."
  value       = [for subnet in aws_subnet.private : subnet.id]
}

output "public_route_table_id" {
  description = "Identifier of the public route table."
  value       = aws_route_table.public.id
}

output "private_route_table_id" {
  description = "Identifier of the private route table."
  value       = aws_route_table.private.id
}

output "nat_gateway_id" {
  description = "Identifier of the NAT gateway when created."
  value       = var.create_nat_gateway ? aws_nat_gateway.this[0].id : null
}

output "flow_log_id" {
  description = "Identifier of the VPC flow log if enabled."
  value       = var.enable_flow_logs ? aws_flow_log.this[0].id : null
}
