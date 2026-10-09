.PHONY: help install install-dev test test-cov lint format format-check type-check type-baseline docs docs-serve man bench clean build changelog pre-commit-install pre-commit-run check-all ci

help: ## Show this help message
	@echo "Available targets:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-20s %s\n", $$1, $$2}'

install: ## Install package in production mode
	pip install -e .

install-dev: ## Install package with development dependencies
	pip install -e ".[dev]"

test: ## Run tests
	pytest

test-cov: ## Run tests with coverage
	pytest --cov=undatum --cov-report=html --cov-report=term

lint: ## Run linters
	ruff check undatum/ tests/ scripts/
	python scripts/check_dependency_bounds.py

format: ## Format code with ruff
	ruff format undatum/ tests/ scripts/

format-check: ## Check code formatting without making changes
	ruff format --check undatum/ tests/ scripts/

type-check: ## Run the mypy ratchet (errors per file may only go down)
	python scripts/mypy_ratchet.py

type-baseline: ## Lock in fixed type errors (rewrites mypy-baseline.json)
	python scripts/mypy_ratchet.py --update

man: ## Generate man/undatum.1 from the CLI
	python scripts/generate_manpage.py

bench: ## Benchmark core commands on 100k rows against tests/benchmarks/budgets.toml
	python scripts/benchmarks.py generate --tier 100k --dir .bench-data
	python scripts/benchmarks.py run --tier 100k --data .bench-data --out .bench-data/results.json
	python scripts/benchmarks.py check .bench-data/results.json

docs: ## Build documentation site (Docusaurus)
	cd docs && npm ci && npm run build

docs-serve: ## Serve documentation locally (Docusaurus)
	cd docs && npm start

clean: ## Clean build artifacts
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info
	rm -rf .pytest_cache
	rm -rf .mypy_cache
	rm -rf htmlcov/
	rm -rf docs/_build/
	rm -rf docs/build/
	rm -rf docs/.docusaurus/
	find . -type d -name __pycache__ -exec rm -r {} +
	find . -type f -name "*.pyc" -delete

build: ## Build distribution packages
	python -m build

changelog: ## Preview unreleased CHANGELOG entries from Conventional Commits (needs git-cliff)
	git cliff --unreleased

pre-commit-install: ## Install pre-commit hooks
	pre-commit install

pre-commit-run: ## Run pre-commit hooks on all files
	pre-commit run --all-files

check-all: format-check lint type-check test ## Run all checks

ci: check-all ## Run all CI checks (alias for check-all)
