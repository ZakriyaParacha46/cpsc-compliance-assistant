#!/usr/bin/env bash
# One-time switch of the server from the dev stack to the production stack.
# Run on the server from the repo:  cd /opt/cpsc-rag && scripts/go-prod.sh
# Safe to re-run: it keeps an existing strong password and the database volume.
set -euo pipefail
cd "$(dirname "$0")/.."

[ -f .env ] || { echo "!! .env not found in $(pwd)"; exit 1; }
get() { grep -E "^$1=" .env | tail -1 | cut -d= -f2- || true; }

BUCKET="$(get DATA_BUCKET)"
PW="$(get POSTGRES_PASSWORD)"
if [[ ! "$PW" =~ ^[a-f0-9]{48}$ ]]; then
  PW="$(openssl rand -hex 24)" # 48 hex chars: strong, and safe inside a URL
  echo "==> Generated a new database password"
fi

echo "==> Setting the password on the existing database (data is kept)"
docker compose -f docker-compose.yml up -d db >/dev/null
for _ in $(seq 1 30); do
  docker compose -f docker-compose.yml exec -T db pg_isready -U cpsc >/dev/null 2>&1 && break
  sleep 1
done
docker compose -f docker-compose.yml exec -T db \
  psql -U cpsc -d cpsc -q -c "ALTER USER cpsc PASSWORD '$PW';"

echo "==> Writing production .env (old one saved as .env.dev.bak)"
cp .env .env.dev.bak
chmod 600 .env.dev.bak
umask 077
cat > .env <<EOF
# Production settings, written by scripts/go-prod.sh. Readable by this user only.
COMPOSE_FILE=deploy/compose.prod.yml
ENV=prod
LLM_MODE=bedrock
AWS_REGION=us-east-1
DATA_BUCKET=$BUCKET
POSTGRES_USER=cpsc
POSTGRES_DB=cpsc
POSTGRES_PASSWORD=$PW
DATABASE_URL=postgresql://cpsc:$PW@db:5432/cpsc
# Proxies that append to X-Forwarded-For: 1 = Caddy only. Becomes 2 behind CloudFront.
TRUSTED_PROXY_HOPS=1
EOF

echo "==> Stopping the dev API"
docker compose -f docker-compose.yml rm -sf api >/dev/null 2>&1 || true

echo "==> Building and starting the production stack (first build takes a few minutes)"
docker compose -f deploy/compose.prod.yml up -d --build --remove-orphans

echo "==> Waiting for health"
for i in $(seq 1 40); do
  if out="$(curl -fsS http://127.0.0.1:8000/api/health 2>/dev/null)"; then
    echo "$out"
    echo "==> Production stack is up after ${i} tries"
    docker compose -f deploy/compose.prod.yml ps
    exit 0
  fi
  sleep 3
done
echo "!! API did not become healthy. Logs:" >&2
docker compose -f deploy/compose.prod.yml logs --tail 60 api >&2
exit 1
