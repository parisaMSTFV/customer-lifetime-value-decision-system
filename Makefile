.PHONY: install run public-data public-snapshots public-validate test lint format clean

install:
	python -m pip install -e .

run:
	python scripts/run_pipeline.py

public-data:
	python scripts/download_public_data.py

public-snapshots:
	python scripts/build_public_snapshots.py

public-validate:
	python scripts/run_public_validation.py

test:
	python -m unittest discover -s tests -v

lint:
	ruff check .
	ruff format --check .

format:
	ruff check --fix .
	ruff format .

clean:
	python scripts/clean_generated.py
