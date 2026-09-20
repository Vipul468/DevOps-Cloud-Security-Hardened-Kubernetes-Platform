variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-2"
}

variable "project_name" {
  description = "Project name"
  type        = string
  default     = "hardened-k8s"
}

variable "environment" {
  description = "Environment name"
  type        = string
  default     = "dev"
}

variable "bucket_suffix" {
  description = "Unique suffix for the S3 bucket name"
  type        = string
  sensitive   = false
}
