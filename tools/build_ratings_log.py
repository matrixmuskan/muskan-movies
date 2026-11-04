#!/usr/bin/env python3
"""Rebuild data/ratings-log.json from a dump of the private feedback files.

Input: a JSON array of feedback file bodies ({id, action, rating, timestamp}),
or of {"path": ..., "body": {...}} objects. The newest file per id wins.
Genres and lessons for titles already in the log are kept; new titles get
genres from NOTES below or an empty list, and a default lesson.

Usage: build_ratings_log.py <feedback-dump.json>
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PICKS = ROOT / "data" / "picks.json"
LOG = ROOT / "data" / "ratings-log.json"

NOTES = {
    "dupahiya-season-2": (
        ["comedy", "slice-of-life", "rustic/small-town (TVF, Panchayat-style)"],
        "Village comedy in the Panchayat mould keeps landing; a second season is no barrier.",
    ),
    "taskaree": (
        ["thriller", "crime", "scam/fraud ring/pills/smuggling", "cop/investigation"],
        "Customs and smuggling thrillers work; keep the scam/smuggling theme high.",
    ),
    "matka-king": (
        ["crime", "drama", "scam/fraud ring/pills/smuggling"],
        "Period crime about gambling rackets lands even when critics are mixed; trust the theme over the review.",
    ),
    "hello-bachhon": (
        ["drama", "study/college/coaching life", "TVF production"],
        "TVF study-life shows are a safe bet, as Kota Factory and Aspirants suggested.",
    ),
    "forgotten-island": (
        ["animation (family)", "adventure", "English (Hollywood)"],
        "Skip animated films unless they are Inside Out-level blockbusters; good reviews alone are not enough.",
    ),
    "shaun-the-sheep-beast-of-mossy-bottom": (
        ["animation (family)", "comedy", "English (Hollywood)"],
        "No cartoons: even a well-reviewed family animation was discarded.",
    ),
}


def bucket(action: str, stars: int | None) -> str | None:
    if action == "keep" or (action == "rate" and stars is not None and stars >= 4):
        return "loved"
    if action == "discard" or (action == "rate" and stars is not None and stars <= 2):
        return "disliked"
    if action == "rate" and stars == 3:
        return "neutral"
    return None


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: build_ratings_log.py <feedback-dump.json>")
    raw = json.loads(Path(sys.argv[1]).read_text())
    bodies = [item.get("body", item) for item in raw]
    picks = {p["id"]: p for p in json.loads(PICKS.read_text())}
    previous = {}
    if LOG.exists():
        old = json.loads(LOG.read_text())
        for name in ("loved", "neutral", "disliked"):
            for entry in old.get(name, []):
                previous[entry["id"]] = entry

    latest: dict[str, dict] = {}
    for body in bodies:
        if body.get("id") not in picks:
            continue
        current = latest.get(body["id"])
        if current is None or body["timestamp"] >= current["timestamp"]:
            latest[body["id"]] = body

    log = {
        "version": 1,
        "updated": date.today().isoformat(),
        "source": "matrixmuskan/muskan-movies-feedback/feedback/",
        "rules": {"loved": "4-5 stars or keep", "neutral": "3 stars", "disliked": "1-2 stars or discard"},
        "loved": [],
        "neutral": [],
        "disliked": [],
    }
    for pick_id, body in sorted(latest.items(), key=lambda kv: kv[1]["timestamp"], reverse=True):
        stars = body.get("rating") if body.get("action") == "rate" else None
        name = bucket(body["action"], stars)
        if not name:
            continue
        pick = picks[pick_id]
        genres, lesson = NOTES.get(pick_id, ([], "Weigh this title's tags by the action above."))
        before = previous.get(pick_id, {})
        log[name].append({
            "title": pick["title"],
            "id": pick_id,
            "type": pick["type"],
            "language": pick["language"],
            "genres": before.get("genres") or genres,
            "action": body["action"],
            "stars": stars,
            "date": body["timestamp"],
            "endorsers": [e["name"] for e in pick.get("endorsements", [])],
            "lesson": before.get("lesson") or lesson,
        })
    LOG.write_text(json.dumps(log, ensure_ascii=False, indent=2) + "\n")
    print(f"ratings-log: {len(log['loved'])} loved, {len(log['neutral'])} neutral, {len(log['disliked'])} disliked")


if __name__ == "__main__":
    main()
