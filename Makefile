.PHONY: up up-full down logs status psql lint format format-check test test-quick audit ci pre-commit clean

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
	@docker compose exec -T postgres psql -U oura -c "SELECT endpoint, last_sync_date, record_count, updated_at FROM sync_log ORDER BY endpoint;"

psql:
	docker compose exec postgres psql -U oura

# ---------------------------------------------------------------------------
# CI / quality targets
# ---------------------------------------------------------------------------

lint:
	ruff check ingestion/ streamlit/

format:
	ruff format ingestion/ streamlit/

format-check:
	ruff format --check ingestion/ streamlit/

test:
	pytest --cov=ingestion --cov-fail-under=70

test-quick:
	pytest

audit:
	pip-audit -r ingestion/requirements.txt
	pip-audit -r streamlit/requirements.txt

ci: lint format-check test

pre-commit:
	pre-commit install

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name .pytest_cache -exec rm -rf {} +
	find . -type d -name .ruff_cache -exec rm -rf {} +
