.PHONY: up down logs login test format

up:
	docker compose up --build -d

down:
	docker compose down

logs:
	docker compose logs -f --tail=200 autoapply

login:
	./scripts/manual_login_local.sh

test:
	PYTHONPATH=. pytest -q
