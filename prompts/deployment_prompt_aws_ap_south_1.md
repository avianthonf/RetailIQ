# RetailIQ Deployment Prompt — AWS ap-south-1

_Last updated: 2026-03-12_

## Objective
Stand up the complete RetailIQ production stack in **ap-south-1** using AWS ECS Fargate with an internet-facing ALB, Secrets Manager-backed configuration, and GitHub Actions CD. Follow this prompt to:

1. Provision networking + compute (ECS cluster, services, task definitions).
2. Create/load all secrets into AWS Secrets Manager.
3. Configure the Application Load Balancer and capture its DNS endpoint.
4. Enable an easy log-viewing workflow through CloudWatch Logs + AWS CLI.
5. Wire GitHub Actions deploy workflow with the required repository secrets.

## 0. Prerequisites
- AWS CLI v2 installed and authenticated as an IAM principal with permissions for ECS, ELBv2, IAM, Secrets Manager, CloudWatch, ECR, and Route 53.
- Docker engine + Buildx on the build machine.
- `aws` default region or `AWS_REGION` env set to `ap-south-1`.
- Domain hosted in Route 53 (optional, required for vanity hostname + ACM TLS).
- GitHub repository admin access to manage Actions secrets.

## 1. Core Infrastructure Summary
| Layer | Resource | Notes |
| --- | --- | --- |
| ECS Cluster | `retailiq-prod-cluster` | Capacity providers: `FARGATE`, `FARGATE_SPOT`. Container Insights enabled. |
| Services | `retailiq-api` (ALB), `retailiq-worker`, `retailiq-beat` | Service roles set via `SERVICE_ROLE` env.
| Task Definitions | `aws/task-definitions/api.json`, `worker.json`, `beat.json` | Use `retailiq-api` container name for ALB mapping (port 5000). |
| ALB | `retailiq-prod-alb-ap` | Internet-facing, HTTPS 443 + HTTP→HTTPS redirect. Target group `retailiq-api-tg`. |
| Datastores | Amazon RDS PostgreSQL 15 (`db.t3.medium`), ElastiCache Redis 7 (`cache.t3.micro`) | Both in private subnets, SSL/TLS enforced. |
| Registry | ECR repo `retailiq-api` under acct `610572473486` | Image tags: commit SHA + `latest`. |
| Logging | CloudWatch log groups `/ecs/retailiq-api`, `/ecs/retailiq-worker`, `/ecs/retailiq-beat` | 30/30/14 day retention.

## 2. Secrets Manager — required keys
Create each secret once, then reference it in the task definitions. Use actual production values (examples below are placeholders).

| Secret name | Purpose | Example command |
| --- | --- | --- |
| `retailiq/prod/db-url` | PostgreSQL URL | `aws secretsmanager create-secret --name retailiq/prod/db-url --secret-string "postgresql://retailiq_admin:${RDS_PASSWORD}@retailiq-prod.cle2abcxyz.ap-south-1.rds.amazonaws.com:5432/retailiq"`
| `retailiq/prod/redis-url` | Redis cache (DB 0) | `aws secretsmanager create-secret --name retailiq/prod/redis-url --secret-string "rediss://retailiq-redis.xxxxxx.ng.0001.apu1.cache.amazonaws.com:6379/0?ssl_cert_reqs=none"`
| `retailiq/prod/celery-broker-url` | Redis broker (DB 1) | `aws secretsmanager create-secret --name retailiq/prod/celery-broker-url --secret-string "rediss://retailiq-redis.xxxxxx.ng.0001.apu1.cache.amazonaws.com:6379/1?ssl_cert_reqs=none"`
| `retailiq/prod/secret-key` | Flask `SECRET_KEY` | `aws secretsmanager create-secret --name retailiq/prod/secret-key --secret-string "$(openssl rand -hex 32)"`
| `retailiq/prod/jwt-private` | JWT signing key | `aws secretsmanager create-secret --name retailiq/prod/jwt-private --secret-string "$(awk 'NF {sub(/\r/, ""); printf "%s\\n", $0}' jwt_private.pem)"`
| `retailiq/prod/jwt-public` | JWT verification key | `aws secretsmanager create-secret --name retailiq/prod/jwt-public --secret-string "$(awk 'NF {sub(/\r/, ""); printf "%s\\n", $0}' jwt_public.pem)"`
| `retailiq/prod/mail-username` | Gmail/SMTP username | `aws secretsmanager create-secret --name retailiq/prod/mail-username --secret-string "alerts@retailiq.com"`
| `retailiq/prod/mail-password` | Gmail App Password | `aws secretsmanager create-secret --name retailiq/prod/mail-password --secret-string "abcd efgh ijkl mnop"`
| `retailiq/prod/whatsapp-access-token` | Meta Cloud API token | `aws secretsmanager create-secret --name retailiq/prod/whatsapp-access-token --secret-string "EAAG..."`
| `retailiq/prod/whatsapp-verify-token` | Meta webhook verify token | `aws secretsmanager create-secret --name retailiq/prod/whatsapp-verify-token --secret-string "retailiq-prod-verify"`

> For updates, run `aws secretsmanager put-secret-value --secret-id <name> --secret-string <value>`.

## 3. Build & Push image to ECR
```bash
aws ecr get-login-password --region ap-south-1 | docker login --username AWS --password-stdin 610572473486.dkr.ecr.ap-south-1.amazonaws.com

docker build -f Dockerfile.prod -t retailiq-api:latest .
docker tag retailiq-api:latest 610572473486.dkr.ecr.ap-south-1.amazonaws.com/retailiq-api:latest
docker push 610572473486.dkr.ecr.ap-south-1.amazonaws.com/retailiq-api:latest
```

## 4. ECS cluster + task definition bootstrap
1. **Cluster**
   ```bash
   aws ecs create-cluster --cluster-name retailiq-prod-cluster --capacity-providers FARGATE FARGATE_SPOT
   aws ecs update-cluster-settings --cluster retailiq-prod-cluster --settings name=containerInsights,value=enabled
   ```
2. **Register task definitions**
   ```bash
   aws ecs register-task-definition --cli-input-json file://aws/task-definitions/api.json
   aws ecs register-task-definition --cli-input-json file://aws/task-definitions/worker.json
   aws ecs register-task-definition --cli-input-json file://aws/task-definitions/beat.json
   ```
   Ensure each container definition references the Secrets Manager ARNs above and leaves the container name as `retailiq-api` for the API service.

## 5. ALB, target group, and DNS capture
```bash
# Create internet-facing ALB
aws elbv2 create-load-balancer \
  --name retailiq-prod-alb-ap \
  --type application \
  --scheme internet-facing \
  --subnets subnet-public-a subnet-public-b \
  --security-groups sg-alb

# Target group for port 5000
aws elbv2 create-target-group \
  --name retailiq-api-tg \
  --protocol HTTP \
  --port 5000 \
  --vpc-id vpc-xxxx \
  --target-type ip \
  --health-check-path /health

# HTTPS listener (replace ACM ARN)
aws elbv2 create-listener \
  --load-balancer-arn arn:aws:elasticloadbalancing:ap-south-1:610572473486:loadbalancer/app/retailiq-prod-alb-ap/... \
  --protocol HTTPS \
  --port 443 \
  --certificates CertificateArn=arn:aws:acm:ap-south-1:610572473486:certificate/xxxxxxxx \
  --default-actions Type=forward,TargetGroupArn=arn:aws:elasticloadbalancing:ap-south-1:610572473486:targetgroup/retailiq-api-tg/xxxxxxxx

# HTTP→HTTPS redirect listener
aws elbv2 create-listener \
  --load-balancer-arn arn:aws:elasticloadbalancing:ap-south-1:610572473486:loadbalancer/app/retailiq-prod-alb-ap/... \
  --protocol HTTP \
  --port 80 \
  --default-actions Type=redirect,RedirectConfig='{Protocol=HTTPS,Port=443,StatusCode=HTTP_301}'
```

**Fetch ALB DNS name** (wire to Route 53 / CNAME):
```bash
aws elbv2 describe-load-balancers --names retailiq-prod-alb-ap --query 'LoadBalancers[0].DNSName' --output text
```

## 6. ECS services (api, worker, beat)
```bash
aws ecs create-service \
  --cluster retailiq-prod-cluster \
  --service-name retailiq-api \
  --task-definition retailiq-api \
  --desired-count 2 \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[subnet-private-a,subnet-private-b],securityGroups=[sg-api],assignPublicIp=DISABLED}" \
  --load-balancers "targetGroupArn=arn:aws:elasticloadbalancing:ap-south-1:610572473486:targetgroup/retailiq-api-tg/xxxxxxxx,containerName=retailiq-api,containerPort=5000" \
  --deployment-configuration "maximumPercent=200,minimumHealthyPercent=100" \
  --deployment-circuit-breaker "{\"enable\":true,\"rollback\":true}"

aws ecs create-service \
  --cluster retailiq-prod-cluster \
  --service-name retailiq-worker \
  --task-definition retailiq-worker \
  --desired-count 2 \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[subnet-private-a,subnet-private-b],securityGroups=[sg-worker],assignPublicIp=DISABLED}" \
  --capacity-provider-strategy "capacityProvider=FARGATE_SPOT,weight=80" "capacityProvider=FARGATE,weight=20"

aws ecs create-service \
  --cluster retailiq-prod-cluster \
  --service-name retailiq-beat \
  --task-definition retailiq-beat \
  --desired-count 1 \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[subnet-private-a],securityGroups=[sg-beat],assignPublicIp=DISABLED}" \
  --deployment-configuration "maximumPercent=100,minimumHealthyPercent=0"
```

## 7. GitHub Actions CD wiring
1. Navigate to **GitHub → Settings → Secrets and variables → Actions**.
2. Add repository secrets:
   - `AWS_ACCESS_KEY_ID` — IAM user or role for deployments.
   - `AWS_SECRET_ACCESS_KEY` — matching secret.
   - `SLACK_WEBHOOK_URL` — optional, for deploy notifications.
3. Verify `.github/workflows/deploy.yml` already targets `ap-south-1`, cluster `retailiq-prod-cluster`, repository `retailiq-api`. No edits needed unless names differ.
4. Ensure IAM credentials have permissions for ECR, ECS, CloudWatch Logs, and ELBv2 (attach a scoped policy or reuse `deployer-policy.json`).
5. Trigger the workflow via push to `main` or manual **Run workflow**; confirm steps `test → build → deploy(api/worker) → verify` succeed.

## 8. Observability & log access (CLI quick paths)
- **Tail API logs (live):**
  ```bash
  aws logs tail /ecs/retailiq-api --follow --since 1h
  ```
- **Tail worker logs:**
  ```bash
  aws logs tail /ecs/retailiq-worker --follow --since 1h
  ```
- **Beat heartbeat check:**
  ```bash
  aws logs tail /ecs/retailiq-beat --since 30m
  ```
- **Describe unhealthy ALB targets:**
  ```bash
  aws elbv2 describe-target-health --target-group-arn arn:aws:elasticloadbalancing:ap-south-1:610572473486:targetgroup/retailiq-api-tg/xxxxxxxx
  ```
- **ECS task exec (ad-hoc debugging):**
  ```bash
  aws ecs execute-command \
    --cluster retailiq-prod-cluster \
    --task <task-arn> \
    --container retailiq-api \
    --interactive --command "/bin/sh"
  ```

## 9. Post-deploy validation
1. `curl https://<alb-dns-or-domain>/api/v1/health` → expect `{"status":"ok"}`.
2. Check ALB target health count ≥ desired tasks.
3. Verify Celery worker queue depth in CloudWatch (`RetailIQ/CeleryQueueDepth`).
4. Run smoke tests (login, inventory list, supplier fetch) via Postman or CLI hitting the ALB DNS.
5. Update runbook with DNS + certificate ARNs for future operators.

## 10. Rollback & cleanup tips
- To redeploy quickly, re-run the GitHub Actions workflow after pushing a fix.
- For infra rebuilds, delete ECS services before deleting target groups/cluster to avoid dependency errors (documented in README).
- Keep copies of Secrets Manager ARNs in your infra tracker so new task definition revisions remain in sync.
