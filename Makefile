.PHONY: build init up down logs health test smoke seed review collect-help
build:
	docker compose build api web etl
init:
	docker compose run --rm api npx wrangler d1 execute oncovo-db --local --persist-to .wrangler/state --file db/schema.sql
seed:
	docker compose run --rm api npx wrangler d1 execute oncovo-db --local --persist-to .wrangler/state --file db/seed.sql
up:
	docker compose up -d api web
logs:
	docker compose logs -f --tail=100 api web
down:
	docker compose down
health:
	python scripts/smoke_local.py
smoke:
	python scripts/smoke_local.py
test:
	docker compose run --rm etl -m unittest discover -s tests -v
review:
	docker compose run --rm etl etl/preparar_publicacao.py --help
collect-help:
	docker compose run --rm collector etl/instagram_collect.py --help
