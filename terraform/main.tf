terraform {
  required_version = ">= 1.5"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project   = "tfm-caudales"
      ManagedBy = "Terraform"
      Owner     = "tfm-grupo"
    }
  }
}

data "aws_caller_identity" "current" {}

locals {
  project     = "tfm-caudales"
  account_id  = data.aws_caller_identity.current.account_id
  bucket_name = "${local.project}-${local.account_id}"
}
