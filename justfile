[private]
default:
	@just --list

# setup virtual environment
devel:
	@uv sync --frozen

# tidy everything with ruff
[group("Analysis/Fixing")]
tidy:
	@uv run --frozen ruff check --fix

# run the typechecker
[group("Analysis/Fixing")]
typecheck:
	@uv run --frozen mypy socketmapsql.py

# clean up any caches or temporary files and directories
clean:
	@rm -rf .mypy_cache .ruff_cache .venv dist
	@find . -name \*.orig -delete

# install tools (you'll have to ensure you have uv already installed)
tools:
	@uv tool install ruff

# Build the source distribution and wheel
[group("Release")]
build:
	@uv build

# Push this release to PyPI
[group("Release")]
publish:
	@uv publish
