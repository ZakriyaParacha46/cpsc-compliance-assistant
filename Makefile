# One entry point for local work AND CI: the pipeline calls these same targets.
.DEFAULT_GOAL := help
SHELL := /bin/bash
IMAGE ?= cpsc-rag-api:local
COMPOSE := docker compose

help: ## List targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-16s\033[0m %s\n",$$1,$$2}'

# ---------- setup ----------
setup: ## First-time setup: .env, python + node deps, git hook
	@command -v uv >/dev/null || { echo "install uv: brew install uv"; exit 1; }
	@command -v docker >/dev/null || echo "!! docker missing: brew install --cask orbstack (or Docker Desktop)"
	@test -f .env || cp .env.example .env
	cd api && uv sync
	cd web && npm ci
	$(MAKE) hooks

hooks: ## Install pre-push hook that runs `make check`
	@ln -sf ../../scripts/pre-push .git/hooks/pre-push && chmod +x scripts/pre-push
	@echo "pre-push hook installed"

# ---------- run locally ----------
up: ## Start db + api (hot reload) on :8000; run `make web` for the UI on :5173
	$(COMPOSE) up -d --build db api
	@echo "API: http://localhost:8000/api/health   docs: http://localhost:8000/api/docs"

web: ## Vite dev server on :5173 (proxies /api to :8000)
	cd web && npm run dev

tunnel: ## Forward the server's API to this Mac's :8000 (keep it open): make tunnel HOST=<server-ip>
	@test -n "$(HOST)" || { echo "usage: make tunnel HOST=<server public IP>"; exit 1; }
	ssh -i ~/.ssh/cpsc-rag -N -L 8000:127.0.0.1:8000 ec2-user@$(HOST)

preview: ## UI with sample data only, no backend or AWS, on :5173
	cd web && npm run dev:mock

db: ## Start only Postgres (for running the api with `uv run` outside Docker)
	$(COMPOSE) up -d db

down: ## Stop everything (keeps data)
	$(COMPOSE) --profile prodlike down

nuke: ## Stop everything and delete the local database volume
	$(COMPOSE) --profile prodlike down -v

logs: ## Tail api logs
	$(COMPOSE) logs -f api

prodlike: web-build ## Prod image + built frontend behind Caddy on :8080 (mirrors CloudFront -> EC2)
	$(COMPOSE) -f docker-compose.yml -f deploy/compose.prodlike.yml --profile prodlike up -d --build
	@sleep 3 && curl -fsS http://localhost:8080/api/health && echo && echo "open http://localhost:8080"

# ---------- production (on the server) ----------
# After scripts/go-prod.sh, .env sets COMPOSE_FILE=deploy/compose.prod.yml, so every
# `docker compose` target below (logs, ingest, eval, reset-limits) uses the prod stack.
go-prod: ## One-time: switch the server from the dev stack to production
	scripts/go-prod.sh

prod-up: ## Rebuild and restart the production stack after a git pull
	docker compose -f deploy/compose.prod.yml up -d --build --remove-orphans
	@sleep 5; curl -fsS http://127.0.0.1:8000/api/health && echo

ps: ## Show running containers
	$(COMPOSE) ps

# ---------- data (runs in the api container, next to the database) ----------
# data/ is created first as you, so Docker doesn't create it as root.
RUN_API := mkdir -p data && $(COMPOSE) run --rm api

ingest-download: ## Download the 16 CFR parts from eCFR into data/raw (+ S3)
	$(RUN_API) python -m ingest download

ingest-dry-run: ## Parse and chunk only; nothing embedded or stored
	$(RUN_API) python -m ingest load --dry-run

ingest-load: ## Parse, chunk, embed with Titan, store in Postgres
	$(RUN_API) python -m ingest load

ingest-guidance: ## Chunk, embed and store the CPSC guidance pages in data/cpsc-html
	$(RUN_API) python -m ingest guidance

ingest-statutes: ## Download, chunk, embed and store the CPSA and FHSA
	$(RUN_API) python -m ingest statutes

ingest-stats: ## Show what's stored in the database
	$(RUN_API) python -m ingest stats

show: ## Show the chunks of one section: make show S=1263.3 (or S="15 U.S.C. 2063")
	$(RUN_API) python -m ingest show "$(S)"

search: ## Vector search check: make search Q="coin battery warning label"
	$(RUN_API) python -m ingest search "$(Q)"

ask: ## Ask the running API and watch the stream: make ask Q="who issues the GCC?"
	@curl -sN -X POST http://127.0.0.1:8000/api/ask -H 'Content-Type: application/json' \
	  -d "$$(python3 -c 'import json,sys; print(json.dumps({"question": sys.argv[1]}))' "$(Q)")"; echo

reset-limits: ## Clear all usage counters (visitor, IP, burst, global) for testing
	$(COMPOSE) exec db psql -U cpsc -d cpsc -c "DELETE FROM usage_counters;"

eval: ## Retrieval eval: 20 golden questions, vector vs BM25 vs hybrid
	$(RUN_API) python -m eval.retrieval

# ---------- checks (CI runs exactly these) ----------
api-check: ## Lint, format-check and test the API
	cd api && uv sync --frozen
	cd api && uv run ruff check .
	cd api && uv run ruff format --check .
	cd api && uv run pytest -q

web-check: ## Typecheck and build the frontend
	cd web && npm ci --no-audit --no-fund
	cd web && npm run build

web-build:
	cd web && npm run build

check: api-check web-check ## Everything the pre-push hook and CI's test jobs run

fmt: ## Auto-fix lint + format
	cd api && uv run ruff check --fix . && uv run ruff format .

image: ## Build the API image (arm64 on Apple Silicon = same as t4g)
	docker build -t $(IMAGE) api

image-smoke: ## Start the image with no DB and check it serves /api/health
	@docker rm -f cpsc-smoke >/dev/null 2>&1 || true
	docker run -d --name cpsc-smoke -p 18000:8000 $(IMAGE)
	@for i in $$(seq 1 20); do \
	  code=$$(curl -s -o /dev/null -w '%{http_code}' http://localhost:18000/api/health || true); \
	  if [[ "$$code" == "200" || "$$code" == "503" ]]; then echo "image serves /api/health ($$code)"; docker rm -f cpsc-smoke >/dev/null; exit 0; fi; \
	  sleep 1; done; \
	docker logs cpsc-smoke; docker rm -f cpsc-smoke >/dev/null; exit 1

lint-workflows: ## Validate GitHub Actions YAML (actionlint, via Docker)
	docker run --rm -v "$$PWD:/repo" -w /repo rhysd/actionlint:latest -color

lint-infra: ## Validate the CloudFormation template (cfn-lint)
	uvx cfn-lint infra/bootstrap.yml

ci-local: check image image-smoke lint-workflows lint-infra ## Full CI dry run locally, no AWS needed
	@echo "✔ ci-local passed: safe to push"

act: ## Run the pipeline's check jobs in containers via `act` (brew install act)
	act push -j api-check -j web-check --container-architecture linux/arm64

.PHONY: help setup hooks up web tunnel preview go-prod prod-up ps ingest-download ingest-dry-run ingest-load ingest-guidance ingest-statutes ingest-stats ask reset-limits eval show search db down nuke logs prodlike api-check web-check web-build check fmt image image-smoke lint-workflows lint-infra ci-local act
