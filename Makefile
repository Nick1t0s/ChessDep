up:        ; docker compose up -d --build
down:      ; docker compose down
logs:      ; docker compose logs -f --tail=100
test:      ; docker compose --profile test run --rm --build api-test; docker compose --profile test rm -sf postgres-test redis-test
make-admin:; docker compose exec api python -m app.cli make-admin $(LOGIN)
.PHONY: up down logs test make-admin
