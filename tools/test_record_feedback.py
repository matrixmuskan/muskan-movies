#!/usr/bin/env python3
"""Recorder checks. Uses a temporary feedback file, never data/feedback.json."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import record_feedback  # noqa: E402


def body_for(payload: dict) -> str:
    return "Feedback from the picks site.\n\n```json\n" + json.dumps(payload, indent=2) + "\n```\n"


def payload(action: str = "keep", rating: object = None, pick_id: str = "andhadhun-2018") -> dict:
    return {
        "id": pick_id,
        "action": action,
        "rating": rating,
        "timestamp": "2026-11-04T21:40:00.000Z",
    }


def expect_ok(name: str, fn) -> None:
    try:
        fn()
    except SystemExit as exc:
        raise AssertionError(f"{name} failed: {exc}") from exc
    print("ok", name)


def expect_fail(name: str, fn) -> None:
    try:
        fn()
    except SystemExit:
        print("ok", name)
        return
    raise AssertionError(f"{name} should have failed")


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "feedback.json"

        def keep() -> None:
            changed = record_feedback.record(
                body_for(payload()),
                12,
                "feedback: andhadhun-2018",
                path,
            )
            assert changed is True
            doc = json.loads(path.read_text())
            assert doc["entries"][0]["action"] == "keep"
            assert doc["entries"][0]["rating"] is None
            assert doc["entries"][0]["issue"] == 12

        expect_ok("keep appends one row", keep)

        def duplicate() -> None:
            changed = record_feedback.record(
                body_for(payload()),
                12,
                "feedback: andhadhun-2018",
                path,
            )
            assert changed is False
            assert len(json.loads(path.read_text())["entries"]) == 1

        expect_ok("same issue is idempotent", duplicate)

        def rate() -> None:
            changed = record_feedback.record(
                body_for(payload("rate", 4, "jailer-2023")),
                13,
                "feedback: jailer-2023",
                path,
            )
            assert changed is True
            rows = json.loads(path.read_text())["entries"]
            assert rows[-1]["rating"] == 4
            assert len(rows) == 2

        expect_ok("rate stores the stars", rate)

        expect_fail(
            "rate without stars",
            lambda: record_feedback.record(
                body_for(payload("rate", None, "jailer-2023")),
                14,
                "feedback: jailer-2023",
                path,
            ),
        )
        expect_fail(
            "keep cannot carry a rating",
            lambda: record_feedback.record(
                body_for(payload("keep", 4)),
                15,
                "feedback: andhadhun-2018",
                path,
            ),
        )
        expect_fail(
            "title must match id",
            lambda: record_feedback.record(
                body_for(payload()),
                16,
                "feedback: other",
                path,
            ),
        )
        expect_fail(
            "id must be a slug",
            lambda: record_feedback.record(
                body_for(payload(pick_id="Andhadhun")),
                17,
                "feedback: Andhadhun",
                path,
            ),
        )
        expect_fail(
            "missing JSON",
            lambda: record_feedback.record("no payload", 18, "feedback: andhadhun-2018", path),
        )
        assert len(json.loads(path.read_text())["entries"]) == 2

    print("recorder checks passed")


if __name__ == "__main__":
    main()
