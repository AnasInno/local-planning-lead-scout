from __future__ import annotations

import csv
import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile


ROOT = Path(__file__).resolve().parents[1]


def run_script(
    script: str, *args: str, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, script, *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )


def run_command(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return run_script("scripts/run.py", *args, env=env)


def test_smoke_command_generates_output_without_llm():
    out = ROOT / "output" / "sample_output.csv"
    if out.exists():
        out.unlink()

    result = run_command(
        "--source",
        "csv",
        "--input",
        "data/sample_input.txt",
        "--output",
        "output/sample_output.csv",
        "--area",
        "Manchester",
        "--trade",
        "roofer",
        "--days",
        "30",
        "--today",
        "2026-06-24",
        "--llm-mode",
        "off",
    )

    assert result.returncode == 0, result.stderr
    assert out.exists()

    with out.open(newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)

    assert rows[0]["reference"] == "MCR-2026-002"
    assert "rule_score" in reader.fieldnames
    assert "outreach_message" in reader.fieldnames
    assert all(row["llm_model"] == "" for row in rows)
    assert any(row["outreach_message"] for row in rows)


def test_api_fixture_generates_ranked_output():
    out = ROOT / "output" / "api_fixture_output.csv"
    if out.exists():
        out.unlink()

    env = os.environ.copy()
    env.pop("GEMINI_API_KEY", None)
    env.pop("GEMINI_MODEL", None)

    result = run_command(
        "--source",
        "api",
        "--api-fixture",
        "data/sample_planning_api_response.json",
        "--output",
        "output/api_fixture_output.csv",
        "--trade",
        "roofer",
        "--days",
        "30",
        "--today",
        "2026-06-24",
        "--llm-mode",
        "off",
        env=env,
    )

    assert result.returncode == 0, result.stderr
    assert out.exists()

    with out.open(newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)

    assert rows
    assert {"site_address", "description"}.issubset(reader.fieldnames or [])
    assert any(row["site_address"] and row["description"] for row in rows)


def test_missing_required_csv_columns_still_fails(tmp_path: Path):
    bad_input = tmp_path / "missing_description.csv"
    bad_input.write_text(
        "reference,area,site_address,status,application_type,validated_date,decision_date,source_url\n"
        "BAD-001,Manchester,1 Example Street,validated,alteration,2026-06-24,,https://example.test/BAD-001\n"
    )

    result = run_command(
        "--source",
        "csv",
        "--input",
        str(bad_input),
        "--output",
        "output/missing_columns_output.csv",
        "--llm-mode",
        "off",
    )

    assert result.returncode != 0
    assert "Input CSV missing required columns" in result.stdout + result.stderr


def test_owner_once_requires_ai_when_no_fixture_or_key():
    out = ROOT / "output" / "owner_shortlist.csv"
    if out.exists():
        out.unlink()

    env = os.environ.copy()
    env.pop("GEMINI_API_KEY", None)
    env.pop("GEMINI_MODEL", None)

    result = run_script(
        "scripts/owner_app.py",
        "--once",
        "--trade",
        "roofer",
        "--area-postcode",
        "Manchester",
        "--days",
        "30",
        "--output",
        "output/owner_shortlist.csv",
        env=env,
    )

    assert result.returncode != 0
    assert "AI key is required" in result.stdout + result.stderr


def test_owner_once_generates_ai_ranked_shortlist_csv():
    out = ROOT / "output" / "owner_shortlist.csv"
    if out.exists():
        out.unlink()

    env = os.environ.copy()
    env.pop("GEMINI_API_KEY", None)
    env.pop("GEMINI_MODEL", None)

    result = run_script(
        "scripts/owner_app.py",
        "--once",
        "--trade",
        "roofer",
        "--area-postcode",
        "Manchester",
        "--days",
        "30",
        "--output",
        "output/owner_shortlist.csv",
        "--ai-fixture",
        "data/sample_owner_ai_insights.json",
        env=env,
    )

    assert result.returncode == 0, result.stderr
    assert out.exists()
    assert "Wrote output/owner_shortlist.csv" in result.stdout

    with out.open(newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)

    assert reader.fieldnames == [
        "rank",
        "address",
        "planning_reference",
        "fit",
        "fit_score",
        "why_it_matched",
        "suggested_next_action",
        "planning_link",
    ]
    assert rows
    assert rows[0]["address"] == "8 Sample Street"
    assert rows[0]["planning_reference"] == "MCR-2026-002"
    assert rows[0]["fit"] == "High"
    assert int(rows[0]["fit_score"]) >= 85
    assert (
        rows[0]["why_it_matched"]
        == "Loft conversion and rear dormer roof extension are a strong roofing fit."
    )
    assert rows[0]["planning_link"].startswith("https://planning.example.local/")
    assert all("llm_" not in field_name for field_name in reader.fieldnames or [])
    assert "rule_score" not in (reader.fieldnames or [])
    assert "source_url" not in (reader.fieldnames or [])


def test_owner_web_config_hides_technical_fields():
    config = json.loads((ROOT / "web_config.json").read_text())

    assert [field["name"] for field in config["fields"]] == ["trade", "area_postcode", "days"]

    serialized = json.dumps(config)
    for hidden_text in [
        "llm_mode",
        "source",
        "radius_km",
        "records_csv",
        "local web shell",
        "model name",
        "temperature",
    ]:
        assert hidden_text not in serialized
    assert "sample_owner_ai_insights.json" in serialized


def test_owner_package_zip_contains_double_click_ai_app(tmp_path: Path):
    zip_path = tmp_path / "local-planning-lead-scout.zip"

    result = run_script("scripts/package_owner_app.py", "--output", str(zip_path))

    assert result.returncode == 0, result.stderr
    assert zip_path.exists()

    with zipfile.ZipFile(zip_path) as archive:
        members = sorted(archive.namelist())

    assert members == sorted(
        [
            "local-planning-lead-scout/Start.command",
            "local-planning-lead-scout/Start.bat",
            "local-planning-lead-scout/README.md",
            "local-planning-lead-scout/scripts/owner_app.py",
            "local-planning-lead-scout/scripts/run.py",
            "local-planning-lead-scout/data/sample_input.txt",
            "local-planning-lead-scout/data/sample_planning_api_response.json",
            "local-planning-lead-scout/data/sample_owner_ai_insights.json",
            "local-planning-lead-scout/output/.gitkeep",
        ]
    )

    for member in members:
        assert ".env" not in member
        assert ".pytest_cache" not in member
        assert "VERIFY.md" not in member
        assert "drafts" not in member
        assert "runs" not in member
        assert "llm_sample_output.csv" not in member
        assert "owner_shortlist.csv" not in member
