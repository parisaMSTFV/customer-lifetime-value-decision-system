.PHONY: install run test lint format clean

install:
	python -m pip install -e .

run:
	python scripts/run_pipeline.py

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

