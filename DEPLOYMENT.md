# RetailIQ — Production Deployment Guide

> **Target Platform**: AWS ECS Fargate (adaptable to GCP Cloud Run / DigitalOcean App Platform)
> **Last Updated**: February 2026

---

## Table of Contents

1. [Architecture Diagram](#1-architecture-diagram)
2. [Environment Variables](#2-environment-variables)
3. [Production Dockerfile](#3-production-dockerfile)
4. [Entrypoint & Migration Safety](#4-entrypoint--migration-safety)
5. [AWS ECS Deployment Steps](#5-aws-ecs-deployment-steps)
6. [Security Hardening Checklist](#6-security-hardening-checklist)
7. [Monitoring & Logging](#7-monitoring--logging)
8. [Common Failure Modes & Mitigation](#8-common-failure-modes--mitigation)
9. [Cost Optimization](#9-cost-optimization)
10. [CI/CD Integration](#10-cicd-integration)

---

## 1. Architecture Diagram

```
                            ┌──────────────────────────────────────────────┐
                            │              AWS Cloud (VPC)                 │
                            │                                              │
                            │  ┌─────────────────────────────────────────┐ │
  Users ──── HTTPS ────────►│  │  Application Load Balancer (ALB)        │ │
                            │  │  • TLS termination (ACM certificate)    │ │
                            │  │  • Health check: GET /health            │ │
                            │  │  • Idle timeout: 60s                    │ │
                            │  └────────────────┬────────────────────────┘ │
                            │                   │                          │
                            │  ┌────────────────▼────────────────────────┐ │
                            │  │  ECS Service: API (Fargate)             │ │
                            │  │  • Image: retailiq:latest               │ │
                            │  │  • SERVICE_ROLE=api                     │ │
                            │  │  • Min 2 / Max 10 tasks                 │ │
                            │  │  • Autoscale: CPU > 60%                 │ │
                            │  │  • 1 vCPU / 2 GB RAM per task           │ │
                            │  │  • Gunicorn (gthread, 3 workers × 4 threads)│
                            │  └──────┬──────────────────────┬───────────┘ │
                            │         │                      │             │
                            │  ┌──────▼──────────┐  ┌───────▼──────────┐  │
                            │  │ ECS: Worker      │  │ ECS: Beat        │  │
                            │  │ (Fargate)        │  │ (Fargate)        │  │
                            │  │ SERVICE_ROLE=    │  │ SERVICE_ROLE=    │  │
                            │  │   worker         │  │   beat           │  │
                            │  │ 2-8 tasks        │  │ 1 task (singleton)│ │
                            │  │ 0.5 vCPU/1GB     │  │ 0.25 vCPU/0.5GB │  │
                            │  └──────┬──────────┘  └───────┬──────────┘  │
                            │         │                      │             │
                            │  ═══════╧══════════════════════╧═══════════  │
                            │         │         VPC Private Subnets        │
                            │  ┌──────▼──────────┐  ┌───────▼──────────┐  │
                            │  │ Amazon RDS       │  │ Amazon ElastiCache│ │
                            │  │ (PostgreSQL 15)  │  │ (Redis 7)        │  │
                            │  │ • db.t3.medium   │  │ • cache.t3.micro │  │
                            │  │ • Multi-AZ       │  │ • 1 node (start) │  │
                            │  │ • SSL enforced   │  │ • Encryption in  │  │
                            │  │ • Auto backups   │  │   transit         │  │
                            │  │ • 7-day retention│  │ • DB 0: cache +  │  │
                            │  │ • Private subnet │  │   rate-limit     │  │
                            │  │   only           │  │ • DB 1: Celery   │  │
                            │  └─────────────────┘  │   broker          │  │
                            │                       └──────────────────┘  │
                            │                                              │
                            │  ┌──────────────────────────────────────────┐│
                            │  │ Amazon ECR (Container Registry)          ││
                            │  │ Amazon CloudWatch (Logs + Metrics)       ││
                            │  │ AWS Secrets Manager (Env var secrets)    ││
                            │  │ Route 53 (DNS) + ACM (TLS certificates) ││
                            │  └──────────────────────────────────────────┘│
                            └──────────────────────────────────────────────┘

  GitHub Actions ──► ECR push ──► ECS rolling deployment
```

### Data Flow

| Flow | Path |
|---|---|
| API requests | Client → ALB → ECS API → RDS + ElastiCache |
| Task dispatch | API enqueues → Redis (DB 1) → Worker picks up → RDS |
| Scheduled jobs | Beat → Redis (DB 1) → Worker → RDS |
| Health probes | ALB → `GET /health` → API checks RDS + Redis → 200/503 |

---

## 2. Environment Variables

### Required (All Services)

| Variable | Description | Example |
|---|---|---|
| `DATABASE_URL` | PostgreSQL connection string (from RDS) | `postgresql://user:pass@rds-host:5432/retailiq` |
| `CELERY_BROKER_URL` | Redis URL for Celery broker (DB 1) | `rediss://elasticache-host:6379/1` |
| `REDIS_URL` | Redis URL for cache + rate limits (DB 0) | `rediss://elasticache-host:6379/0` |
| `SECRET_KEY` | Flask session secret (32+ random chars) | `openssl rand -hex 32` |
| `JWT_PRIVATE_KEY` | RSA private key (PEM, `\n` escaped as `\\n`) | `-----BEGIN RSA PRIVATE KEY-----\\nMIIE...` |
| `JWT_PUBLIC_KEY` | RSA public key (PEM, `\n` escaped as `\\n`) | `-----BEGIN PUBLIC KEY-----\\nMIIB...` |
| `SERVICE_ROLE` | Service dispatch: `api`, `worker`, or `beat` | `api` |

### Required (API Only)

| Variable | Description | Example |
|---|---|---|
| `FLASK_ENV` | Must be `production` | `production` |
| `CORS_ORIGINS` | Comma-separated allowed origins | `https://app.retailiq.com,https://admin.retailiq.com` |

### Optional

| Variable | Default | Description |
|---|---|---|
| `CELERY_CONCURRENCY` | `4` | Worker process concurrency |
| `CELERY_QUEUES` | `celery` | Comma-separated queue names |
| `GUNICORN_MAX_WORKERS` | `4` | Max Gunicorn worker processes |
| `GUNICORN_THREADS` | `4` | Threads per Gunicorn worker |
| `GUNICORN_TIMEOUT` | `120` | Request timeout (seconds) |
| `GUNICORN_LOG_LEVEL` | `info` | Log verbosity |
| `GUNICORN_MAX_REQUESTS` | `2000` | Worker restart threshold |
| `DB_WAIT_TIMEOUT` | `60` | Seconds to wait for DB at startup |
| `FCM_CREDENTIALS_PATH` | — | Path to Firebase credentials JSON |
| `OTP_API_KEY` | — | OTP provider API key |
| `CLOUDFLARE_R2_BUCKET` | — | R2 bucket name for file storage |

### Generating JWT Keys

```bash
# Generate RSA key pair
openssl genrsa -out jwt_private.pem 2048
openssl rsa -in jwt_private.pem -pubout -out jwt_public.pem

# Encode for env var (escape newlines)
awk 'NF {sub(/\r/, ""); printf "%s\\n", $0}' jwt_private.pem
awk 'NF {sub(/\r/, ""); printf "%s\\n", $0}' jwt_public.pem
```

> [!CAUTION]
> Never commit `.pem` files or actual secret values into source control.
> Use AWS Secrets Manager or SSM Parameter Store to inject secrets into ECS task definitions.

---

## 3. Production Dockerfile

The production image is defined in [`Dockerfile.prod`](file:///d:/Files/Desktop/Integration-TyProj/RetailIQ/Dockerfile.prod).

### Key Design Decisions

| Feature | Rationale |
|---|---|
| **Multi-stage build** | Builder stage compiles C extensions (psycopg2, Prophet, scipy). Runtime stage has no compilers → smaller image, reduced attack surface |
| **`tini` as PID 1** | Proper signal forwarding to Gunicorn/Celery; reaps zombie processes |
| **Non-root `appuser`** | Container runs as UID 1000, not root. Required by many security policies |
| **`HEALTHCHECK`** | Docker-level health probe. ECS Fargate uses ALB health checks instead, but this provides defense-in-depth |
| **`PYTHONUNBUFFERED=1`** | Ensures logs appear in CloudWatch without delay |
| **`max_requests=2000`** | Periodic worker restart mitigates Prophet/sklearn memory leaks |

### Expected Image Size

~800MB–1.2GB (Prophet + sklearn + WeasyPrint runtime libs are substantial). This is acceptable for Fargate where images are cached on the host.

---

## 4. Entrypoint & Migration Safety

The entrypoint script [`scripts/entrypoint.sh`](file:///d:/Files/Desktop/Integration-TyProj/RetailIQ/scripts/entrypoint.sh) handles all three service roles.

### Migration Race Prevention

During rolling deployments, multiple API containers start simultaneously. Without coordination, parallel `alembic upgrade head` calls can cause conflicts.

**Solution**: Redis-based distributed lock.

```mermaid
sequenceDiagram
    participant C1 as API Container 1
    participant C2 as API Container 2
    participant Redis
    participant DB as PostgreSQL

    C1->>Redis: SET lock:alembic_migration NX EX 300
    Redis-->>C1: OK (lock acquired)
    C2->>Redis: SET lock:alembic_migration NX EX 300
    Redis-->>C2: FAIL (lock held)
    C2->>C2: Wait for lock release...
    C1->>DB: alembic upgrade head
    DB-->>C1: Migrations complete
    C1->>Redis: DEL lock:alembic_migration
    Redis-->>C2: Lock released
    C2->>C2: Skip migrations (already done)
    C1->>C1: exec gunicorn
    C2->>C2: exec gunicorn
```

- Lock TTL: 300s (prevents deadlock if leader crashes mid-migration)
- Only `SERVICE_ROLE=api` runs migrations
- Workers and beat skip migrations entirely

---

## 5. AWS ECS Deployment Steps

### Prerequisites

- AWS CLI v2 configured with appropriate IAM credentials
- Docker installed locally
- Domain name + Route 53 hosted zone (for HTTPS)

### Step-by-Step

#### 5.1 VPC & Networking

```bash
# Create VPC with public + private subnets across 2 AZs
aws cloudformation deploy \
  --template-file infrastructure/vpc.yml \
  --stack-name retailiq-vpc \
  --parameter-overrides \
    EnvironmentName=production \
    VpcCIDR=10.0.0.0/16

# Or use the default VPC with private subnets added.
# Critical: RDS and ElastiCache must be in PRIVATE subnets only.
```

**Security Groups**:

| SG Name | Inbound | Source |
|---|---|---|
| `sg-alb` | 443 (HTTPS) | 0.0.0.0/0 |
| `sg-api` | 5000 | `sg-alb` |
| `sg-rds` | 5432 | `sg-api`, `sg-worker`, `sg-beat` |
| `sg-redis` | 6379 | `sg-api`, `sg-worker`, `sg-beat` |

#### 5.2 Amazon RDS (PostgreSQL)

```bash
aws rds create-db-instance \
  --db-instance-identifier retailiq-prod \
  --db-instance-class db.t3.medium \
  --engine postgres \
  --engine-version 15.4 \
  --master-username retailiq_admin \
  --master-user-password "${RDS_PASSWORD}" \
  --allocated-storage 50 \
  --storage-type gp3 \
  --vpc-security-group-ids sg-rds \
  --db-subnet-group-name retailiq-private-subnets \
  --multi-az \
  --backup-retention-period 7 \
  --preferred-backup-window "03:00-04:00" \
  --storage-encrypted \
  --no-publicly-accessible \
  --deletion-protection
```

> [!IMPORTANT]
> Enable `force_ssl` in the RDS parameter group to reject unencrypted connections.

```bash
aws rds modify-db-parameter-group \
  --db-parameter-group-name retailiq-pg15 \
  --parameters "ParameterName=rds.force_ssl,ParameterValue=1,ApplyMethod=pending-reboot"
```

#### 5.3 Amazon ElastiCache (Redis)

```bash
aws elasticache create-replication-group \
  --replication-group-id retailiq-redis \
  --replication-group-description "RetailIQ Redis" \
  --engine redis \
  --engine-version 7.0 \
  --cache-node-type cache.t3.micro \
  --num-cache-clusters 1 \
  --cache-subnet-group-name retailiq-private-subnets \
  --security-group-ids sg-redis \
  --transit-encryption-enabled \
  --at-rest-encryption-enabled \
  --automatic-failover-enabled false
```

> [!NOTE]
> With `transit-encryption-enabled`, connection strings use `rediss://` (double 's').

#### 5.4 Amazon ECR

```bash
aws ecr create-repository \
  --repository-name retailiq \
  --image-scanning-configuration scanOnPush=true \
  --encryption-configuration encryptionType=AES256

# Build and push
aws ecr get-login-password | docker login --username AWS --password-stdin \
  ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com

docker build -f Dockerfile.prod -t retailiq:latest .
docker tag retailiq:latest ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/retailiq:latest
docker push ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/retailiq:latest
```

#### 5.5 ECS Cluster & Task Definitions

```bash
# Create cluster
aws ecs create-cluster --cluster-name retailiq-prod --capacity-providers FARGATE FARGATE_SPOT

# Store secrets in Secrets Manager
aws secretsmanager create-secret --name retailiq/prod/db-url \
  --secret-string "postgresql://retailiq_admin:${RDS_PASSWORD}@rds-endpoint:5432/retailiq"

aws secretsmanager create-secret --name retailiq/prod/redis-url \
  --secret-string "rediss://elasticache-endpoint:6379/0"

aws secretsmanager create-secret --name retailiq/prod/secret-key \
  --secret-string "$(openssl rand -hex 32)"

# (similarly for JWT keys, Celery broker URL, etc.)
```

**API Task Definition** (`task-def-api.json`):

```json
{
  "family": "retailiq-api",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "1024",
  "memory": "2048",
  "executionRoleArn": "arn:aws:iam::ACCOUNT:role/ecsTaskExecutionRole",
  "taskRoleArn": "arn:aws:iam::ACCOUNT:role/retailiq-task-role",
  "containerDefinitions": [
    {
      "name": "retailiq-api",
      "image": "ACCOUNT.dkr.ecr.REGION.amazonaws.com/retailiq:latest",
      "portMappings": [{ "containerPort": 5000, "protocol": "tcp" }],
      "environment": [
        { "name": "SERVICE_ROLE", "value": "api" },
        { "name": "FLASK_ENV", "value": "production" },
        { "name": "CORS_ORIGINS", "value": "https://app.retailiq.com" }
      ],
      "secrets": [
        { "name": "DATABASE_URL", "valueFrom": "arn:aws:secretsmanager:REGION:ACCOUNT:secret:retailiq/prod/db-url" },
        { "name": "REDIS_URL", "valueFrom": "arn:aws:secretsmanager:REGION:ACCOUNT:secret:retailiq/prod/redis-url" },
        { "name": "CELERY_BROKER_URL", "valueFrom": "arn:aws:secretsmanager:REGION:ACCOUNT:secret:retailiq/prod/celery-broker-url" },
        { "name": "SECRET_KEY", "valueFrom": "arn:aws:secretsmanager:REGION:ACCOUNT:secret:retailiq/prod/secret-key" },
        { "name": "JWT_PRIVATE_KEY", "valueFrom": "arn:aws:secretsmanager:REGION:ACCOUNT:secret:retailiq/prod/jwt-private" },
        { "name": "JWT_PUBLIC_KEY", "valueFrom": "arn:aws:secretsmanager:REGION:ACCOUNT:secret:retailiq/prod/jwt-public" }
      ],
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/retailiq-api",
          "awslogs-region": "REGION",
          "awslogs-stream-prefix": "api"
        }
      },
      "healthCheck": {
        "command": ["CMD-SHELL", "curl -f http://localhost:5000/health || exit 1"],
        "interval": 30,
        "timeout": 10,
        "retries": 3,
        "startPeriod": 60
      }
    }
  ]
}
```

**Worker Task Definition**: Same image, `SERVICE_ROLE=worker`, `cpu=512`, `memory=1024`, no port mappings, no ALB.

**Beat Task Definition**: Same image, `SERVICE_ROLE=beat`, `cpu=256`, `memory=512`, no port mappings, no ALB.

#### 5.6 ALB + Target Group

```bash
# Create ALB
aws elbv2 create-load-balancer \
  --name retailiq-alb \
  --subnets subnet-public-1 subnet-public-2 \
  --security-groups sg-alb \
  --scheme internet-facing \
  --type application

# Create target group
aws elbv2 create-target-group \
  --name retailiq-api-tg \
  --protocol HTTP \
  --port 5000 \
  --vpc-id vpc-xxx \
  --target-type ip \
  --health-check-path /health \
  --health-check-interval-seconds 30 \
  --healthy-threshold-count 2 \
  --unhealthy-threshold-count 3 \
  --health-check-timeout-seconds 10

# HTTPS listener (requires ACM certificate)
aws elbv2 create-listener \
  --load-balancer-arn arn:aws:elasticloadbalancing:... \
  --protocol HTTPS \
  --port 443 \
  --certificates CertificateArn=arn:aws:acm:REGION:ACCOUNT:certificate/xxx \
  --default-actions Type=forward,TargetGroupArn=arn:...retailiq-api-tg

# HTTP → HTTPS redirect
aws elbv2 create-listener \
  --load-balancer-arn arn:aws:elasticloadbalancing:... \
  --protocol HTTP \
  --port 80 \
  --default-actions Type=redirect,RedirectConfig='{Protocol=HTTPS,Port=443,StatusCode=HTTP_301}'
```

ALB idle timeout:

```bash
aws elbv2 modify-load-balancer-attributes \
  --load-balancer-arn arn:... \
  --attributes Key=idle_timeout.timeout_seconds,Value=60
```

#### 5.7 ECS Services + Autoscaling

```bash
# API Service
aws ecs create-service \
  --cluster retailiq-prod \
  --service-name retailiq-api \
  --task-definition retailiq-api \
  --desired-count 2 \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[subnet-private-1,subnet-private-2],securityGroups=[sg-api],assignPublicIp=DISABLED}" \
  --load-balancers "targetGroupArn=arn:...retailiq-api-tg,containerName=retailiq-api,containerPort=5000" \
  --deployment-configuration "maximumPercent=200,minimumHealthyPercent=100" \
  --enable-execute-command

# Worker Service
aws ecs create-service \
  --cluster retailiq-prod \
  --service-name retailiq-worker \
  --task-definition retailiq-worker \
  --desired-count 2 \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[subnet-private-1,subnet-private-2],securityGroups=[sg-worker],assignPublicIp=DISABLED}" \
  --capacity-provider-strategy "capacityProvider=FARGATE_SPOT,weight=80 capacityProvider=FARGATE,weight=20"

# Beat Service (singleton)
aws ecs create-service \
  --cluster retailiq-prod \
  --service-name retailiq-beat \
  --task-definition retailiq-beat \
  --desired-count 1 \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[subnet-private-1],securityGroups=[sg-beat],assignPublicIp=DISABLED}" \
  --deployment-configuration "maximumPercent=100,minimumHealthyPercent=0"
```

> [!IMPORTANT]
> Beat uses `maximumPercent=100,minimumHealthyPercent=0` to guarantee only 1 instance runs at a time during deploys (stop-before-start). This prevents duplicate schedule execution.

**API Autoscaling**:

```bash
# Register scalable target
aws application-autoscaling register-scalable-target \
  --service-namespace ecs \
  --resource-id service/retailiq-prod/retailiq-api \
  --scalable-dimension ecs:service:DesiredCount \
  --min-capacity 2 \
  --max-capacity 10

# CPU-based scaling policy
aws application-autoscaling put-scaling-policy \
  --service-namespace ecs \
  --resource-id service/retailiq-prod/retailiq-api \
  --scalable-dimension ecs:service:DesiredCount \
  --policy-name retailiq-api-cpu-scaling \
  --policy-type TargetTrackingScaling \
  --target-tracking-scaling-policy-configuration \
    "TargetValue=60.0,PredefinedMetricSpecification={PredefinedMetricType=ECSServiceAverageCPUUtilization},ScaleInCooldown=300,ScaleOutCooldown=60"
```

**Worker Autoscaling** (queue-depth based):

```bash
# Register scalable target for workers
aws application-autoscaling register-scalable-target \
  --service-namespace ecs \
  --resource-id service/retailiq-prod/retailiq-worker \
  --scalable-dimension ecs:service:DesiredCount \
  --min-capacity 2 \
  --max-capacity 8

# Custom metric: publish Redis queue length to CloudWatch via a Lambda
# Then create a step-scaling policy:
aws application-autoscaling put-scaling-policy \
  --service-namespace ecs \
  --resource-id service/retailiq-prod/retailiq-worker \
  --scalable-dimension ecs:service:DesiredCount \
  --policy-name retailiq-worker-queue-scaling \
  --policy-type StepScaling \
  --step-scaling-policy-configuration \
    "AdjustmentType=ChangeInCapacity,StepAdjustments=[{MetricIntervalLowerBound=0,MetricIntervalUpperBound=100,ScalingAdjustment=1},{MetricIntervalLowerBound=100,ScalingAdjustment=2}],Cooldown=120"
```

**Monitoring queue depth** (Lambda or sidecar):

```python
# Lambda function to publish Celery queue depth to CloudWatch
import redis, boto3

def handler(event, context):
    r = redis.Redis.from_url("rediss://elasticache-endpoint:6379/1")
    queue_length = r.llen("celery")  # default queue name
    cloudwatch = boto3.client("cloudwatch")
    cloudwatch.put_metric_data(
        Namespace="RetailIQ",
        MetricData=[{
            "MetricName": "CeleryQueueDepth",
            "Value": queue_length,
            "Unit": "Count"
        }]
    )
```

---

## 6. Security Hardening Checklist

### Network Layer

- [x] RDS in private subnets only (no public IP)
- [x] ElastiCache in private subnets only
- [x] ECS tasks in private subnets (NAT Gateway for outbound)
- [x] Security groups: least-privilege (only ALB → API port 5000)
- [x] VPC Flow Logs enabled
- [ ] AWS WAF on ALB (OWASP ruleset)
- [ ] AWS Shield Standard (automatic with ALB)

### Transport & Encryption

- [x] HTTPS only (ALB terminates TLS with ACM cert)
- [x] HTTP → HTTPS redirect on ALB
- [x] RDS SSL enforced (`rds.force_ssl=1`)
- [x] ElastiCache transit encryption enabled (`rediss://`)
- [x] RDS storage encryption (AES-256)
- [x] ElastiCache at-rest encryption

### Application Layer

- [x] `DEBUG=False` enforced in production
- [x] `SECRET_KEY` validated at startup (no weak defaults)
- [x] JWT keys from env vars (no auto-generation in production)
- [x] CORS restricted to explicit origins
- [x] Rate limiting (flask-limiter backed by Redis)
- [x] Non-root container user (`appuser`)
- [x] No `.env` files in container image (secrets via Secrets Manager)
- [x] Gunicorn `limit_request_line` / `limit_request_fields` set

### Secrets Management

- [x] All secrets in AWS Secrets Manager
- [x] ECS task execution role with `secretsmanager:GetSecretValue` only
- [x] Rotate DB password quarterly (RDS supports automatic rotation)
- [x] Rotate JWT keys with overlap period

### Container Security

- [x] ECR image scanning on push
- [x] Minimal base image (slim-bookworm, no compilers in runtime)
- [x] Read-only root filesystem (ECS Fargate supports this)
- [x] No `--privileged` flag
- [x] Resource limits via ECS task definition (CPU/memory caps)

---

## 7. Monitoring & Logging

### CloudWatch Logs

All three services log to stdout, which ECS Fargate forwards to CloudWatch Logs via the `awslogs` driver.

| Log Group | Service | Retention |
|---|---|---|
| `/ecs/retailiq-api` | API (Gunicorn) | 30 days |
| `/ecs/retailiq-worker` | Celery worker | 30 days |
| `/ecs/retailiq-beat` | Celery beat | 14 days |

**Structured Logging**: Gunicorn access logs are JSON-formatted (configured in `gunicorn.conf.py`). Celery task logs use `get_task_logger` with JSON payloads.

### CloudWatch Container Insights

Enable on the ECS cluster for automatic collection of:
- CPU / Memory utilization per task
- Network I/O
- Storage I/O
- Running task count

```bash
aws ecs update-cluster-settings \
  --cluster retailiq-prod \
  --settings name=containerInsights,value=enabled
```

### Key Metrics & Alarms

| Metric | Threshold | Action |
|---|---|---|
| API CPU > 80% | 5 min sustained | SNS notification |
| API HTTP 5xx > 10/min | 3 min sustained | SNS notification + PagerDuty |
| ALB healthy host count < 2 | 1 min | SNS critical alert |
| RDS CPU > 80% | 10 min sustained | Scale up instance class |
| RDS free storage < 5 GB | Immediate | SNS + auto-scale storage |
| RDS connections > 80% max | 5 min | Review connection pooling |
| ElastiCache memory > 80% | 5 min | Scale to larger node |
| Celery queue depth > 500 | 3 min | Scale workers + SNS alert |
| ECS task restart count > 5/hr | Per service | Investigate crash loop |

### Recommended Alarms Setup

```bash
# Example: ALB 5xx alarm
aws cloudwatch put-metric-alarm \
  --alarm-name retailiq-api-5xx \
  --metric-name HTTPCode_Target_5XX_Count \
  --namespace AWS/ApplicationELB \
  --statistic Sum \
  --period 60 \
  --threshold 10 \
  --comparison-operator GreaterThanThreshold \
  --evaluation-periods 3 \
  --alarm-actions arn:aws:sns:REGION:ACCOUNT:retailiq-alerts \
  --dimensions Name=LoadBalancer,Value=app/retailiq-alb/xxx
```

### Application Performance Monitoring (Optional)

For deeper visibility, integrate one of:
- **AWS X-Ray**: Add `aws-xray-sdk[flask]` to requirements, instrument Flask app
- **Datadog / New Relic**: Add agent as sidecar container in task definition

---

## 8. Common Failure Modes & Mitigation

### 8.1 Database Connection Exhaustion

**Symptoms**: `FATAL: too many connections` in logs, API returning 503.

**Root Cause**: Each Gunicorn worker opens its own connection pool. With 2 API tasks × 3 workers × pool_size(5) = 30 connections, plus workers.

**Mitigation**:
- Set `SQLALCHEMY_ENGINE_OPTIONS.pool_size=3` and `max_overflow=5`
- Use RDS `max_connections` appropriate for instance class (db.t3.medium = 150)
- Consider RDS Proxy for connection pooling at scale

### 8.2 Migration Deadlock on Deploy

**Symptoms**: API containers stuck at startup, health checks failing.

**Root Cause**: Two containers attempting `alembic upgrade head` simultaneously.

**Mitigation**: Already handled by Redis distributed lock in `entrypoint.sh`. If Redis is unavailable, the lock acquisition fails gracefully and migrations run without lock (acceptable risk — Alembic is idempotent for most operations).

### 8.3 Celery Beat Duplicate Execution

**Symptoms**: Scheduled tasks running twice (e.g., double digest emails).

**Root Cause**: More than one beat instance running during deployment.

**Mitigation**:
- Beat service uses `maximumPercent=100, minimumHealthyPercent=0` (stop-before-start)
- All scheduled tasks already use Redis distributed locks (`_RedisLock`)

### 8.4 Worker OOM Kill (Prophet/sklearn)

**Symptoms**: Workers restarted by ECS, exit code 137.

**Root Cause**: Prophet model fitting allocates large memory for MCMC sampling.

**Mitigation**:
- Worker task memory: 1024 MB minimum
- `max-tasks-per-child=1000` in Celery (periodic restart)
- Gunicorn `max_requests=2000` for API
- Monitor container memory via CloudWatch Container Insights

### 8.5 Redis Connection Lost

**Symptoms**: Rate limiting stops, Celery tasks not dispatched, health check returns 503.

**Root Cause**: ElastiCache maintenance window, network partition, or node failure.

**Mitigation**:
- ElastiCache Multi-AZ for automatic failover
- Celery `broker_connection_retry_on_startup=True`
- Flask-limiter falls back to in-memory limiter (degraded, not hard-failed)
- `_redis_client()` reconnects on each call

### 8.6 Deployment Rollback

**Symptoms**: New deployment causing errors.

**Mitigation**:
- ECS circuit breaker: automatically rolls back if tasks fail health checks
- Enable: `--deployment-configuration "deploymentCircuitBreaker={enable=true,rollback=true}"`
- CI/CD deploys with `wait-for-service-stability`

### 8.7 Alembic Migration Failure

**Symptoms**: API containers crash-looping, exit code 1 in logs.

**Root Cause**: Incompatible migration (e.g., column rename on large table).

**Mitigation**:
- Test migrations against a staging DB with production-like data
- Use `alembic upgrade head --sql` to preview SQL before deploy
- For dangerous migrations: deploy migration separately from code changes

### 8.8 Stale Cache / Rate Limit Drift

**Symptoms**: Inconsistent rate limiting across API instances.

**Root Cause**: Rate limiting uses Redis globally — this is actually correct behavior.

**Note**: No mitigation needed. Redis-backed rate limiting is consistent across instances.

### 8.9 Long-Running Forecasting Tasks

**Symptoms**: Worker appears stuck, no heartbeat.

**Root Cause**: `forecast_store` processes up to 200 SKUs per store.

**Mitigation**:
- Tasks have `max_retries=3` with `retry_backoff=True`
- Lock TTL of 1800s (30 min) prevents indefinite stalls
- Monitor with Celery queue depth metric + alarm

### 8.10 TLS Certificate Expiry

**Symptoms**: Browser shows certificate warning.

**Mitigation**: ACM certificates auto-renew. Verify with:
```bash
aws acm describe-certificate --certificate-arn arn:... --query Certificate.NotAfter
```

---

## 9. Cost Optimization

### Estimated Monthly Cost (Moderate Traffic)

| Resource | Spec | Est. Cost (USD) |
|---|---|---|
| ECS API (2 tasks, 1vCPU/2GB) | Fargate on-demand | ~$60 |
| ECS Worker (2 tasks, 0.5vCPU/1GB) | **Fargate Spot (80%)** | ~$15 |
| ECS Beat (1 task, 0.25vCPU/0.5GB) | Fargate on-demand | ~$8 |
| RDS PostgreSQL (db.t3.medium, Multi-AZ) | On-demand | ~$130 |
| ElastiCache Redis (cache.t3.micro) | On-demand | ~$13 |
| ALB | Per hour + LCU | ~$25 |
| NAT Gateway (2 AZs) | Per hour + data | ~$70 |
| ECR | Storage + transfer | ~$5 |
| CloudWatch Logs | 30-day retention | ~$10 |
| **Total** | | **~$336/mo** |

### Optimization Strategies

1. **Fargate Spot for Workers** (already configured):
   Workers are stateless and retry-safe. Spot pricing saves ~70% vs on-demand. Set capacity provider strategy to 80% Spot / 20% on-demand for availability.

2. **RDS Reserved Instance**:
   If committed for 1 year, `db.t3.medium` reserved saves ~35% (~$85/mo instead of $130).

3. **NAT Gateway → VPC Interface Endpoints**:
   Replace NAT Gateway ($70/mo) with VPC Interface Endpoints for ECR, Secrets Manager, CloudWatch (~$25/mo total). 
   
   ```bash
   aws ec2 create-vpc-endpoint --vpc-id vpc-xxx --service-name com.amazonaws.REGION.ecr.dkr --vpc-endpoint-type Interface
   aws ec2 create-vpc-endpoint --vpc-id vpc-xxx --service-name com.amazonaws.REGION.ecr.api --vpc-endpoint-type Interface
   aws ec2 create-vpc-endpoint --vpc-id vpc-xxx --service-name com.amazonaws.REGION.logs --vpc-endpoint-type Interface
   aws ec2 create-vpc-endpoint --vpc-id vpc-xxx --service-name com.amazonaws.REGION.secretsmanager --vpc-endpoint-type Interface
   ```

4. **Right-size Fargate Tasks**:
   Start with the specs above. After 2 weeks, review Container Insights CPU/memory utilization. If API tasks average < 40% CPU, downsize to 0.5 vCPU / 1 GB.

5. **ElastiCache Serverless** (alternative):
   If Redis usage is bursty, ElastiCache Serverless eliminates the fixed node cost. Pay per ECPU + data stored.

6. **Scheduled Scaling**:
   If traffic has a known pattern (e.g., retail hours 9am–9pm), schedule API scale-down to 1 task overnight.

   ```bash
   aws application-autoscaling put-scheduled-action \
     --service-namespace ecs \
     --resource-id service/retailiq-prod/retailiq-api \
     --scalable-dimension ecs:service:DesiredCount \
     --scheduled-action-name scale-down-night \
     --schedule "cron(0 21 * * ? *)" \
     --scalable-target-action MinCapacity=1,MaxCapacity=3
   ```

---

## 10. CI/CD Integration

The GitHub Actions workflow is defined in [`.github/workflows/deploy.yml`](file:///d:/Files/Desktop/Integration-TyProj/RetailIQ/.github/workflows/deploy.yml).

### Pipeline Overview

```mermaid
graph LR
    A[Push to main] --> B[Test Job]
    B --> C{Tests Pass?}
    C -->|Yes| D[Build Docker Image]
    C -->|No| E[❌ Fail]
    D --> F[Push to ECR]
    F --> G[Deploy API to ECS]
    F --> H[Deploy Worker to ECS]
    F --> I[Deploy Beat to ECS]
    G --> J[Wait for stability]
    H --> J
    I --> J
```

### Required GitHub Secrets

| Secret | Value |
|---|---|
| `AWS_ACCESS_KEY_ID` | IAM user access key (CI/CD user) |
| `AWS_SECRET_ACCESS_KEY` | IAM user secret key |
| `AWS_REGION` | e.g., `ap-south-1` |
| `AWS_ACCOUNT_ID` | 12-digit account ID |
| `ECR_REPOSITORY` | `retailiq` |
| `ECS_CLUSTER` | `retailiq-prod` |
| `ECS_API_SERVICE` | `retailiq-api` |
| `ECS_WORKER_SERVICE` | `retailiq-worker` |
| `ECS_BEAT_SERVICE` | `retailiq-beat` |
| `ECS_API_TASK_DEF` | `retailiq-api` |
| `ECS_WORKER_TASK_DEF` | `retailiq-worker` |
| `ECS_BEAT_TASK_DEF` | `retailiq-beat` |

### IAM Policy for CI/CD User

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ecr:GetAuthorizationToken",
        "ecr:BatchCheckLayerAvailability",
        "ecr:GetDownloadUrlForLayer",
        "ecr:BatchGetImage",
        "ecr:PutImage",
        "ecr:InitiateLayerUpload",
        "ecr:UploadLayerPart",
        "ecr:CompleteLayerUpload"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "ecs:DescribeTaskDefinition",
        "ecs:RegisterTaskDefinition",
        "ecs:UpdateService",
        "ecs:DescribeServices"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": "iam:PassRole",
      "Resource": [
        "arn:aws:iam::ACCOUNT:role/ecsTaskExecutionRole",
        "arn:aws:iam::ACCOUNT:role/retailiq-task-role"
      ]
    }
  ]
}
```

### Recommended CI/CD Enhancements

1. **Environment-based deploys**: Use GitHub Environments (`staging`, `production`) with approval gates for production
2. **Canary deployments**: ECS supports CodeDeploy blue/green with traffic shifting
3. **Database migrations as separate job**: For risky schema changes, run migration in a dedicated CI step before container deploy
4. **Image caching**: Use GitHub Actions cache for Docker layers to speed up builds

---

## Appendix: Quick Reference Commands

```bash
# View service status
aws ecs describe-services --cluster retailiq-prod --services retailiq-api retailiq-worker retailiq-beat

# View running tasks
aws ecs list-tasks --cluster retailiq-prod --service-name retailiq-api

# Exec into running container (debugging)
aws ecs execute-command --cluster retailiq-prod --task TASK_ID --container retailiq-api --interactive --command "/bin/bash"

# View recent logs
aws logs tail /ecs/retailiq-api --since 1h --follow

# Force new deployment (pull latest image)
aws ecs update-service --cluster retailiq-prod --service retailiq-api --force-new-deployment

# Scale manually
aws ecs update-service --cluster retailiq-prod --service retailiq-worker --desired-count 4

# Check Celery queue depth
redis-cli -h elasticache-endpoint -p 6379 --tls LLEN celery
```
