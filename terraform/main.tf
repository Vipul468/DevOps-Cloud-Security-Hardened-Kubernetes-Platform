module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 6.0"

  name = "hardened-k8s-vpc"
  cidr = "10.0.0.0/16"

  azs = ["us-east-1a", "us-east-1b"]

  private_subnets = [
    "10.0.1.0/24",
    "10.0.2.0/24"
  ]

  public_subnets = [
    "10.0.101.0/24",
    "10.0.102.0/24"
  ]

  enable_nat_gateway = true
  single_nat_gateway  = true

  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = {
    Project     = "Security-Hardened-Kubernetes-Platform"
    Environment = var.environment
  }
}

module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 21.0"

  name               = var.project_name
  kubernetes_version = "1.33"

  endpoint_public_access = true

  vpc_id     = module.vpc.vpc_id
  subnet_ids = module.vpc.private_subnets

  enable_cluster_creator_admin_permissions = true

  addons = {
    vpc-cni = {
      most_recent    = true
      before_compute = true
    }

    kube-proxy = {
      most_recent    = true
      before_compute = true
    }

    coredns = {
      most_recent    = true
      before_compute = true
    }
  }

  eks_managed_node_groups = {
    default = {
      name               = "k8s-node"
      kubernetes_version = "1.33"

      instance_types = ["t3.small"]

      min_size     = 2
      desired_size = 2
      max_size     = 2

      capacity_type = "ON_DEMAND"

      labels = {
        role = "worker"
      }

      metadata_options = {
        http_endpoint               = "enabled"
        http_tokens                 = "required"
        http_put_response_hop_limit = 1
      }

      tags = {
        Project     = "Security-Hardened-Kubernetes-Platform"
        Environment = var.environment
      }
    }
  }

  tags = {
    Project     = "Security-Hardened-Kubernetes-Platform"
    Environment = var.environment
  }
}

resource "terraform_data" "update_kubeconfig" {
  triggers_replace = [
    module.eks.cluster_name
  ]

  provisioner "local-exec" {
    command = "aws eks update-kubeconfig --region ${var.aws_region} --name ${module.eks.cluster_name}"
  }

  depends_on = [module.eks]
}

resource "aws_ecr_repository" "app" {
  name                 = "security-hardened-k8s-platform"

  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = {
    Project     = "Security-Hardened-Kubernetes-Platform"
    Environment = var.environment
  }
}