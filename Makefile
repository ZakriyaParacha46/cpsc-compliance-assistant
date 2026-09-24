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

.PHONY: help setup hooks up web preview db down nuke logs prodlike api-check web-check web-build check fmt image image-smoke lint-workflows lint-infra ci-local act
