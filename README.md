# DevOps & Cloud Engineer | Security Hardened Kubernetes Platform

A security-hardened DevOps and Kubernetes project deployed on AWS using Terraform, Docker, Amazon ECR, Amazon EKS, GitHub Actions, Trivy, IAM, ALB/Ingress, Prometheus and Grafana.

## Project Objective

The objective of this project is to build an end-to-end DevSecOps deployment workflow where application code moves from development to GitHub, passes CI/CD and security scanning, is containerized and stored in Amazon ECR, and is finally deployed on a security-hardened Amazon EKS cluster with monitoring.

---

# Architecture

```text
Developer
    |
    | 1. Write Application Code
    v
GitHub Repository
    |
    | 2. Git Push
    v
GitHub Actions
    |
    +---- Build & Test
    |
    +---- Trivy Security Scan
    |
    v
Terraform
    |
    +---- IAM
    +---- VPC / Networking
    +---- EKS
    +---- Worker Nodes
    |
    v
Docker Image
    |
    v
Amazon ECR
    |
    v
Amazon EKS
    |
    +---- Kubernetes Deployment
    +---- Service
    +---- RBAC
    +---- NetworkPolicy
    |
    v
AWS Application Load Balancer / Ingress
    |
    v
Application
    |
    +-------------------+
    |                   |
    v                   v
Prometheus           Grafana
    |                   |
    +---------+---------+
              |
              v
       CPU / Memory
       Monitoring
