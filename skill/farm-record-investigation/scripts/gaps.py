#!/usr/bin/env python3
"""Find missing records before a symptom. Stdlib only.

Usage: python scripts/gaps.py examples/sample_farm.csv --symptom-date 2026-03-12 [--window 14]
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from timeline import load_events, timeline, window_bounds  # noqa: E402

TRACKED_TYPES = ("irrigation", "fertilizer", "weather")
QUANTITY_TYPES = ("irrigation", "fertilizer", "pesticide")


def longest_gap_days(items: list[dict[str, Any]], type_: str, start: date, end: date) -> int:
    """Longest stretch in [start, end] without a record of type_."""
    dates = sorted({e["date"] for e in items if e["type"] == type_})
    points = [start, *dates, end]
    return max((b - a).days for a, b in zip(points, points[1:]))


def find_gaps(
    events: list[dict[str, Any]], symptom_date: date, window_days: int = 14, field: str | None = None
) -> dict[str, Any]:
    start, end = window_bounds(symptom_date, window_days)
    in_window = timeline(events, start, end, field)
    present = {e["type"] for e in in_window}
    scoped = [e for e in events if field is None or e["field"] == field]
    return {
        "window": {"start": start.isoformat(), "end": end.isoformat(), "days": window_days},
        "missing_types": [t for t in TRACKED_TYPES if t not in present],
        "longest_irrigation_gap_days": longest_gap_days(in_window, "irrigation", start, end),
        "null_quantity_events": [
            e["event_id"] for e in in_window if e["type"] in QUANTITY_TYPES and e["quantity"] is None
        ],
        "unknown_date_events": [
            e["event_id"] for e in scoped if e["date"] is None or e["date_certainty"] == "unknown"
        ],
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Missing records before a symptom.")
    p.add_argument("csv")
    p.add_argument("--symptom-date", required=True)
    p.add_argument("--window", type=int, default=14)
    p.add_argument("--field")
    a = p.parse_args(argv)
    report = find_gaps(load_events(a.csv), date.fromisoformat(a.symptom_date), a.window, a.field)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())