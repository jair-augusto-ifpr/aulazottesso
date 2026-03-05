PYTHON=python
PIP=pip
MANAGE=$(PYTHON) manage.py

install:
	$(PIP) install -r requirements.txt

run:
	$(MANAGE) runserver

migrate:
	$(MANAGE) migrate

makemigrations:
	$(MANAGE) makemigrations

superuser:
	$(MANAGE) createsuperuser

shell:
	$(MANAGE) shell

collectstatic:
	$(MANAGE) collectstatic --noinput

test:
	$(MANAGE) test

clean:
	find . -name "*.pyc" -delete
	find . -name "__pycache__" -delete