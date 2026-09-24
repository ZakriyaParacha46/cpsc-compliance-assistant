#!/usr/bin/env bash
# Build the React site and publish it to S3 + CloudFront. Runs ON the server (the instance
# role has the permissions; no AWS keys anywhere). GitHub Actions will call the same script.
# Needs WEB_BUCKET and CF_DISTRIBUTION_ID in .env (outputs of the cpsc-rag-public stack).
set -euo pipefail
cd "$(dirname "$0")/.."

get() { grep -E "^$1=" .env | tail -1 | cut -d= -f2- || true; }
BUCKET="$(get WEB_BUCKET)"
DIST="$(get CF_DISTRIBUTION_ID)"
[ -n "$BUCKET" ] && [ -n "$DIST" ] || {
  echo "!! Add WEB_BUCKET and CF_DISTRIBUTION_ID to .env (cpsc-rag-public stack outputs)"
  exit 1
}

echo "==> Building the site in a temporary Node container"
docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD/web:/web" -w /web \
  node:22-slim sh -c "npm ci --no-audit --no-fund --loglevel=error && npm run build"

echo "==> Uploading to s3://$BUCKET"
# Hashed asset files never change, so browsers may cache them forever; index.html never.
aws s3 sync web/dist "s3://$BUCKET" --delete --exclude index.html \
  --cache-control "public,max-age=31536000,immutable" --only-show-errors
aws s3 cp web/dist/index.html "s3://$BUCKET/index.html" \
  --cache-control "no-cache" --only-show-errors

echo "==> Refreshing CloudFront"
aws cloudfront create-invalidation --distribution-id "$DIST" --paths "/index.html" "/" \
  --query Invalidation.Id --output text

echo "==> Published. Give CloudFront a minute to pick it up."
