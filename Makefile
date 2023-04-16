.venv:
	python3 -m venv .venv

dev: .venv
	.venv/bin/pip install flit
	.venv/bin/flit install --symlink

wheel: dev
	.venv/bin/flit build

release: wheel
	.venv/bin/flit publish

.PHONY: dev wheel release
