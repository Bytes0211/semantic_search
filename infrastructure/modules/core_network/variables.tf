terraform {
  required_version = ">= 1.5.0"
}

#############################################
# Core Network Module Variables
#############################################

variable "project" {
  type        = string
  description = "Project identifier applied to names and tags (e.g., semantic-search)."
}

variable "environment" {
  type        = string
  description = "Deployment environment label (e.g., dev, staging, prod)."
}

variable "name_prefix" {
  type        = string
  description = "Optional override for resource name prefixes; defaults to <project>-core when empty."
  default     = ""
}

variable "tags" {
  type        = map(string)
  description = "Additional tags merged into every resource managed by this module."
  default     = {}
}

variable "vpc_cidr" {
  type        = string
  description = "Primary IPv4 CIDR block allocated to the VPC (e.g., 10.0.0.0/16)."
  default     = "10.0.0.0/16"

  validation {
    condition     = can(cidrnetmask(var.vpc_cidr))
    error_message = "The provided vpc_cidr must be a valid IPv4 CIDR block."
  }
}

variable "availability_zones" {
  type        = list(string)
  description = "Optional explicit list of availability zones to use; leave empty to let the module auto-select."
  default     = []
}

variable "default_az_count" {
  type        = number
  description = "Number of AZs to select automatically when availability_zones is not provided."
  default     = 2

  validation {
    condition     = var.default_az_count >= 1 && var.default_az_count <= 6
    error_message = "default_az_count must be between 1 and 6."
  }
}

variable "subnet_newbits" {
  type        = number
  description = "Additional network bits used when deriving subnet CIDR blocks from the VPC CIDR."
  default     = 4

  validation {
    condition     = var.subnet_newbits >= 1 && var.subnet_newbits <= 10
    error_message = "subnet_newbits must be between 1 and 10."
  }
}

variable "enable_internet_gateway" {
  type        = bool
  description = "Whether to provision an internet gateway and public route for outbound internet access."
  default     = true
}

variable "create_nat_gateway" {
  type        = bool
  description = "Whether to provision a managed NAT gateway in the first public subnet."
  default     = false

  validation {
    condition     = var.create_nat_gateway == false || var.enable_internet_gateway == true
    error_message = "A NAT gateway requires enable_internet_gateway to be true."
  }
}

variable "enable_flow_logs" {
  type        = bool
  description = "Enable VPC flow logs for traffic observability."
  default     = false
}

variable "flow_log_destination_type" {
  type        = string
  description = "Destination type for VPC flow logs: either cloud-watch-logs or s3."
  default     = "cloud-watch-logs"

  validation {
    condition     = contains(["cloud-watch-logs", "s3"], var.flow_log_destination_type)
    error_message = "flow_log_destination_type must be either cloud-watch-logs or s3."
  }
}

variable "flow_log_destination_arn" {
  type        = string
  description = "ARN for the CloudWatch Log Group or S3 bucket that receives flow logs. Required when enable_flow_logs is true."
  default     = ""
}

variable "flow_log_iam_role_arn" {
  type        = string
  description = "IAM role ARN used when delivering flow logs to CloudWatch Logs."
  default     = ""
}
