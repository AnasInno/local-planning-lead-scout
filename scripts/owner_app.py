#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import html
import os
import sys
import urllib.parse
import webbrowser
from datetime import date
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import run as engine


APP_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = APP_ROOT / "output" / "owner_shortlist.csv"
DEFAULT_TODAY = date(2026, 6, 24)
LOCAL_ENV_PATH = APP_ROOT / ".env"
DEFAULT_MODEL = engine.OWNER_AI_MODEL


OWNER_TABLE_COLUMNS = [
    ("address", "Address"),
    ("planning_reference", "Planning reference"),
    ("why_it_matched", "Why it matched"),
    ("fit", "Fit"),
    ("fit_score", "Score"),
    ("suggested_next_action", "Next action"),
    ("planning_link", "Planning link"),
]


def app_path(value: str | Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return APP_ROOT / path


def display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(APP_ROOT))
    except ValueError:
        return str(path)


def read_dotenv_key(path: Path = LOCAL_ENV_PATH) -> str:
    if not path.exists():
        return ""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return ""
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        if key.strip() == "GEMINI_API_KEY":
            return value.strip().strip('"').strip("'")
    return ""


def save_local_ai_key(api_key: str, path: Path = LOCAL_ENV_PATH) -> None:
    key = api_key.strip()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"GEMINI_API_KEY={key}\nGEMINI_MODEL={DEFAULT_MODEL}\n", encoding="utf-8")
    if os.name == "posix":
        path.chmod(0o600)


def resolve_ai_key(explicit_key: str = "", env_file: str = "") -> str:
    if explicit_key.strip():
        return explicit_key.strip()
    env_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if env_key:
        return env_key
    if env_file.strip():
        file_key = read_dotenv_key(app_path(env_file))
        if file_key:
            return file_key
    return read_dotenv_key(LOCAL_ENV_PATH)


def safe_days(value: object) -> int:
    try:
        days = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 30
    if days <= 0:
        return 30
    return days


def search_options_for_owner(trade: str, area_postcode: str, days: int) -> tuple[engine.LeadSearchOptions, str]:
    owner_trade = trade.strip() or "roofer"
    location = area_postcode.strip() or "Manchester"
    lookback_days = safe_days(days)
    if engine.looks_like_postcode_or_outcode(location):
        return (
            engine.LeadSearchOptions(
                source="api",
                area="",
                trade=owner_trade,
                days=lookback_days,
                today=None,
                min_score=1,
                postcode=location,
                planning_limit=100,
                api_timeout=30,
                llm_mode="off",
            ),
            f"Live public planning data for {location}",
        )
    return (
        engine.LeadSearchOptions(
            source="csv",
            input_path=APP_ROOT / "data" / "sample_input.txt",
            area=location,
            trade=owner_trade,
            days=lookback_days,
            today=DEFAULT_TODAY,
            min_score=1,
            llm_mode="off",
        ),
        f"Demo sample data for {location}",
    )


def run_owner_search(
    trade: str,
    area_postcode: str,
    days: int,
    output: Path = DEFAULT_OUTPUT,
    api_key: str = "",
    env_file: str = "",
    ai_fixture: Path | None = None,
) -> tuple[list[dict[str, str]], str, Path]:
    options, mode_label = search_options_for_owner(trade, area_postcode, days)
    leads = engine.find_leads(options)
    fixture_path = ai_fixture
    key = "" if fixture_path is not None else resolve_ai_key(api_key, env_file)
    if fixture_path is None and not key.strip():
        raise SystemExit("AI key is required. Paste your Gemini API key once to score leads.")
    ranked = engine.rank_owner_leads_with_ai(
        leads,
        trade=options.trade,
        api_key=key,
        fixture_path=fixture_path,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    engine.write_owner_shortlist(ranked, output)
    return engine.owner_rows_from_ranked_leads(ranked), mode_label, output


def read_file_value(path_text: str, default: str) -> str:
    if not path_text.strip():
        return default
    return app_path(path_text).read_text(encoding="utf-8").strip()


def read_rows_from_output(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def page_shell(title: str, body: str) -> bytes:
    document = f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
  <title>{html.escape(title)}</title>
  <style>
    :root {{ color-scheme: light; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; }}
    body {{ margin: 0; background: #f7f4ed; color: #172017; }}
    main {{ max-width: 1080px; margin: 0 auto; padding: 32px 20px 56px; }}
    .hero, .panel {{ background: #fffdf8; border: 1px solid #ded6c9; border-radius: 24px; padding: 24px; box-shadow: 0 18px 40px rgba(44, 35, 20, 0.08); }}
    .hero {{ margin-bottom: 18px; }}
    h1 {{ margin: 0 0 8px; font-size: clamp(2rem, 5vw, 4rem); line-height: 0.95; }}
    h2 {{ margin-top: 0; }}
    p {{ line-height: 1.55; }}
    form {{ display: grid; gap: 16px; }}
    label {{ display: grid; gap: 6px; font-weight: 700; }}
    input {{ border: 1px solid #cfc6b6; border-radius: 12px; font: inherit; padding: 12px 14px; background: white; }}
    button, .button {{ appearance: none; border: 0; border-radius: 999px; background: #172017; color: white; cursor: pointer; display: inline-block; font: inherit; font-weight: 800; padding: 12px 18px; text-decoration: none; }}
    .grid {{ display: grid; gap: 18px; grid-template-columns: minmax(0, 0.9fr) minmax(0, 1.1fr); }}
    .notice {{ background: #ecf8ec; border: 1px solid #b9d9ba; border-radius: 16px; padding: 12px 14px; }}
    .error {{ background: #fff0ed; border: 1px solid #e0aaa0; border-radius: 16px; padding: 12px 14px; }}
    .actions {{ display: flex; flex-wrap: wrap; gap: 10px; margin: 16px 0; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 0.95rem; }}
    th, td {{ border-bottom: 1px solid #e5ded2; padding: 12px 10px; text-align: left; vertical-align: top; }}
    th {{ color: #5f4d35; font-size: 0.8rem; letter-spacing: 0.04em; text-transform: uppercase; }}
    .muted {{ color: #645a4c; }}
    @media (max-width: 820px) {{ .grid {{ grid-template-columns: 1fr; }} table {{ display: block; overflow-x: auto; }} }}
  </style>
</head>
<body>
  <main>{body}</main>
</body>
</html>"""
    return document.encode("utf-8")


def render_form(trade: str, area_postcode: str, days: int, key_saved: bool, message: str = "", error: str = "") -> str:
    message_html = f'<div class="notice">{html.escape(message)}</div>' if message else ""
    error_html = f'<div class="error">{html.escape(error)}</div>' if error else ""
    key_status = "AI key saved on this computer." if key_saved else "Paste your Gemini API key once before searching."
    return f"""
<section class=\"hero\">
  <h1>Planning Lead Scout</h1>
  <p>Put in your trade and area. Get this week's planning jobs worth checking.</p>
</section>
{message_html}
{error_html}
<div class=\"grid\">
  <section class=\"panel\">
    <h2>AI setup</h2>
    <p>Paste your Gemini API key once. It stays on this computer and is used only to score planning leads.</p>
    <p class=\"muted\">{html.escape(key_status)}</p>
    <form method=\"post\" action=\"/save-key\">
      <label>Gemini API key
        <input name=\"api_key\" type=\"password\" autocomplete=\"off\" placeholder=\"Paste key here\">
      </label>
      <button type=\"submit\">Save key</button>
    </form>
  </section>
  <section class=\"panel\">
    <h2>Find leads</h2>
    <form method=\"post\" action=\"/run\">
      <label>Trade
        <input name=\"trade\" value=\"{html.escape(trade)}\">
      </label>
      <label>Town or postcode
        <input name=\"area_postcode\" value=\"{html.escape(area_postcode)}\">
      </label>
      <label>Date range
        <input name=\"days\" type=\"number\" min=\"1\" value=\"{html.escape(str(days))}\">
      </label>
      <button type=\"submit\">Find leads</button>
    </form>
  </section>
</div>
"""


def render_results(rows: list[dict[str, str]], mode_label: str) -> str:
    mode_html = f'<p class="muted">{html.escape(mode_label)}</p>' if mode_label else ""
    if not rows:
        table_html = "<p>No matching AI-ranked leads found for this search. Try a wider date range or a nearby postcode.</p>"
    else:
        header_html = "".join(f"<th>{html.escape(label)}</th>" for _, label in OWNER_TABLE_COLUMNS)
        body_rows = []
        for row in rows:
            cells = []
            for key, _label in OWNER_TABLE_COLUMNS:
                value = row.get(key, "")
                if key == "planning_link" and value:
                    cells.append(f'<td><a href="{html.escape(value, quote=True)}" target="_blank" rel="noreferrer">Open planning page</a></td>')
                else:
                    cells.append(f"<td>{html.escape(value)}</td>")
            body_rows.append(f"<tr>{''.join(cells)}</tr>")
        table_html = f"<table><thead><tr>{header_html}</tr></thead><tbody>{''.join(body_rows)}</tbody></table>"
    return f"""
<section class=\"panel\" style=\"margin-top: 18px;\">
  <h2>Shortlist</h2>
  {mode_html}
  <div class=\"actions\"><a class=\"button\" href=\"/download\">Download CSV</a><a class=\"button\" href=\"/print\">Print</a></div>
  {table_html}
</section>
"""


def render_home(state: dict[str, Any], message: str = "", error: str = "") -> bytes:
    body = render_form(
        state.get("trade", "roofer"),
        state.get("area_postcode", "Manchester"),
        state.get("days", 30),
        bool(resolve_ai_key()),
        message=message,
        error=error,
    )
    if state.get("has_run"):
        body += render_results(state.get("rows", []), state.get("mode_label", ""))
    return page_shell("Planning Lead Scout", body)


def render_print_page(rows: list[dict[str, str]]) -> bytes:
    body = """
<section class=\"hero\"><h1>Planning Lead Scout</h1><p>Put in your trade and area. Get this week's planning jobs worth checking.</p></section>
<section class=\"panel\"><h2>Shortlist</h2>
"""
    if rows:
        header_html = "".join(f"<th>{html.escape(label)}</th>" for _, label in OWNER_TABLE_COLUMNS)
        row_html = []
        for row in rows:
            row_html.append("<tr>" + "".join(f"<td>{html.escape(row.get(key, ''))}</td>" for key, _ in OWNER_TABLE_COLUMNS) + "</tr>")
        body += f"<table><thead><tr>{header_html}</tr></thead><tbody>{''.join(row_html)}</tbody></table>"
    else:
        body += "<p>No matching AI-ranked leads found for this search. Try a wider date range or a nearby postcode.</p>"
    body += "</section><script>window.print()</script>"
    return page_shell("Planning Lead Scout", body)


def parse_post_body(handler: BaseHTTPRequestHandler) -> dict[str, str]:
    length = int(handler.headers.get("Content-Length", "0") or "0")
    raw = handler.rfile.read(length).decode("utf-8")
    parsed = urllib.parse.parse_qs(raw, keep_blank_values=True)
    return {key: values[-1] if values else "" for key, values in parsed.items()}


class OwnerAppHandler(BaseHTTPRequestHandler):
    server: "OwnerAppServer"

    def log_message(self, format: str, *args: object) -> None:
        return

    def send_html(self, body: bytes, status: HTTPStatus = HTTPStatus.OK) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        path = urllib.parse.urlparse(self.path).path
        if path == "/":
            self.send_html(render_home(self.server.state))
            return
        if path == "/download":
            output = self.server.output_path
            if not output.exists():
                self.send_error(HTTPStatus.NOT_FOUND, "No shortlist has been created yet")
                return
            data = output.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/csv; charset=utf-8")
            self.send_header("Content-Disposition", 'attachment; filename="owner_shortlist.csv"')
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        if path == "/print":
            self.send_html(render_print_page(self.server.state.get("rows", [])))
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        path = urllib.parse.urlparse(self.path).path
        form = parse_post_body(self)
        if path == "/save-key":
            key = form.get("api_key", "").strip()
            if not key:
                self.send_html(render_home(self.server.state, error="Paste a valid AI key to score leads."), HTTPStatus.BAD_REQUEST)
                return
            save_local_ai_key(key)
            self.send_html(render_home(self.server.state, message="AI key saved."))
            return
        if path == "/run":
            trade = form.get("trade", "roofer")
            area_postcode = form.get("area_postcode", "Manchester")
            days = safe_days(form.get("days", "30"))
            self.server.state.update({"trade": trade.strip() or "roofer", "area_postcode": area_postcode.strip() or "Manchester", "days": days})
            try:
                rows, mode_label, output_path = run_owner_search(
                    trade,
                    area_postcode,
                    days,
                    output=self.server.output_path,
                    ai_fixture=self.server.fixture_path,
                )
            except (SystemExit, ValueError, RuntimeError, OSError) as exc:
                self.send_html(render_home(self.server.state, error=one_line_error(exc)), HTTPStatus.BAD_REQUEST)
                return
            self.server.output_path = output_path
            self.server.state.update({"rows": rows, "mode_label": mode_label, "has_run": True})
            self.send_html(render_home(self.server.state))
            return
        self.send_error(HTTPStatus.NOT_FOUND)


class OwnerAppServer(ThreadingHTTPServer):
    def __init__(self, server_address: tuple[str, int], handler_class: type[BaseHTTPRequestHandler], output_path: Path, fixture_path: Path | None):
        super().__init__(server_address, handler_class)
        self.output_path = output_path
        self.fixture_path = fixture_path
        self.state: dict[str, Any] = {
            "trade": "roofer",
            "area_postcode": "Manchester",
            "days": 30,
            "rows": [],
            "mode_label": "",
            "has_run": False,
            "fixture_path": fixture_path,
        }


def one_line_error(exc: BaseException) -> str:
    if isinstance(exc, SystemExit):
        if exc.code in (None, 0):
            return ""
        return " ".join(str(exc.code).split())
    text = str(exc) or exc.__class__.__name__
    return " ".join(text.split())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-open", action="store_true")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--trade", default="roofer")
    parser.add_argument("--trade-file", default="")
    parser.add_argument("--area-postcode", default="Manchester")
    parser.add_argument("--area-postcode-file", default="")
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--days-file", default="")
    parser.add_argument("--output", default="output/owner_shortlist.csv")
    parser.add_argument("--api-key", default="")
    parser.add_argument("--env-file", default="")
    parser.add_argument("--ai-fixture", default="")
    return parser


def run_once(args: argparse.Namespace) -> int:
    output = app_path(args.output)
    fixture = app_path(args.ai_fixture) if args.ai_fixture.strip() else None
    try:
        trade = read_file_value(args.trade_file, args.trade)
        area_postcode = read_file_value(args.area_postcode_file, args.area_postcode)
        days_text = read_file_value(args.days_file, str(args.days))
        rows, _mode_label, output_path = run_owner_search(
            trade,
            area_postcode,
            safe_days(days_text),
            output=output,
            api_key=args.api_key,
            env_file=args.env_file,
            ai_fixture=fixture,
        )
    except (SystemExit, ValueError, RuntimeError, OSError) as exc:
        message = one_line_error(exc)
        if message:
            print(message, file=sys.stderr)
        return 1
    print(f"Wrote {display_path(output_path)} ({len(rows)} leads)")
    return 0


def serve(args: argparse.Namespace) -> int:
    output = app_path(args.output)
    fixture = app_path(args.ai_fixture) if args.ai_fixture.strip() else None
    server = OwnerAppServer((args.host, args.port), OwnerAppHandler, output, fixture)
    url = f"http://{args.host}:{args.port}"
    if not args.no_open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    finally:
        server.server_close()
    return 0


def main() -> int:
    args = build_parser().parse_args()
    if args.once:
        return run_once(args)
    return serve(args)


if __name__ == "__main__":
    raise SystemExit(main())
