# Security Architecture

High-level overview of the security boundaries, controls, and data flow for the semantic search platform deployed on AWS.

---

```mermaid
%%{init: {'flowchart': {'diagramPadding': 50, 'rankSpacing': 100, 'nodeSpacing': 60}, 'themeVariables': {'fontSize': '20px', 'fontFamily': 'trebuchet ms, verdana, arial, sans-serif'}}}%%
flowchart TD

    USER(["👤 Client / User"])

    subgraph PERIMETER["① Perimeter"]
        ALB["ALB / API Gateway
        ─────────────────
        HTTPS only · VPC-restricted
        mTLS optional"]
    end

    subgraph VPC["② VPC — Private Subnets"]
        direction TB
        SVC["Search Service
        ─────────────────
        ECS / Fargate  ·  Lambda
        private subnet"]
        IAM["IAM Roles
        ─────────────────
        Permission Boundaries
        Deny Guardrails"]
        SG["Security Groups
        ─────────────────
        HTTPS-only egress
        VPC CIDR restricted"]
    end

    subgraph VPCE["③ VPC Endpoints — No Public Internet"]
        direction LR
        S3_EP["S3
        ───────
        Gateway Endpoint"]
        BRCK_EP["Bedrock
        ───────
        Interface Endpoint"]
        CW_EP["CloudWatch Logs
        ───────
        Interface Endpoint"]
        SQS_EP["SQS · SNS
        ───────
        Interface Endpoint"]
        ECR_EP["ECR API · ECR DKR
        ───────
        Interface Endpoint"]
    end

    subgraph DATA["④ Encrypted Data Plane"]
        direction LR
        S3["S3 Buckets
        ───────────
        SSE-KMS encrypted
        Index · Records · Embeddings"]
        KMS["KMS CMK
        ───────────
        Auto-rotation
        Encrypts S3 · SQS · SNS"]
        SM["Secrets Manager
        ───────────
        Credential storage
        Rotation schedules"]
    end

    subgraph AUDIT["⑤ Audit & Observability"]
        direction LR
        CT["CloudTrail
        ───────────
        All AWS API calls
        Retention policy"]
        CW["CloudWatch
        ───────────
        Metrics · Alarms
        Dashboards · Logs"]
    end

    USER        -->|"HTTPS"| ALB
    ALB         -->|"private subnet only"| SVC
    IAM         -.->|"least-privilege scoping"| SVC
    SG          -.->|"egress restricted"| SVC
    SVC         -->|"all traffic via endpoints"| VPCE
    S3_EP       --> S3
    S3          <-->|"SSE-KMS"| KMS
    SVC         -.->|"fetch credentials"| SM
    SVC         -.->|"structured JSON logs"| CW
    SVC         -.->|"API audit trail"| CT
```

---

## Layer Notes

### ① Perimeter
Inbound traffic terminates at the Application Load Balancer (ALB) or API Gateway — the only entry point exposed outside the VPC. All traffic is HTTPS; mutual TLS (`mTLS`) or VPC-based access restrictions can be enabled for production.

### ② VPC — Private Subnets
The search service runs on private subnets with no direct internet access. Each service role carries an IAM permission boundary that caps maximum permissions and inline deny guardrails that block lateral movement, privilege escalation, and bucket destruction even if a container is compromised. Security groups restrict egress to HTTPS-only traffic within the VPC CIDR.

### ③ VPC Endpoints
All AWS service calls (S3, Bedrock, CloudWatch Logs, SQS, SNS, ECR) are routed through VPC interface or gateway endpoints. No control-plane or data-plane traffic leaves AWS networking.

### ④ Encrypted Data Plane
S3 buckets (canonical records, vector index, embeddings) and SQS/SNS queues are encrypted at rest using a customer-managed KMS key with automatic rotation. Credentials are stored in Secrets Manager with rotation schedules and never hardcoded in task definitions or environment variables.

### ⑤ Audit & Observability
CloudTrail captures every AWS API call with retention policies for compliance. CloudWatch provides structured JSON logs, query latency metrics, error-rate alarms (fires at >2%), and dashboards for end-to-end runtime monitoring.
