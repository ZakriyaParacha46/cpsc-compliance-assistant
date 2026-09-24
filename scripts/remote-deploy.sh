#!/usr/bin/env bash
# Runs ON the EC2 instance (invoked by the pipeline through SSM Run Command).
# Usage: remote-deploy.sh <api-image-uri> <artifact-bucket> <git-sha>
set -euo pipefail

IMAGE="$1"
BUCKET="$2"
SHA="$3"
REGION="$(cloud-init query region 2>/dev/null || echo us-east-1)"
APP_DIR=/opt/cpsc-rag

mkdir -p "$APP_DIR"
cd "$APP_DIR"

echo "==> Fetching deploy bundle for $SHA"
aws s3 cp "s3://$BUCKET/deploy/$SHA/" . --recursive --region "$REGION"

echo "==> Writing .env"
DB_PASSWORD="$(aws ssm get-parameter --region "$REGION" --name /cpsc-rag/db-password \
  --with-decryption --query Parameter.Value --output text)"
umask 077
cat > .env <<EOF
ENV=prod
API_IMAGE=$IMAGE
GIT_SHA=$SHA
AWS_REGION=$REGION
LLM_MODE=bedrock
POSTGRES_USER=cpsc
POSTGRES_DB=cpsc
POSTGRES_PASSWORD=$DB_PASSWORD
DATABASE_URL=postgresql://cpsc:$DB_PASSWORD@db:5432/cpsc
EOF

echo "==> Pulling $IMAGE"
REGISTRY="${IMAGE%%/*}"
aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "$REGISTRY"
docker compose -f compose.prod.yml pull
docker compose -f compose.prod.yml up -d --remove-orphans

echo "==> Waiting for health"
for i in $(seq 1 30); do
  if curl -fsS http://localhost/api/health; then
    echo
    echo "==> Healthy after ${i} tries"
    docker image prune -f >/dev/null
    exit 0
  fi
  sleep 2
done

echo "!! API did not become healthy" >&2
docker compose -f compose.prod.yml logs --tail 80 api >&2
exit 1
