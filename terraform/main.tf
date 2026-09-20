# Infrastructure scaffold.
# We will add the AWS VPC/EKS resources step-by-step during the lab.
# Keeping this file intentionally small makes the project easier to learn.

resource "aws_s3_bucket" "project_artifacts" {
  bucket = "${var.project_name}-${var.environment}-artifacts-${var.bucket_suffix}"

  tags = {
    Project     = var.project_name
    Environment = var.environment
  }
}
