#!/usr/bin/env python3
"""Append one feedback issue to data/feedback.json.

The site opens a GitHub issue titled "feedback: <id>" whose body contains:

    ```json
    {"id": "...", "action": "keep|discard|rate", "rating": null, "timestamp": "..."}
    ```

Run from a workflow with GITHUB_EVENT_PATH set to the issues event. Recording the
same issue number twice is a no-op so a re-run cannot duplicate a row.
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA = ROOT / "data" / "feedback.json"
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,80}$")
ACTIONS = {"keep", "discard", "rate"}
FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def fail(message: str) -> None:
    raise SystemExit(message)


def parse_timestamp(value: object) -> str:
    if not isinstance(value, str) or not value:
        fail("timestamp must be an ISO-8601 string")
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        datetime.fromisoformat(text)
    except ValueError:
        fail("timestamp is not ISO-8601")
    return value


def rating_value(action: str, value: object) -> int | None:
    if isinstance(value, bool) or (value is not None and not isinstance(value, int)):
        fail("rating must be an integer from 1 to 5, or null")
    if action == "rate":
        if value is None or not 1 <= value <= 5:
            fail("a rate action needs a rating from 1 to 5")
        return value
    if value is not None:
        fail("rating is only set for a rate action")
    return None


def extract_payload(body: str) -> dict:
    if len(body) > 20000:
        fail("issue body is too large")
    fenced = FENCE_RE.search(body)
    raw = fenced.group(1) if fenced else ""
    if not raw:
        start = body.find("{")
        end = body.rfind("}")
        if start == -1 or end <= start:
            fail("no JSON object in issue body")
        raw = body[start : end + 1]
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        fail("feedback JSON could not be parsed")
    if not isinstance(payload, dict):
        fail("feedback JSON must be an object")
    return payload


def load_doc(path: Path) -> dict:
    if not path.exists():
        return {"entries": []}
    try:
        doc = json.loads(path.read_text())
    except json.JSONDecodeError:
        fail(f"{path} is not valid JSON")
    if not isinstance(doc, dict) or not isinstance(doc.get("entries"), list):
        fail(f"{path} must be an object with an entries array")
    return doc


def record(body: str, number: int, title: str, path: Path) -> bool:
    """Append the issue. Return False when that issue number is already stored."""
    if number < 1:
        fail("issue number must be positive")
    payload = extract_payload(body)
    pick_id = payload.get("id")
    action = payload.get("action")
    if not isinstance(pick_id, str) or not ID_RE.fullmatch(pick_id):
        fail("id must be a lowercase slug")
    if not isinstance(action, str) or action not in ACTIONS:
        fail("action must be keep, discard, or rate")
    if title != f"feedback: {pick_id}":
        fail("issue title must be 'feedback: <id>' and match the JSON id")
    entry = {
        "id": pick_id,
        "action": action,
        "rating": rating_value(action, payload.get("rating")),
        "timestamp": parse_timestamp(payload.get("timestamp")),
        "issue": number,
    }
    doc = load_doc(path)
    if any(isinstance(item, dict) and item.get("issue") == number for item in doc["entries"]):
        return False
    doc["entries"].append(entry)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2) + "\n")
    return True


def main() -> None:
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    if not event_path:
        fail("GITHUB_EVENT_PATH is not set")
    event = json.loads(Path(event_path).read_text())
    issue = event.get("issue") or {}
    data_path = Path(os.environ.get("FEEDBACK_PATH", DEFAULT_DATA))
    changed = record(issue.get("body") or "", int(issue["number"]), issue.get("title") or "", data_path)
    print("recorded" if changed else "already recorded")


if __name__ == "__main__":
    main()
