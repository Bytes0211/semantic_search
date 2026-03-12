# Core Network Module

This module establishes the base networking stack (VPC, subnets, routing, and security boundaries) that every semantic search deployment composes. It is the first Terraform component applied in any environment, providing shared networking primitives for data, compute, and observability layers.

## Module Contents

- **VPC skeleton:** CIDR configuration, DNS settings, flow logs toggle.
- **Subnets:** Parameterized public and private subnet definitions across availability zones.
- **Routing:** Internet/NAT gateway wiring, route table associations, VPC endpoints (optional).
- **Security groups & NACL placeholders:** Default-deny posture with module outputs for downstream services.
- **Outputs:** Exported IDs/ARNs to stitch into data plane, vector store, and runtime modules.

## Phase Documentation Placeholders

### Phase 0 — Planning & Alignment
> _TODO: Document CIDR planning worksheets, naming conventions, and environment-specific constraints._

### Phase 1 — Foundation & Infrastructure
> _TODO: Provide step-by-step Terraform usage, variable examples (`tfvars`), and validation checks prior to apply._

### Phase 2 — Data Ingestion Layer
> _TODO: Describe additional endpoint or subnet requirements when enabling ingestion services (batch or streaming)._

### Phase 3 — Embedding & Vector Services
> _TODO: Capture security group rules and subnet placement guidance for embedding providers and vector stores._

### Phase 4 — Search Runtime & Interfaces
> _TODO: Outline load balancer, API gateway, or private link considerations for runtime deployments._

### Phase 5 — Quality & Launch Readiness
> _TODO: List network verification tasks (reachability tests, flow logs review, compliance evidence) before launch._

## Next Steps

- Implement Terraform code with variables for CIDR blocks, AZ spread, and optional endpoints.
- Author examples demonstrating integration with `modules/data_plane` and `modules/search_service_*`.
- Backfill each phase placeholder with concrete procedures as those phases complete.