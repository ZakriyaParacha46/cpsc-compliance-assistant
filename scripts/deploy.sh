#!/usr/bin/env bash
# Deploy the checked-out commit. Runs ON the server as ec2-user, called by GitHub Actions via
# SSM Run Command right after `git reset --hard <tested sha>` (or run it by hand after a pull).
set -euo pipefail
cd "$(dirname "$0")/.."

PREV="$(cat .deployed-sha 2>/dev/null || echo none)"
NOW="$(git rev-parse HEAD)"
echo "==> Deploying ${NOW:0:7}: $(git log -1 --format=%s)"
echo "    previously deployed: ${PREV:0:7}"

echo "==> API: rebuild and restart"
docker compose -f deploy/compose.prod.yml up -d --build --remove-orphans

echo "==> Waiting for health"
ok=""
for _ in $(seq 1 40); do
  if curl -fsS http://127.0.0.1:8000/api/health; then ok=1; echo; break; fi
  sleep 3
done
if [ -z "$ok" ]; then
  echo "!! API unhealthy after deploy. Logs:" >&2
  docker compose -f deploy/compose.prod.yml logs --tail 80 api >&2
  exit 1
fi

# The site only needs rebuilding when web/ changed (saves ~1-2 minutes per deploy).
if [ "$PREV" = none ] || ! git diff --quiet "$PREV" "$NOW" -- web/ 2>/dev/null; then
  echo "==> Web changed: rebuilding and publishing the site"
  scripts/deploy-web.sh
else
  echo "==> Web unchanged: skipping site publish"
fi

echo "$NOW" > .deployed-sha
docker image prune -f >/dev/null
docker builder prune -f --filter until=168h >/dev/null 2>&1 || true
echo "==> Deployed ${NOW:0:7}"
