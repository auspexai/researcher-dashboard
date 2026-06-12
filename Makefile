# Local CI gate — mirrors .github/workflows/ci.yml (backend + frontend jobs)
# so a green `make ci` is a green CI run (CI additionally runs the backend on
# a 3.11/3.12 matrix). Run before every push.
#
# CI resolves auspexai-tenant from git@main (not on PyPI yet); locally we
# install the sibling checkout so the gate tests against what you are about
# to push.
.PHONY: ci ci-backend ci-frontend backend-venv backend-lint backend-test

ci: ci-backend ci-frontend

ci-backend: backend-venv backend-lint backend-test

backend-venv:
	cd backend && uv venv --clear
	cd backend && uv pip install ../../tenant-sdk
	cd backend && uv pip install -e ".[dev]"

backend-lint:
	cd backend && .venv/bin/ruff check src tests
	cd backend && .venv/bin/ruff format --check src tests

backend-test:
	cd backend && .venv/bin/pytest

ci-frontend:
	cd frontend && pnpm install --no-frozen-lockfile
	cd frontend && pnpm run check
	cd frontend && pnpm run build
