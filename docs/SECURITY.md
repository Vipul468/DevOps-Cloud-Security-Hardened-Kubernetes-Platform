# Security Design

Initial security controls included in the project:

1. Container runs as a non-root user.
2. Kubernetes pod uses `runAsNonRoot`.
3. Linux capabilities are dropped.
4. Privilege escalation is disabled.
5. Root filesystem is read-only.
6. RuntimeDefault seccomp profile is enabled.
7. Service account token automount is disabled.
8. Namespace Pod Security Admission labels use the `restricted` profile.
9. Kubernetes RBAC is minimal and the application Role has no permissions.
10. NetworkPolicy starts with default-deny ingress and explicitly allows application traffic.
11. CPU and memory requests/limits are defined.
12. Health and readiness probes are configured.

Next hardening stages:
- Image vulnerability scanning with Trivy
- Dependency scanning
- Secret management
- Signed images / provenance
- Kyverno or Gatekeeper policies
- TLS
- EKS private networking
- AWS IAM Roles for Service Accounts (IRSA)
- Centralized logging and monitoring
