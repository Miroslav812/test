.PHONY: install check test smoke parallel ui ui-headed all report demo

install:
	uv sync --frozen

check:
	uv run --frozen ruff check .
	uv run --frozen ruff format --check .
	uv run --frozen mypy

test:
	uv run --frozen pytest --alluredir=reports/allure-results --clean-alluredir --junitxml=reports/junit.xml

smoke:
	uv run --frozen pytest -m smoke

parallel:
	uv run --frozen pytest -n 2 --alluredir=reports/allure-results --clean-alluredir --junitxml=reports/junit.xml

ui:
	uv run --frozen --group ui pytest tests/ui --alluredir=reports/ui/allure-results --clean-alluredir --junitxml=reports/ui/junit.xml

ui-headed:
	uv run --frozen --group ui pytest tests/ui --headed

all:
	uv run --frozen --group ui pytest tests --alluredir=reports/allure-results --clean-alluredir --junitxml=reports/junit.xml

report:
	allure generate reports/allure-results --clean -o reports/allure-report

demo:
	uv run --frozen uvicorn demo_api.app:create_app --factory --host 127.0.0.1 --port 8000 --ws none
