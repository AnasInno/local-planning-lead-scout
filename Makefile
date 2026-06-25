.PHONY: smoke technical-smoke web app package test clean

smoke:
	python3 scripts/owner_app.py --once --trade roofer --area-postcode Manchester --days 30 --output output/owner_shortlist.csv --ai-fixture data/sample_owner_ai_insights.json

technical-smoke:
	python3 scripts/run.py --source csv --input data/sample_input.txt --output output/sample_output.csv --area "Manchester" --trade "roofer" --days 30 --today 2026-06-24 --llm-mode off

web:
	python3 scripts/owner_app.py

app:
	python3 scripts/owner_app.py

package:
	python3 scripts/package_owner_app.py

test:
	python3 -m pytest -q

clean:
	rm -f output/owner_shortlist.csv dist/local-planning-lead-scout.zip output/sample_output.csv output/api_fixture_output.csv output/llm_sample_output.csv data/web_*
