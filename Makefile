.PHONY: test lint
test:
	uv run --extra dev ruff check src tests
	uv run --extra dev pytest -q

lint:
	uv run --extra dev ruff check src tests
