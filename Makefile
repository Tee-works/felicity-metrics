PYTHON ?= python3

.PHONY: run test install postgres-check clean

install:
	$(PYTHON) -m pip install -r requirements.txt

run:
	$(PYTHON) run.py

test:
	$(PYTHON) -m pytest -q

# Needs psql and PGURL pointing at a scratch database. Run `make run` first.
postgres-check:
	scripts/postgres_check.sh

clean:
	rm -rf data .pytest_cache
