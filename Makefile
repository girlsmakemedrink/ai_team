.DEFAULT_GOAL := help
.PHONY: help install dev install-hooks up down logs ps restart \
        test test-unit test-integration test-smoke test-real-llm \
        lint typecheck format format-check fix sec \
        migrate alembic-rev \
        smoke-llm demo demo-iter-0 demo-iter-1 demo-iter-2 demo-iter-3 demo-iter-4 demo-iter-5 demo-iter-6 demo-iter-7 demo-iter-8 demo-iter-9 \
        clean

help: ## Show available targets
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install: ## Install all dependencies via uv
	uv sync --all-extras

dev: install install-hooks ## Set up dev environment (install + pre-commit + pre-push + .env)
	uv run pre-commit install
	uv run pre-commit install --hook-type commit-msg
	@if [ ! -f .env ]; then cp .env.example .env && echo "Created .env from template — fill in secrets"; fi

install-hooks: ## Symlink .githooks/pre-push into this checkout's hooks dir
	@# Hooks dirs are shared across worktrees from the same repo (git's
	@# default), so the symlink target gets baked in as an absolute path
	@# of WHICHEVER checkout ran this. If you swap checkouts (or delete a
	@# worktree the symlink points at), re-run `make install-hooks` from
	@# the new one. We accept this re-install step rather than touch
	@# `git config core.hooksPath`.
	@hooksdir="$$(git rev-parse --git-path hooks)"; \
	 mkdir -p "$$hooksdir"; \
	 ln -sf "$$(pwd)/.githooks/pre-push" "$$hooksdir/pre-push"; \
	 echo "Installed pre-push hook → $$hooksdir/pre-push"

up: ## Start infra: postgres, redis, prometheus, grafana
	docker compose -f infra/docker-compose.yml up -d
	@echo ""
	@echo "Services starting. Run 'make ps' to check health."

down: ## Stop infra
	docker compose -f infra/docker-compose.yml down

logs: ## Tail infra logs (Ctrl+C to exit)
	docker compose -f infra/docker-compose.yml logs -f --tail=100

ps: ## Show infra status
	docker compose -f infra/docker-compose.yml ps

restart: down up ## Restart infra

# === Tests ===

test: ## Run all tests (mocked LLM only)
	uv run pytest

test-unit: ## Unit tests only
	uv run pytest tests/unit -v

test-integration: ## Integration tests (requires `make up`)
	uv run pytest tests/integration -v -m "integration and not real_llm"

test-smoke: ## Smoke suite (<=5min)
	uv run pytest -m smoke

test-real-llm: ## E2E with real `claude -p` — uses subscription quota
	uv run pytest -m real_llm --real-llm

# === Quality ===

lint: ## Ruff lint
	uv run ruff check .

typecheck: ## Mypy strict
	uv run mypy .

format: ## Ruff format
	uv run ruff format .

format-check: ## Ruff format in check-mode (used by pre-push hook)
	uv run ruff format --check .

fix: ## Auto-fix lint + format
	uv run ruff check --fix .
	uv run ruff format .

sec: ## Bandit security scan (gates on high-severity per ADR-005)
	uv run bandit -c pyproject.toml -r apps agents core tools --severity-level high

# === Migrations ===

migrate: ## alembic upgrade head
	uv run alembic upgrade head

alembic-rev: ## New alembic revision (usage: make alembic-rev MSG="description")
	uv run alembic revision --autogenerate -m "$(MSG)"

# === Smoke / demo ===

smoke-llm: ## Validate `claude -p` substrate (ADR-008)
	uv run python scripts/smoke_claude_p.py

demo: demo-iter-9 ## Alias for the current iteration's demo

demo-iter-9: ## Run iter-9 e2e (pre-flight MCP health-gate → BLOCKED on unhealthy)
	bash scripts/demo_iter_9.sh

demo-iter-8: ## Run iter-8 e2e — regression baseline
	bash scripts/demo_iter_8.sh

demo-iter-7: ## Run iter-7 e2e — regression baseline
	bash scripts/demo_iter_7.sh

demo-iter-6: ## Run iter-6 e2e — regression baseline
	bash scripts/demo_iter_6.sh

demo-iter-5: ## Run iter-5 e2e — regression baseline
	bash scripts/demo_iter_5.sh

demo-iter-4: ## Run iter-4 e2e — regression baseline
	bash scripts/demo_iter_4.sh

demo-iter-3: ## Run iter-3 e2e — regression baseline (uv-run MCP)
	bash scripts/demo_iter_3.sh

demo-iter-2: ## Run iter-2 end-to-end (TL → Architect → Backend → QA) — regression baseline
	bash scripts/demo_iter_2.sh

demo-iter-1: ## Run the Iteration 1 demo (TL + PM live)
	bash scripts/demo_iter_1.sh

demo-iter-0: ## Run the Iteration 0 demo (foundation only)
	bash scripts/demo_iter_0.sh

# === Cleanup ===

clean: ## Remove caches and build artifacts
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage coverage.xml dist build *.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
