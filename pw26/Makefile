# Python do sistema (só para criar o .venv)
PYTHON_HOST ?= python3

VENV := .venv
PY := $(VENV)/bin/python
PIP := $(VENV)/bin/pip
MANAGE := $(PY) manage.py

.PHONY: venv install migrate run makemigrations superuser shell collectstatic test clean deploy-gcp seed reset-db

deploy-gcp:
	./scripts/deploy-gcp.sh

# Cria o ambiente virtual local se ainda não existir
$(PY):
	$(PYTHON_HOST) -m venv $(VENV)

install: $(PY)
	$(PIP) install -r requirements.txt

migrate: install
	$(MANAGE) migrate --noinput

# Um comando: venv + deps + migrate + servidor
run: migrate
	$(MANAGE) runserver

venv: $(PY)
	@echo "Ambiente em $(VENV) — rode: make run"

makemigrations: install
	$(MANAGE) makemigrations

superuser: install
	$(MANAGE) createsuperuser

shell: install
	$(MANAGE) shell

collectstatic: install
	$(MANAGE) collectstatic --noinput

test: install
	$(MANAGE) test

seed: install
	$(MANAGE) seed

reset-db: install
	rm -f db.sqlite3
	$(MANAGE) makemigrations website
	$(MANAGE) migrate --noinput
	$(MANAGE) seed

clean:
	find . -name "*.pyc" -delete
	find . -name "__pycache__" -delete