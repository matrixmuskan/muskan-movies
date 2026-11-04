#!/usr/bin/env python3
"""Check the picks file, the feedback file, and that the site embeds no token."""

from __future__ import annotations

import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,80}$")
PICK_FIELDS = {
    "id",
    "title",
    "year",
    "type",
    "language",
    "imdb_rating",
    "hook",
    "where_to_watch",
    "trailer_url",
    "poster_url",
    "kid_safe",
    "week",
    "source",
    "status",
    "example",
    "imdb_id",
    "imdb_url",
}
STATUSES = {"new", "kept", "discarded", "seen"}
TYPES = {"movie", "series"}
SECRET_MARKERS = (
    "gh" + "p_",
    "github_" + "pat_",
    "AK" + "IA",
    "xox" + "b-",
    "xox" + "p-",
    "googletag" + "manager",
    "google-" + "analytics",
)
TEXT_SUFFIXES = {".html", ".css", ".js", ".json", ".md", ".yml", ".py", ".svg"}

errors: list[str] = []


def error(message: str) -> None:
    errors.append(message)


def load(path: Path) -> object:
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        error(f"{path.relative_to(ROOT)} is not valid JSON ({exc})")
        return None


def https_url(value: object, label: str) -> None:
    if not isinstance(value, str) or not value.startswith("https://") or " " in value:
        error(f"{label} must be an https URL")


def check_pick(index: int, pick: object, seen_ids: set[str]) -> None:
    label = f"picks[{index}]"
    if not isinstance(pick, dict):
        error(f"{label} must be an object")
        return
    extra = set(pick) - PICK_FIELDS
    if extra:
        error(f"{label} has unknown fields: {', '.join(sorted(extra))}")
    pick_id = pick.get("id")
    if not isinstance(pick_id, str) or not ID_RE.fullmatch(pick_id):
        error(f"{label}.id must be a lowercase slug")
    elif pick_id in seen_ids:
        error(f"{label}.id {pick_id} is duplicated")
    else:
        seen_ids.add(pick_id)
    if not isinstance(pick.get("title"), str) or not pick["title"].strip():
        error(f"{label}.title must be a non-empty string")
    year = pick.get("year")
    if isinstance(year, bool) or not isinstance(year, int) or not 1888 <= year <= 2100:
        error(f"{label}.year must be a year")
    if pick.get("type") not in TYPES:
        error(f"{label}.type must be movie or series")
    if not isinstance(pick.get("language"), str) or not pick["language"].strip():
        error(f"{label}.language must be a non-empty string")
    rating = pick.get("imdb_rating")
    if rating is not None and (isinstance(rating, bool) or not isinstance(rating, (int, float)) or not 0 <= float(rating) <= 10):
        error(f"{label}.imdb_rating must be a number from 0 to 10, or null")
    if not isinstance(pick.get("hook"), str) or not pick["hook"].strip() or len(pick["hook"]) > 240:
        error(f"{label}.hook must be a short non-empty string")
    if not isinstance(pick.get("where_to_watch"), str) or not pick["where_to_watch"].strip():
        error(f"{label}.where_to_watch must be a non-empty string")
    https_url(pick.get("trailer_url"), f"{label}.trailer_url")
    https_url(pick.get("poster_url"), f"{label}.poster_url")
    if not isinstance(pick.get("kid_safe"), bool):
        error(f"{label}.kid_safe must be true or false")
    week = pick.get("week")
    if not isinstance(week, str):
        error(f"{label}.week must be a Friday in YYYY-MM-DD")
    else:
        try:
            year_s, month_s, day_s = week.split("-")
            found = date(int(year_s), int(month_s), int(day_s))
            if found.isoformat() != week or found.weekday() != 4:
                error(f"{label}.week {week} must be the Friday of that week")
        except ValueError:
            error(f"{label}.week {week} must be the Friday of that week")
    if not isinstance(pick.get("source"), str) or not pick["source"].strip():
        error(f"{label}.source must be a non-empty string")
    if pick.get("status") not in STATUSES:
        error(f"{label}.status must be new, kept, discarded, or seen")
    if "example" in pick and not isinstance(pick["example"], bool):
        error(f"{label}.example must be true or false when present")
    imdb_id = pick.get("imdb_id")
    if imdb_id is not None and (not isinstance(imdb_id, str) or not re.fullmatch(r"tt\d{5,12}", imdb_id)):
        error(f"{label}.imdb_id must look like tt1234567 when present")
    if "imdb_url" in pick:
        https_url(pick.get("imdb_url"), f"{label}.imdb_url")


def check_feedback_wiring() -> None:
    config = ROOT / "assets" / "js" / "config.js"
    app_js = ROOT / "assets" / "js" / "app.js"
    if not config.is_file():
        error("assets/js/config.js is missing")
    else:
        text = config.read_text()
        if text.count("__MOVIES_FEEDBACK_TOKEN__") != 1:
            error("assets/js/config.js must contain exactly one token placeholder")
    if app_js.is_file() and "issues/new" in app_js.read_text():
        error("assets/js/app.js still opens a GitHub issue")
    if (ROOT / ".github" / "workflows" / "feedback.yml").exists():
        error("the issue-recording workflow should be removed")
    if (ROOT / "data" / "feedback.json").exists():
        error("viewer feedback no longer lives in data/feedback.json")


def check_secrets() -> None:
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.suffix not in TEXT_SUFFIXES:
            continue
        rel = path.relative_to(ROOT)
        if ".git" in rel.parts or "_site" in rel.parts:
            continue
        text = path.read_text(errors="ignore")
        for marker in SECRET_MARKERS:
            if marker in text:
                error(f"{path.relative_to(ROOT)} contains {marker}")


def main() -> None:
    picks_path = ROOT / "data" / "picks.json"
    picks_doc = load(picks_path)
    picks = None
    if isinstance(picks_doc, list):
        picks = picks_doc
    elif isinstance(picks_doc, dict) and isinstance(picks_doc.get("picks"), list):
        picks = picks_doc["picks"]
    if picks is None:
        error("data/picks.json must be an array of picks")
    else:
        seen_ids: set[str] = set()
        for index, pick in enumerate(picks):
            check_pick(index, pick, seen_ids)
    check_feedback_wiring()
    check_secrets()
    if errors:
        print("\n".join(errors))
        sys.exit(1)
    print(f"ok {len(picks)} picks")


if __name__ == "__main__":
    main()
