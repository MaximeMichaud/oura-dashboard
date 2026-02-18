.PHONY: up down logs status psql

up:
	docker compose up -d --build

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
