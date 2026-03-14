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
