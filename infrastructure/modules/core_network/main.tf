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
  name_prefix = var.name_prefix != "" ? var.name_prefix : "${var.project}-core"

  azs = (var.availability_zones != null && length(var.availability_zones) > 0
    ? var.availability_zones
    : slice(data.aws_availability_zones.available.names, 0, var.default_az_count)
  )

  public_subnets = {
    for idx, az in local.azs :
    az => cidrsubnet(var.vpc_cidr, var.subnet_newbits, idx)
  }

  private_subnets = {
    for idx, az in local.azs :
    az => cidrsubnet(var.vpc_cidr, var.subnet_newbits, idx + length(local.azs))
  }

  common_tags = merge({
    "Project"     = var.project,
    "Environment" = var.environment,
    "Module"      = "core-network"
  }, var.tags)
}

data "aws_availability_zones" "available" {
  state = "available"
}

resource "aws_vpc" "this" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = merge(local.common_tags, {
    "Name" = "${local.name_prefix}-vpc"
  })
}

resource "aws_internet_gateway" "this" {
  count  = var.enable_internet_gateway ? 1 : 0
  vpc_id = aws_vpc.this.id

  tags = merge(local.common_tags, {
    "Name" = "${local.name_prefix}-igw"
  })
}

resource "aws_subnet" "public" {
  for_each                = local.public_subnets
  vpc_id                  = aws_vpc.this.id
  cidr_block              = each.value
  availability_zone       = each.key
  map_public_ip_on_launch = true

  tags = merge(local.common_tags, {
    "Name" = "${local.name_prefix}-public-${each.key}"
    "Tier" = "public"
  })
}

resource "aws_subnet" "private" {
  for_each                = local.private_subnets
  vpc_id                  = aws_vpc.this.id
  cidr_block              = each.value
  availability_zone       = each.key
  map_public_ip_on_launch = false

  tags = merge(local.common_tags, {
    "Name" = "${local.name_prefix}-private-${each.key}"
    "Tier" = "private"
  })
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.this.id

  tags = merge(local.common_tags, {
    "Name" = "${local.name_prefix}-public-rt"
  })
}

resource "aws_route" "public_internet" {
  count                  = var.enable_internet_gateway ? 1 : 0
  route_table_id         = aws_route_table.public.id
  destination_cidr_block = "0.0.0.0/0"
  gateway_id             = aws_internet_gateway.this[0].id
}

resource "aws_route_table_association" "public" {
  for_each       = aws_subnet.public
  subnet_id      = each.value.id
  route_table_id = aws_route_table.public.id
}

resource "aws_eip" "nat" {
  count  = var.create_nat_gateway ? 1 : 0
  domain = "vpc"

  tags = merge(local.common_tags, {
    "Name" = "${local.name_prefix}-nat-eip"
  })
}

resource "aws_nat_gateway" "this" {
  count         = var.create_nat_gateway ? 1 : 0
  allocation_id = aws_eip.nat[0].id
  subnet_id     = tolist([for subnet in aws_subnet.public : subnet.id])[0]

  tags = merge(local.common_tags, {
    "Name" = "${local.name_prefix}-nat"
  })

  depends_on = [
    aws_internet_gateway.this
  ]
}

resource "aws_route_table" "private" {
  vpc_id = aws_vpc.this.id

  tags = merge(local.common_tags, {
    "Name" = "${local.name_prefix}-private-rt"
  })
}

resource "aws_route" "private_nat" {
  count                  = var.create_nat_gateway ? 1 : 0
  route_table_id         = aws_route_table.private.id
  destination_cidr_block = "0.0.0.0/0"
  nat_gateway_id         = aws_nat_gateway.this[0].id
}

resource "aws_route_table_association" "private" {
  for_each       = aws_subnet.private
  subnet_id      = each.value.id
  route_table_id = aws_route_table.private.id
}

resource "aws_flow_log" "this" {
  count = var.enable_flow_logs ? 1 : 0

  log_destination      = var.flow_log_destination_arn
  log_destination_type = var.flow_log_destination_type
  traffic_type         = "ALL"
  vpc_id               = aws_vpc.this.id
  iam_role_arn = (var.flow_log_destination_type == "cloud-watch-logs" && var.flow_log_iam_role_arn != ""
    ? var.flow_log_iam_role_arn
    : null
  )

  lifecycle {
    precondition {
      condition     = var.flow_log_destination_arn != ""
      error_message = "flow_log_destination_arn must be set when enable_flow_logs is true."
    }
    precondition {
      condition     = var.flow_log_destination_type != "cloud-watch-logs" || var.flow_log_iam_role_arn != ""
      error_message = "flow_log_iam_role_arn must be set when flow_log_destination_type is cloud-watch-logs."
    }
  }

  tags = merge(local.common_tags, {
    "Name" = "${local.name_prefix}-flow-log"
  })
}

variable "project" {
  type        = string
  description = "Identifier used for tagging and naming."
}

variable "environment" {
  type        = string
  description = "Environment label (e.g., dev, staging, prod)."
}

variable "name_prefix" {
  type        = string
  description = "Optional override for resource name prefixes."
  default     = ""
}

variable "tags" {
  type        = map(string)
  description = "Additional tags to merge into all resources."
  default     = {}
}

variable "vpc_cidr" {
  type        = string
  description = "CIDR block for the VPC."
  default     = "10.0.0.0/16"

  validation {
    condition     = can(cidrnetmask(var.vpc_cidr))
    error_message = "The provided vpc_cidr must be a valid IPv4 CIDR block."
  }
}

variable "availability_zones" {
  type        = list(string)
  description = "Optional explicit list of availability zones to use. Leave empty to let the module choose."
  default     = []
}

variable "default_az_count" {
  type        = number
  description = "Number of availability zones to select when availability_zones is empty."
  default     = 2

  validation {
    condition     = var.default_az_count >= 1 && var.default_az_count <= 6
    error_message = "default_az_count must be between 1 and 6."
  }
}

variable "subnet_newbits" {
  type        = number
  description = "Number of additional network bits to use when calculating subnet CIDRs."
  default     = 4

  validation {
    condition     = var.subnet_newbits >= 1 && var.subnet_newbits <= 10
    error_message = "subnet_newbits must be between 1 and 10."
  }
}

variable "enable_internet_gateway" {
  type        = bool
  description = "When true, create an internet gateway and public route."
  default     = true
}

variable "create_nat_gateway" {
  type        = bool
  description = "When true, provision a managed NAT gateway in the first public subnet."
  default     = false

  validation {
    condition     = var.create_nat_gateway == false || var.enable_internet_gateway == true
    error_message = "A NAT gateway requires enable_internet_gateway to be true."
  }
}

variable "enable_flow_logs" {
  type        = bool
  description = "Enable VPC flow logs for the network."
  default     = false
}

variable "flow_log_destination_type" {
  type        = string
  description = "Destination type for flow logs (cloud-watch-logs or s3)."
  default     = "cloud-watch-logs"

  validation {
    condition     = contains(["cloud-watch-logs", "s3"], var.flow_log_destination_type)
    error_message = "flow_log_destination_type must be either cloud-watch-logs or s3."
  }
}

variable "flow_log_destination_arn" {
  type        = string
  description = "ARN of the CloudWatch Log Group or S3 bucket for flow logs."
  default     = ""
}

variable "flow_log_iam_role_arn" {
  type        = string
  description = "IAM role ARN used when flow logs are delivered to CloudWatch Logs."
  default     = ""
}
