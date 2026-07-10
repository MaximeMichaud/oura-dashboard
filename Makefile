.PHONY: up up-full down logs status psql migrate oauth-setup lint format format-check test test-quick audit ci pre-commit clean

up:
	docker compose up -d --build

up-full:
	docker compose --profile ingestion up -d --build

down:
	docker compose down

logs:
	docker compose logs -f

status:
	@docker compose ps
	@echo ""
	@echo "--- Sync Log ---"
	@docker compose exec -T postgres sh -c 'psql -U "$$POSTGRES_USER" -d "$$POSTGRES_DB" -c "SELECT endpoint, last_sync_date, record_count, last_success_at, consecutive_failures FROM sync_log ORDER BY endpoint;"'

psql:
	docker compose exec postgres sh -c 'psql -U "$$POSTGRES_USER" -d "$$POSTGRES_DB"'

migrate:
	docker compose run --rm migrate

# One-shot local OAuth setup. The callback is published on 127.0.0.1:8765 only.
# To use a different port, set OURA_REDIRECT_URI (e.g. http://localhost:9000/callback)
# AND update the -p mapping below to match, otherwise Docker won't publish that port.
oauth-setup:
	docker compose build ingestion
	docker compose run --rm --no-deps --user "$$(id -u):$$(id -g)" -p 127.0.0.1:8765:8765 -v "$(CURDIR):/workspace" -w /workspace -e PYTHONPATH=/workspace/ingestion ingestion python -m oura_ingest.cli --oauth-setup --oauth-host 0.0.0.0

# ---------------------------------------------------------------------------
# CI / quality targets
# ---------------------------------------------------------------------------

lint:
	ruff check ingestion/ streamlit/ tests/

format:
	ruff format ingestion/ streamlit/ tests/

format-check:
	ruff format --check ingestion/ streamlit/ tests/

test:
	pytest --cov=ingestion --cov-fail-under=70

test-quick:
	pytest

audit:
	pip-audit -r ingestion/requirements.txt
	pip-audit -r streamlit/requirements.txt
	npm audit --prefix scripts --audit-level=high

ci: lint format-check test

pre-commit:
	pre-commit install

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name .pytest_cache -exec rm -rf {} +
	find . -type d -name .ruff_cache -exec rm -rf {} +
