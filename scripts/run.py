#!/usr/bin/env python3
from __future__ import annotations
"""Public planning lead scout with deterministic and optional Gemini scoring."""

import argparse
import csv
import json
import math
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, replace
from datetime import date, timedelta
from pathlib import Path
from typing import Any


REQUIRED_COLUMNS = [
    "reference",
    "area",
    "site_address",
    "description",
    "status",
    "application_type",
    "validated_date",
    "decision_date",
    "source_url",
]

OUTPUT_COLUMNS = [
    "rank",
    "score",
    "rule_score",
    "reference",
    "area",
    "site_address",
    "description",
    "status",
    "application_type",
    "validated_date",
    "decision_date",
    "likely_trade_category",
    "matched_keywords",
    "reason",
    "suggested_outreach_angle",
    "llm_trade_fit",
    "llm_work_types",
    "llm_value_signal",
    "llm_urgency",
    "llm_reason",
    "outreach_message",
    "llm_confidence",
    "llm_model",
    "llm_error",
    "source_url",
]

OWNER_OUTPUT_COLUMNS = [
    "rank",
    "address",
    "planning_reference",
    "fit",
    "fit_score",
    "why_it_matched",
    "suggested_next_action",
    "planning_link",
]

TRADE_KEYWORDS = {
    "roofer": [
        "roof",
        "roofing",
        "rooflight",
        "dormer",
        "loft",
        "slate",
        "tile",
        "chimney",
        "solar",
        "extension",
    ],
    "builder": [
        "extension",
        "conversion",
        "garage",
        "alteration",
        "rear",
        "side",
        "storey",
    ],
    "electrician": [
        "electrical",
        "wiring",
        "solar",
        "battery",
        "lighting",
        "lights",
        "ev charger",
    ],
    "window fitter": [
        "window",
        "windows",
        "rooflight",
        "glazing",
        "door",
        "doors",
        "fenestration",
    ],
    "architect": [
        "planning",
        "design",
        "drawing",
        "extension",
        "conversion",
        "dormer",
        "alteration",
    ],
}

EXCLUSION_TERMS = [
    "tree",
    "tree works",
    "signage",
    "advertisement",
    "telecoms",
    "discharge condition",
]

TRADE_FITS = {"high", "medium", "low", "none"}
VALUE_SIGNALS = {"small", "medium", "large", "unknown"}
URGENCY_VALUES = {"now", "soon", "monitor", "low"}

LLM_ALLOWED_FIELDS = [
    "reference",
    "site_address",
    "description",
    "status",
    "application_type",
    "validated_date",
    "decision_date",
    "source_url",
]


@dataclass(frozen=True)
class LeadInsight:
    trade_fit: str
    work_types: list[str]
    value_signal: str
    urgency: str
    reason: str
    outreach_message: str
    confidence: float
    model: str
    error: str


@dataclass(frozen=True)
class ScoredLead:
    score: int
    rule_score: int
    reference: str
    area: str
    site_address: str
    description: str
    status: str
    application_type: str
    validated_date: str
    decision_date: str
    source_url: str
    likely_trade_category: str
    matched_keywords: list[str]
    reason: str
    suggested_outreach_angle: str
    llm_trade_fit: str
    llm_work_types: list[str]
    llm_value_signal: str
    llm_urgency: str
    llm_reason: str
    outreach_message: str
    llm_confidence: str
    llm_model: str
    llm_error: str

OWNER_AI_MODEL = "gemini-2.5-flash"
OWNER_AI_ENDPOINT_TEMPLATE = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
OWNER_AI_FITS = {"high", "medium", "low", "not_relevant"}
OWNER_AI_URGENCIES = {"now", "soon", "monitor", "ignore"}


@dataclass(frozen=True)
class OwnerAiInsight:
    fit: str
    urgency: str
    why_it_matched: str
    suggested_next_action: str
    confidence: float
    model: str
    error: str = ""


@dataclass(frozen=True)
class OwnerRankedLead:
    lead: ScoredLead
    insight: OwnerAiInsight
    owner_score: int


@dataclass(frozen=True)
class LeadSearchOptions:
    source: str = "csv"
    input_path: Path = Path("data/sample_input.txt")
    area: str = ""
    trade: str = "roofer"
    days: int = 30
    today: date | None = None
    min_score: int = 0
    postcode: str = ""
    radius_km: float = 5.0
    geometry_wkt: str = ""
    planning_limit: int = 100
    api_timeout: int = 30
    api_fixture_path: Path | None = None
    llm_mode: str = "off"
    gemini_model: str = ""
    env_file: str = ""
    max_llm_records: int = 10


def parse_date(value: str) -> date | None:
    if not value.strip():
        return None
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        return None


def read_text_arg(value: str | None, file_path: str | None, default: str) -> str:
    if value is not None:
        return value.strip()
    if file_path is not None:
        path = Path(file_path)
        if not path.exists():
            raise SystemExit(f"Input file not found: {path}")
        return path.read_text(encoding="utf-8").strip()
    return default


def normalize_whitespace(value: object) -> str:
    return " ".join(str(value or "").split())


def load_records(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise SystemExit(f"Input file not found: {path}")

    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        missing_columns = [
            column for column in REQUIRED_COLUMNS if column not in fieldnames
        ]
        if missing_columns:
            raise SystemExit(
                "Input CSV missing required columns: " + ", ".join(missing_columns)
            )

        records: list[dict[str, str]] = []
        for row in reader:
            records.append(
                {
                    column: (row.get(column) or "").strip()
                    for column in REQUIRED_COLUMNS
                }
            )
        return records


def load_env_file(path_text: str) -> None:
    if not path_text.strip():
        return
    path = Path(path_text)
    if not path.exists():
        raise SystemExit(f"Env file not found: {path}")
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key or key in os.environ:
            continue
        value = value.strip().strip('"').strip("'")
        os.environ[key] = value


OUTCODE_PATTERN = re.compile(r"^[A-Z]{1,2}\d[A-Z\d]?$", re.IGNORECASE)
FULL_POSTCODE_PATTERN = re.compile(r"^[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}$", re.IGNORECASE)


def normalize_location_query(value: str) -> str:
    return " ".join(value.strip().upper().split())


def looks_like_outcode(value: str) -> bool:
    return bool(OUTCODE_PATTERN.fullmatch(normalize_location_query(value).replace(" ", "")))


def looks_like_full_postcode(value: str) -> bool:
    return bool(FULL_POSTCODE_PATTERN.fullmatch(normalize_location_query(value)))


def looks_like_postcode_or_outcode(value: str) -> bool:
    return looks_like_outcode(value) or looks_like_full_postcode(value)


def fetch_postcode_location(postcode: str, timeout_seconds: int) -> tuple[float, float, str]:
    normalized_postcode = postcode.strip()
    if not normalized_postcode:
        raise ValueError("--postcode is required when geocoding for API mode")
    encoded_postcode = urllib.parse.quote(normalized_postcode)
    url = f"https://api.postcodes.io/postcodes/{encoded_postcode}"
    request = urllib.request.Request(url, headers={"User-Agent": "planning-lead-scout/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Postcodes.io request failed: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Postcodes.io returned invalid JSON: {exc}") from exc

    if not isinstance(payload, dict) or payload.get("status") != 200:
        raise RuntimeError("Postcodes.io did not return a successful result")
    result = payload.get("result")
    if not isinstance(result, dict):
        raise RuntimeError("Postcodes.io response missing result")
    latitude = result.get("latitude")
    longitude = result.get("longitude")
    if latitude is None or longitude is None:
        raise RuntimeError("Postcodes.io response missing latitude/longitude")
    return float(latitude), float(longitude), str(result.get("admin_district") or "")


def fetch_outcode_location(outcode: str, timeout_seconds: int) -> tuple[float, float, str]:
    normalized_outcode = normalize_location_query(outcode).replace(" ", "")
    if not normalized_outcode:
        raise ValueError("A postcode or outcode is required for live public planning data")
    encoded_outcode = urllib.parse.quote(normalized_outcode)
    url = f"https://api.postcodes.io/outcodes/{encoded_outcode}"
    request = urllib.request.Request(url, headers={"User-Agent": "planning-lead-scout/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Postcodes.io outcode request failed: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Postcodes.io outcode returned invalid JSON: {exc}") from exc

    if not isinstance(payload, dict) or payload.get("status") != 200:
        raise RuntimeError("Postcodes.io outcode did not return a successful result")
    result = payload.get("result")
    if not isinstance(result, dict):
        raise RuntimeError("Postcodes.io outcode response missing result")
    latitude = result.get("latitude")
    longitude = result.get("longitude")
    if latitude is None or longitude is None:
        raise RuntimeError("Postcodes.io outcode response missing latitude/longitude")
    return float(latitude), float(longitude), str(result.get("admin_district") or normalized_outcode)


def bbox_wkt_from_lat_lon(latitude: float, longitude: float, radius_km: float) -> str:
    if radius_km <= 0:
        raise ValueError("--radius-km must be greater than 0")
    delta_lat = radius_km / 111.32
    cos_latitude = math.cos(math.radians(latitude))
    safe_cos_latitude = max(abs(cos_latitude), 0.01)
    delta_lon = radius_km / (111.32 * safe_cos_latitude)
    south = latitude - delta_lat
    north = latitude + delta_lat
    west = longitude - delta_lon
    east = longitude + delta_lon
    return (
        "POLYGON (("
        f"{west:.6f} {south:.6f}, "
        f"{east:.6f} {south:.6f}, "
        f"{east:.6f} {north:.6f}, "
        f"{west:.6f} {north:.6f}, "
        f"{west:.6f} {south:.6f}"
        "))"
    )


def bbox_wkt_from_location_query(location_query: str, radius_km: float, timeout_seconds: int) -> tuple[str, str]:
    normalized_location_query = normalize_location_query(location_query)
    if not normalized_location_query:
        raise ValueError("A postcode or outcode is required for live public planning data")
    if looks_like_outcode(normalized_location_query):
        latitude, longitude, admin_district_or_outcode = fetch_outcode_location(
            normalized_location_query,
            timeout_seconds,
        )
    else:
        latitude, longitude, admin_district_or_outcode = fetch_postcode_location(
            normalized_location_query,
            timeout_seconds,
        )
    return (
        bbox_wkt_from_lat_lon(latitude, longitude, radius_km),
        admin_district_or_outcode,
    )


def fetch_planning_api_records(
    since: date,
    limit: int,
    geometry_wkt: str,
    timeout_seconds: int,
) -> list[dict[str, str]]:
    if limit <= 0:
        return []
    params = {
        "dataset": "planning-application",
        "start_date_year": str(since.year),
        "start_date_month": str(since.month),
        "start_date_day": str(since.day),
        "start_date_match": "since",
        "limit": str(limit),
        "offset": "0",
    }
    if geometry_wkt.strip():
        params["geometry"] = geometry_wkt.strip()
        params["geometry_relation"] = "intersects"
    query = urllib.parse.urlencode(params)
    url = f"https://www.planning.data.gov.uk/entity.json?{query}"
    request = urllib.request.Request(url, headers={"User-Agent": "planning-lead-scout/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Planning Data API request failed: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Planning Data API returned invalid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("Planning Data API returned an unexpected payload")
    return records_from_planning_response(payload)


def records_from_planning_response(payload: dict[str, object]) -> list[dict[str, str]]:
    entities = payload.get("entities")
    if entities is None:
        entities = payload.get("entity", [])
    if not isinstance(entities, list):
        raise ValueError("Planning Data API payload missing entities list")

    records: list[dict[str, str]] = []
    for item in entities:
        if not isinstance(item, dict):
            continue
        reference = item.get("reference") or item.get("entity") or ""
        records.append(
            {
                "reference": normalize_whitespace(reference),
                "area": normalize_whitespace(item.get("organisation-entity")),
                "site_address": normalize_whitespace(item.get("address-text")),
                "description": normalize_whitespace(item.get("description")),
                "status": normalize_whitespace(
                    item.get("planning-decision") or item.get("status")
                ),
                "application_type": normalize_whitespace(
                    item.get("development-classification")
                    or item.get("application-type")
                ),
                "validated_date": normalize_whitespace(
                    item.get("start-date") or item.get("entry-date")
                ),
                "decision_date": normalize_whitespace(item.get("decision-date")),
                "source_url": normalize_whitespace(
                    item.get("documentation-url") or item.get("endpoint")
                ),
            }
        )
    return records


def records_from_planning_fixture(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise SystemExit(f"API fixture not found: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"API fixture returned invalid JSON: {exc}")
    if not isinstance(payload, dict):
        raise SystemExit("API fixture must contain a JSON object")
    try:
        return records_from_planning_response(payload)
    except ValueError as exc:
        raise SystemExit(f"API fixture shape error: {exc}")


def trade_keywords(trade: str) -> list[str]:
    normalized_trade = trade.strip().lower()
    if normalized_trade in TRADE_KEYWORDS:
        return TRADE_KEYWORDS[normalized_trade]
    return [word for word in normalized_trade.split() if word]


def contains_term(text: str, term: str) -> bool:
    normalized_text = "".join(ch.lower() if ch.isalnum() else " " for ch in text)
    normalized_term = " ".join(term.lower().split())
    return f" {normalized_term} " in f" {' '.join(normalized_text.split())} "


def deterministic_outreach_message(record: dict[str, str], trade: str) -> str:
    return (
        f"Hi — I saw planning reference {record['reference']} for {record['site_address']}. "
        f"If {trade} work is part of this project, I can take a quick look and advise on next steps."
    )


def score_record(
    record: dict[str, str],
    trade: str,
    today: date,
    days: int,
    area_query: str,
) -> ScoredLead | None:
    normalized_area_query = area_query.strip().lower()
    area = record["area"]
    site_address = record["site_address"]
    if normalized_area_query:
        area_text = f"{area} {site_address}".lower()
        if normalized_area_query not in area_text:
            return None

    validated = parse_date(record["validated_date"])
    if validated is None:
        return None
    if days > 0:
        age_days = (today - validated).days
        if age_days < 0 or age_days > days:
            return None

    searchable_text = " ".join(
        [
            record["description"],
            record["status"],
            record["application_type"],
            record["site_address"],
        ]
    ).lower()
    matched_keywords = sorted(
        {
            keyword
            for keyword in trade_keywords(trade)
            if keyword and keyword in searchable_text
        }
    )
    matched_exclusions = sorted(
        {term for term in EXCLUSION_TERMS if contains_term(searchable_text, term)}
    )

    if "telecoms" in matched_exclusions and not matched_keywords:
        return None

    score = min(60, 15 * len(matched_keywords))
    status_text = record["status"].lower()
    application_type_text = record["application_type"].lower()

    status_notes: list[str] = []
    application_notes: list[str] = []
    penalty_notes: list[str] = []

    if "submitted" in status_text or "validated" in status_text:
        score += 15
        status_notes.append("submitted/validated status boost")
    if "approved" in status_text:
        score += 10
        status_notes.append("approved status boost")
    if "householder" in application_type_text:
        score += 10
        application_notes.append("householder application boost")
    if "extension" in application_type_text or "conversion" in application_type_text:
        score += 5
        application_notes.append("extension/conversion application boost")
    if matched_exclusions:
        score -= 40
        penalty_notes.append(
            "exclusion penalty for " + ", ".join(matched_exclusions)
        )
    if "refused" in status_text or "withdrawn" in status_text:
        score -= 10
        penalty_notes.append("refused/withdrawn status penalty")

    score = max(0, min(100, score))

    if matched_keywords:
        reason_parts = ["Matched keywords: " + ", ".join(matched_keywords)]
        reason_parts.extend(status_notes)
        reason_parts.extend(application_notes)
        reason_parts.extend(penalty_notes)
        reason = "; ".join(reason_parts) + "."
        outreach_keywords = ", ".join(matched_keywords[:3])
        suggested_outreach_angle = (
            f"Offer a {trade.strip()} quote around {outreach_keywords} work "
            f"for {site_address}."
        )
    else:
        reason = "No trade keywords matched; review manually."
        suggested_outreach_angle = (
            "Review manually before outreach; no clear trade match."
        )

    likely_trade_category = trade.strip().title() if score > 0 else "Manual review"

    return ScoredLead(
        score=score,
        rule_score=score,
        reference=record["reference"],
        area=area,
        site_address=site_address,
        description=record["description"],
        status=record["status"],
        application_type=record["application_type"],
        validated_date=record["validated_date"],
        decision_date=record["decision_date"],
        source_url=record["source_url"],
        likely_trade_category=likely_trade_category,
        matched_keywords=matched_keywords,
        reason=reason,
        suggested_outreach_angle=suggested_outreach_angle,
        llm_trade_fit="",
        llm_work_types=[],
        llm_value_signal="",
        llm_urgency="",
        llm_reason="",
        outreach_message=deterministic_outreach_message(record, trade.strip()),
        llm_confidence="",
        llm_model="",
        llm_error="",
    )


def parse_json_response(text: str) -> dict[str, Any]:
    content = text.strip()
    if content.startswith("```"):
        lines = content.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        content = "\n".join(lines).strip()
    try:
        parsed = json.loads(content)
        if isinstance(parsed, dict):
            return parsed
        raise ValueError("JSON response was not an object")
    except json.JSONDecodeError:
        start = content.find("{")
        end = content.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise
        parsed = json.loads(content[start : end + 1])
        if isinstance(parsed, dict):
            return parsed
        raise ValueError("JSON response was not an object")



def extract_gemini_rest_text(payload: dict[str, object]) -> str:
    candidates = payload.get("candidates")
    if isinstance(candidates, list) and candidates:
        first_candidate = candidates[0]
        if isinstance(first_candidate, dict):
            content = first_candidate.get("content")
            if isinstance(content, dict):
                parts = content.get("parts")
                if isinstance(parts, list) and parts:
                    first_part = parts[0]
                    if isinstance(first_part, dict):
                        text = first_part.get("text")
                        if isinstance(text, str) and text.strip():
                            return text
    raise ValueError("Gemini response missing generated text")


def owner_ai_insight_from_payload(payload: dict[str, Any], model: str) -> OwnerAiInsight:
    expected_fields = [
        "fit",
        "urgency",
        "why_it_matched",
        "suggested_next_action",
        "confidence",
    ]
    missing_fields = [field for field in expected_fields if field not in payload]

    fit = str(payload.get("fit") or "low").strip().lower()
    if fit not in OWNER_AI_FITS:
        missing_fields.append("fit")
        fit = "low"

    urgency = str(payload.get("urgency") or "monitor").strip().lower()
    if urgency not in OWNER_AI_URGENCIES:
        missing_fields.append("urgency")
        urgency = "monitor"

    why_it_matched = str(payload.get("why_it_matched") or "").strip()
    if not why_it_matched:
        missing_fields.append("why_it_matched")

    suggested_next_action = str(payload.get("suggested_next_action") or "").strip()
    if not suggested_next_action:
        missing_fields.append("suggested_next_action")

    try:
        confidence = float(payload.get("confidence", 0.0))
    except (TypeError, ValueError):
        missing_fields.append("confidence")
        confidence = 0.0
    if "confidence" not in payload:
        missing_fields.append("confidence")
    confidence = max(0.0, min(1.0, confidence))

    error = ""
    if missing_fields:
        error = "Missing or invalid AI fields: " + ", ".join(sorted(set(missing_fields)))

    return OwnerAiInsight(
        fit=fit,
        urgency=urgency,
        why_it_matched=why_it_matched,
        suggested_next_action=suggested_next_action,
        confidence=confidence,
        model=model,
        error=error,
    )

def lead_insight_from_payload(payload: dict[str, Any], model: str) -> LeadInsight:
    expected_fields = [
        "trade_fit",
        "work_types",
        "value_signal",
        "urgency",
        "reason",
        "outreach_message",
        "confidence",
    ]
    if not any(field in payload for field in expected_fields):
        for nested_key in ("LeadInsight", "lead_insight", "leadInsight", "insight"):
            nested_payload = payload.get(nested_key)
            if isinstance(nested_payload, dict):
                payload = nested_payload
                break
    field_aliases = {
        "trade_fit": ("tradeFit",),
        "work_types": ("workTypes",),
        "value_signal": ("valueSignal",),
        "outreach_message": ("outreachMessage",),
    }
    for canonical_field, aliases in field_aliases.items():
        if canonical_field in payload:
            continue
        for alias in aliases:
            if alias in payload:
                payload[canonical_field] = payload[alias]
                break
    missing_fields = [field for field in expected_fields if field not in payload]

    trade_fit = str(payload.get("trade_fit") or "low").strip().lower()
    if trade_fit not in TRADE_FITS:
        missing_fields.append("trade_fit")
        trade_fit = "low"

    raw_work_types = payload.get("work_types") or []
    if isinstance(raw_work_types, list):
        work_types = [str(item).strip() for item in raw_work_types if str(item).strip()]
    else:
        missing_fields.append("work_types")
        work_types = []

    value_signal = str(payload.get("value_signal") or "unknown").strip().lower()
    if value_signal not in VALUE_SIGNALS:
        missing_fields.append("value_signal")
        value_signal = "unknown"

    urgency = str(payload.get("urgency") or "monitor").strip().lower()
    if urgency not in URGENCY_VALUES:
        missing_fields.append("urgency")
        urgency = "monitor"

    try:
        confidence = float(payload.get("confidence", 0.0))
    except (TypeError, ValueError):
        missing_fields.append("confidence")
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))

    error = ""
    if missing_fields:
        error = "Missing or invalid Gemini fields: " + ", ".join(sorted(set(missing_fields)))

    return LeadInsight(
        trade_fit=trade_fit,
        work_types=work_types,
        value_signal=value_signal,
        urgency=urgency,
        reason=str(payload.get("reason") or "").strip(),
        outreach_message=str(payload.get("outreach_message") or "").strip(),
        confidence=confidence,
        model=model,
        error=error,
    )


def empty_insight(error: str = "") -> LeadInsight:
    return LeadInsight(
        trade_fit="",
        work_types=[],
        value_signal="",
        urgency="",
        reason="",
        outreach_message="",
        confidence=0.0,
        model="",
        error=error,
    )


def classify_with_gemini(
    record: dict[str, str],
    trade: str,
    api_key: str,
    model: str,
    timeout_seconds: int,
) -> LeadInsight:
    from google import genai  # type: ignore[import-not-found]
    from google.genai import types  # type: ignore[import-not-found]

    client = genai.Client(api_key=api_key)
    timeout_ms = timeout_seconds * 1000
    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        temperature=0,
        http_options=types.HttpOptions(timeout=timeout_ms),
    )
    prompt = {
        "instruction": (
            "classify a public UK planning application for a small trade business; "
            "use only `reference`, `site_address`, `description`, `status`, "
            "`application_type`, `validated_date`, `decision_date`, `source_url`, "
            "and target `trade`; do not mention applicant names; do not imply "
            "consent or an existing relationship; return JSON only with the "
            "`LeadInsight` fields."
        ),
        "target_trade": trade,
        "record": {field: record.get(field, "") for field in LLM_ALLOWED_FIELDS},
        "lead_insight_fields": {
            "trade_fit": "one of high, medium, low, none",
            "work_types": "array of short strings",
            "value_signal": "one of small, medium, large, unknown",
            "urgency": "one of now, soon, monitor, low",
            "reason": "max one sentence",
            "outreach_message": "max 280 chars, plain English, no pretending prior relationship, no email sending",
            "confidence": "number from 0.0 to 1.0",
            "model": model,
            "error": "blank unless there is a classification error",
        },
        "return_shape": {
            "trade_fit": "high|medium|low|none",
            "work_types": ["roofing"],
            "value_signal": "small|medium|large|unknown",
            "urgency": "now|soon|monitor|low",
            "reason": "one sentence",
            "outreach_message": "under 280 characters",
            "confidence": 0.0,
            "model": model,
            "error": "",
        },
    }
    response = client.models.generate_content(
        model=model,
        contents=json.dumps(prompt, ensure_ascii=False),
        config=config,
    )
    parsed = parse_json_response(getattr(response, "text", "") or "")
    insight = lead_insight_from_payload(parsed, model)
    if not insight.model:
        insight = replace(insight, model=model)
    return insight


def llm_adjustment(insight: LeadInsight) -> int:
    if insight.error or not insight.model:
        return 0
    adjustment = {
        "high": 15,
        "medium": 5,
        "low": -20,
        "none": -40,
    }.get(insight.trade_fit, 0)
    adjustment += {
        "now": 10,
        "soon": 5,
        "monitor": 0,
        "low": -10,
    }.get(insight.urgency, 0)
    return adjustment


def lead_record_for_llm(lead: ScoredLead) -> dict[str, str]:
    return {
        "reference": lead.reference,
        "site_address": lead.site_address,
        "description": lead.description,
        "status": lead.status,
        "application_type": lead.application_type,
        "validated_date": lead.validated_date,
        "decision_date": lead.decision_date,
        "source_url": lead.source_url,
    }


def classify_owner_lead_with_gemini_rest(
    lead: ScoredLead,
    trade: str,
    api_key: str,
    model: str = OWNER_AI_MODEL,
    timeout_seconds: int = 30,
) -> OwnerAiInsight:
    prompt = {
        "instruction": (
            "Classify one public UK planning application for a small trade business. "
            "Use only `reference`, `site_address`, `description`, `status`, "
            "`application_type`, `validated_date`, `decision_date`, `source_url`, "
            "and target `trade`. Do not mention applicant names. Do not imply "
            "consent or an existing relationship. Return JSON only."
        ),
        "target_trade": trade,
        "record": lead_record_for_llm(lead),
        "required_json_keys": [
            "fit",
            "urgency",
            "why_it_matched",
            "suggested_next_action",
            "confidence",
        ],
        "allowed_values": {
            "fit": ["high", "medium", "low", "not_relevant"],
            "urgency": ["now", "soon", "monitor", "ignore"],
        },
        "return_shape": {
            "fit": "high|medium|low|not_relevant",
            "urgency": "now|soon|monitor|ignore",
            "why_it_matched": "one short sentence about trade fit only",
            "suggested_next_action": "one safe next step; do not claim consent or relationship",
            "confidence": 0.0,
        },
    }
    prompt_text = json.dumps(prompt, ensure_ascii=False)
    body = {
        "contents": [{"parts": [{"text": prompt_text}]}],
        "generationConfig": {"temperature": 0, "responseMimeType": "application/json"},
    }
    request = urllib.request.Request(
        OWNER_AI_ENDPOINT_TEMPLATE.format(model=urllib.parse.quote(model, safe="-_.~")),
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": api_key,
            "User-Agent": "planning-lead-scout/1.0",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Owner AI request failed: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Owner AI returned invalid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("Owner AI returned an unexpected payload")
    generated_text = extract_gemini_rest_text(payload)
    parsed = parse_json_response(generated_text)
    return owner_ai_insight_from_payload(parsed, model)


def apply_insight(lead: ScoredLead, insight: LeadInsight) -> ScoredLead:
    adjusted_score = max(0, min(100, lead.rule_score + llm_adjustment(insight)))
    confidence = "" if not insight.model else f"{insight.confidence:.2f}"
    outreach_message = insight.outreach_message or lead.outreach_message
    return replace(
        lead,
        score=adjusted_score,
        llm_trade_fit=insight.trade_fit,
        llm_work_types=insight.work_types,
        llm_value_signal=insight.value_signal,
        llm_urgency=insight.urgency,
        llm_reason=insight.reason,
        outreach_message=outreach_message,
        llm_confidence=confidence,
        llm_model=insight.model,
        llm_error=insight.error,
    )


def enrich_leads_with_gemini(
    leads: list[ScoredLead],
    trade: str,
    mode: str,
    model: str,
    max_records: int,
    timeout_seconds: int,
) -> list[ScoredLead]:
    if mode == "off":
        return leads

    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        if mode == "require":
            raise SystemExit("GEMINI_API_KEY is required for --llm-mode require")
        print("Skipping Gemini enrichment: GEMINI_API_KEY is not set", file=sys.stderr)
        return leads

    try:
        from google import genai as _genai  # noqa: F401  # type: ignore[import-not-found]
        from google.genai import types as _types  # noqa: F401  # type: ignore[import-not-found]
    except ImportError as exc:
        if mode == "require":
            raise SystemExit("google-genai is required for --llm-mode require") from exc
        print("Skipping Gemini enrichment: google-genai is not installed", file=sys.stderr)
        return leads

    if not leads or max_records <= 0:
        return leads

    enriched: list[ScoredLead] = []
    for index, lead in enumerate(leads):
        if index >= max_records:
            enriched.append(lead)
            continue
        try:
            insight = classify_with_gemini(
                record=lead_record_for_llm(lead),
                trade=trade,
                api_key=api_key,
                model=model,
                timeout_seconds=timeout_seconds,
            )
            if mode == "require" and insight.error:
                raise RuntimeError(insight.error)
        except Exception as exc:
            if mode == "require":
                raise SystemExit(f"Gemini enrichment failed: {exc}") from exc
            insight = empty_insight(f"Gemini enrichment failed: {exc}")
        enriched.append(apply_insight(lead, insight))
    return enriched


def write_leads(leads: list[ScoredLead], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        for rank, lead in enumerate(leads, start=1):
            writer.writerow(
                {
                    "rank": rank,
                    "score": lead.score,
                    "rule_score": lead.rule_score,
                    "reference": lead.reference,
                    "area": lead.area,
                    "site_address": lead.site_address,
                    "description": lead.description,
                    "status": lead.status,
                    "application_type": lead.application_type,
                    "validated_date": lead.validated_date,
                    "decision_date": lead.decision_date,
                    "likely_trade_category": lead.likely_trade_category,
                    "matched_keywords": ";".join(lead.matched_keywords),
                    "reason": lead.reason,
                    "suggested_outreach_angle": lead.suggested_outreach_angle,
                    "llm_trade_fit": lead.llm_trade_fit,
                    "llm_work_types": ";".join(lead.llm_work_types),
                    "llm_value_signal": lead.llm_value_signal,
                    "llm_urgency": lead.llm_urgency,
                    "llm_reason": lead.llm_reason,
                    "outreach_message": lead.outreach_message,
                    "llm_confidence": lead.llm_confidence,
                    "llm_model": lead.llm_model,
                    "llm_error": lead.llm_error,
                    "source_url": lead.source_url,
                }
            )


def sorted_leads(leads: list[ScoredLead]) -> list[ScoredLead]:
    return sorted(
        leads,
        key=lambda lead: (
            -lead.score,
            -(parse_date(lead.validated_date) or date.min).toordinal(),
            lead.reference,
        ),
    )


def load_owner_ai_fixture(path: Path) -> dict[str, OwnerAiInsight]:
    if not path.exists():
        raise SystemExit(f"Owner AI fixture not found: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Owner AI fixture returned invalid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise SystemExit("Owner AI fixture must contain a JSON object")
    insights: dict[str, OwnerAiInsight] = {}
    for reference, raw_insight in payload.items():
        if not isinstance(raw_insight, dict):
            raw_insight = {}
        insights[str(reference)] = owner_ai_insight_from_payload(raw_insight, "fixture")
    return insights


def owner_ai_score_adjustment(insight: OwnerAiInsight) -> int:
    adjustment = {
        "high": 20,
        "medium": 8,
        "low": -20,
        "not_relevant": -100,
    }.get(insight.fit, 0)
    adjustment += {
        "now": 10,
        "soon": 5,
        "monitor": 0,
        "ignore": -30,
    }.get(insight.urgency, 0)
    return adjustment


def rank_owner_leads_with_ai(
    leads: list[ScoredLead],
    trade: str,
    api_key: str,
    model: str = OWNER_AI_MODEL,
    timeout_seconds: int = 30,
    fixture_path: Path | None = None,
    max_records: int = 12,
) -> list[OwnerRankedLead]:
    if max_records <= 0:
        return []
    if fixture_path is None and not api_key.strip():
        raise SystemExit("AI key is required for owner lead scoring")

    fixture = load_owner_ai_fixture(fixture_path) if fixture_path is not None else None
    selected_leads = sorted(
        leads,
        key=lambda lead: (
            -lead.rule_score,
            -(parse_date(lead.validated_date) or date.min).toordinal(),
            lead.reference,
        ),
    )[:max_records]
    ranked_leads: list[OwnerRankedLead] = []
    for lead in selected_leads:
        if fixture is not None:
            insight = fixture.get(
                lead.reference,
                OwnerAiInsight(
                    fit="low",
                    urgency="monitor",
                    why_it_matched="",
                    suggested_next_action="",
                    confidence=0.0,
                    model="fixture",
                    error="Missing or invalid AI fields: reference",
                ),
            )
        else:
            try:
                insight = classify_owner_lead_with_gemini_rest(
                    lead=lead,
                    trade=trade,
                    api_key=api_key.strip(),
                    model=model,
                    timeout_seconds=timeout_seconds,
                )
            except Exception as exc:
                insight = OwnerAiInsight(
                    fit="low",
                    urgency="monitor",
                    why_it_matched="",
                    suggested_next_action="",
                    confidence=0.0,
                    model=model,
                    error=f"Owner AI scoring failed: {exc}",
                )
        if insight.error or insight.fit == "not_relevant":
            continue
        owner_score = max(0, min(100, lead.rule_score + owner_ai_score_adjustment(insight)))
        ranked_leads.append(
            OwnerRankedLead(lead=lead, insight=insight, owner_score=owner_score)
        )
    return sorted(
        ranked_leads,
        key=lambda ranked: (
            -ranked.owner_score,
            -(parse_date(ranked.lead.validated_date) or date.min).toordinal(),
            ranked.lead.reference,
        ),
    )


def owner_fit_label(fit: str) -> str:
    return {
        "high": "High",
        "medium": "Medium",
        "low": "Low",
    }.get(fit, "Manual review")


def owner_rows_from_ranked_leads(ranked_leads: list[OwnerRankedLead], limit: int = 8) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for rank, ranked in enumerate(ranked_leads[:limit], start=1):
        if (
            ranked.insight.error
            or ranked.insight.fit not in OWNER_AI_FITS
            or ranked.insight.fit == "not_relevant"
            or not ranked.insight.why_it_matched.strip()
            or not ranked.insight.suggested_next_action.strip()
        ):
            continue
        rows.append(
            {
                "rank": str(rank),
                "address": ranked.lead.site_address,
                "planning_reference": ranked.lead.reference,
                "fit": owner_fit_label(ranked.insight.fit),
                "fit_score": str(ranked.owner_score),
                "why_it_matched": ranked.insight.why_it_matched,
                "suggested_next_action": ranked.insight.suggested_next_action,
                "planning_link": ranked.lead.source_url,
            }
        )
    return rows


def write_owner_shortlist(ranked_leads: list[OwnerRankedLead], output: Path, limit: int = 8) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=OWNER_OUTPUT_COLUMNS)
        writer.writeheader()
        for row in owner_rows_from_ranked_leads(ranked_leads, limit=limit):
            writer.writerow(row)


def find_leads(options: LeadSearchOptions) -> list[ScoredLead]:
    today = options.today or date.today()
    load_env_file(options.env_file)
    gemini_model = (
        options.gemini_model.strip()
        or os.environ.get("GEMINI_MODEL", "").strip()
        or OWNER_AI_MODEL
    )

    if options.source == "csv":
        records = load_records(options.input_path)
    elif options.source == "api":
        if options.api_fixture_path is not None:
            records = records_from_planning_fixture(options.api_fixture_path)
        else:
            geometry_wkt = options.geometry_wkt.strip()
            if not geometry_wkt and options.postcode.strip():
                try:
                    geometry_wkt, _admin_district_or_outcode = bbox_wkt_from_location_query(
                        options.postcode,
                        options.radius_km,
                        options.api_timeout,
                    )
                except Exception as exc:
                    raise SystemExit(f"Postcode lookup failed: {exc}") from exc
            since = today - timedelta(days=options.days) if options.days > 0 else date.min
            try:
                records = fetch_planning_api_records(
                    since=since,
                    limit=options.planning_limit,
                    geometry_wkt=geometry_wkt,
                    timeout_seconds=options.api_timeout,
                )
            except Exception as exc:
                raise SystemExit(f"Planning Data API failed: {exc}") from exc
    else:
        raise SystemExit(f"Unsupported source: {options.source}")

    leads = [
        lead
        for record in records
        if (
            lead := score_record(
                record=record,
                trade=options.trade,
                today=today,
                days=options.days,
                area_query=options.area,
            )
        )
        is not None
        and lead.score >= options.min_score
    ]
    leads = sorted_leads(leads)
    leads = enrich_leads_with_gemini(
        leads=leads,
        trade=options.trade,
        mode=options.llm_mode,
        model=gemini_model,
        max_records=options.max_llm_records,
        timeout_seconds=options.api_timeout,
    )
    return sorted_leads(leads)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", choices=["csv", "api"], default="csv")
    parser.add_argument("--input", default="data/sample_input.txt")
    parser.add_argument("--output", default="output/sample_output.csv")
    parser.add_argument("--area", default="")
    parser.add_argument("--area-file", default=None)
    parser.add_argument("--trade", default="roofer")
    parser.add_argument("--trade-file", default=None)
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--days-file", default=None)
    parser.add_argument("--today", default="")
    parser.add_argument("--min-score", type=int, default=0)
    parser.add_argument("--postcode", default="")
    parser.add_argument("--radius-km", type=float, default=5.0)
    parser.add_argument("--geometry-wkt", default="")
    parser.add_argument("--planning-limit", type=int, default=100)
    parser.add_argument("--api-timeout", type=int, default=30)
    parser.add_argument("--api-fixture", default="")
    parser.add_argument("--llm-mode", choices=["off", "auto", "require"], default="auto")
    parser.add_argument("--gemini-model", default="")
    parser.add_argument("--env-file", default="")
    parser.add_argument("--max-llm-records", type=int, default=10)
    args = parser.parse_args()

    area_value = None if args.area_file is not None and args.area == "" else args.area
    trade_value = None if args.trade_file is not None and args.trade == "roofer" else args.trade
    area = read_text_arg(area_value, args.area_file, "")
    trade = read_text_arg(trade_value, args.trade_file, "roofer")

    if args.days_file is not None and args.days == 30:
        days_text = read_text_arg(None, args.days_file, "30")
        try:
            days = int(days_text)
        except ValueError:
            raise SystemExit(f"Invalid --days value: {days_text}")
    else:
        days = args.days

    today: date | None = None
    if args.today.strip():
        today = parse_date(args.today)
        if today is None:
            raise SystemExit(f"Invalid --today value: {args.today}")

    leads = find_leads(
        LeadSearchOptions(
            source=args.source,
            input_path=Path(args.input),
            area=area,
            trade=trade,
            days=days,
            today=today,
            min_score=args.min_score,
            postcode=args.postcode,
            radius_km=args.radius_km,
            geometry_wkt=args.geometry_wkt,
            planning_limit=args.planning_limit,
            api_timeout=args.api_timeout,
            api_fixture_path=Path(args.api_fixture) if args.api_fixture.strip() else None,
            llm_mode=args.llm_mode,
            gemini_model=args.gemini_model,
            env_file=args.env_file,
            max_llm_records=args.max_llm_records,
        )
    )

    output = Path(args.output)
    write_leads(leads, output)
    print(f"Wrote {output} ({len(leads)} leads)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
