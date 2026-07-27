.PHONY: sync test lint typecheck build check serve docker-build

sync:
	uv sync --frozen

test:
	PYTHONPATH="$(KEOL_SOURCE):$$PYTHONPATH" uv run pytest -q

lint:
	uv run ruff check src service ontology tests scripts

typecheck:
	uv run pyright

build:
	uv build

check:
	KEOL_SOURCE="$(KEOL_SOURCE)" scripts/ci/check.sh

serve:
	uv run ke-memory-serve

docker-build:
	docker build -t ke-memory:local .
