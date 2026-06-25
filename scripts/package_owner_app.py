#!/usr/bin/env python3
from __future__ import annotations

import argparse
import zipfile
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[1]
ZIP_ROOT = "local-planning-lead-scout"
PACKAGE_FILES = [
    (APP_ROOT / "Start.command", "Start.command"),
    (APP_ROOT / "Start.bat", "Start.bat"),
    (APP_ROOT / "OWNER_README.md", "README.md"),
    (APP_ROOT / "scripts" / "owner_app.py", "scripts/owner_app.py"),
    (APP_ROOT / "scripts" / "run.py", "scripts/run.py"),
    (APP_ROOT / "data" / "sample_input.txt", "data/sample_input.txt"),
    (APP_ROOT / "data" / "sample_planning_api_response.json", "data/sample_planning_api_response.json"),
    (APP_ROOT / "data" / "sample_owner_ai_insights.json", "data/sample_owner_ai_insights.json"),
    (APP_ROOT / "output" / ".gitkeep", "output/.gitkeep"),
]


def add_file(archive: zipfile.ZipFile, source: Path, relative_name: str) -> None:
    data = source.read_bytes()
    info = zipfile.ZipInfo(f"{ZIP_ROOT}/{relative_name}")
    info.compress_type = zipfile.ZIP_DEFLATED
    mode = 0o755 if relative_name == "Start.command" else 0o644
    info.external_attr = mode << 16
    archive.writestr(info, data)


def build_package(output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w") as archive:
        for source, relative_name in PACKAGE_FILES:
            add_file(archive, source, relative_name)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="dist/local-planning-lead-scout.zip")
    args = parser.parse_args()
    output_arg = Path(args.output)
    output = output_arg if output_arg.is_absolute() else APP_ROOT / output_arg
    build_package(output)
    print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
