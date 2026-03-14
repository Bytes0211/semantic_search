terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0"
    }
  }
}

# Phase 3 stub — spot-hosted embedding infrastructure is not yet implemented.
# See README.md for the expected scope of this module.
