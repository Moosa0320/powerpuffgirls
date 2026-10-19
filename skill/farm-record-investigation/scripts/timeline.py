#!/usr/bin/env python3
"""Build a chronological timeline from a farm-record CSV. Stdlib only, usable without the app.

Usage: python scripts/timeline.py examples/sample_farm.csv [--symptom-date 2026-03-12 --window 14]
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import date, timedelta
from typing import Any


def _opt(row: dict[str, str], key: str) -> str | None:
    value = (row.get(key) or "").strip()
    return value or None


def load_events(csv_path: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    with open(csv_path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            raw_date, qty = _opt(row, "date"), _opt(row, "quantity")
            events.append({
                "event_id": row["event_id"].strip(),
                "field": _opt(row, "field"),
                "type": row["type"].strip(),
                "date": date.fromisoformat(raw_date) if raw_date else None,
                "date_certainty": _opt(row, "date_certainty") or ("exact" if raw_date else "unknown"),
                "product": _opt(row, "product"),
                "quantity": float(qty) if qty else None,
                "unit": _opt(row, "unit"),
                "symptom": _opt(row, "symptom"),
                "source": _opt(row, "source") or "farmer_text",
            })
    return events


def window_bounds(symptom_date: date, window_days: int) -> tuple[date, date]:
    return symptom_date - timedelta(days=window_days), symptom_date


def timeline(
    events: list[dict[str, Any]], start: date | None = None, end: date | None = None,
    field: str | None = None,
) -> list[dict[str, Any]]:
    """Dated events in [start, end], sorted by date then ID. Undated events are excluded."""
    selected = [
        e for e in events
        if e["date"] is not None
        and (start is None or e["date"] >= start)
        and (end is None or e["date"] <= end)
        and (field is None or e["field"] == field)
    ]
    return sorted(selected, key=lambda e: (e["date"], e["event_id"]))


def to_jsonable(e: dict[str, Any]) -> dict[str, Any]:
    return {**e, "date": e["date"].isoformat() if e["date"] else None}


def format_line(e: dict[str, Any]) -> str:
    parts = [e["date"].isoformat(), e["event_id"], e["type"]]
    if e["product"]:
        parts.append(e["product"])
    if e["quantity"] is not None:
        parts.append(f"{e['quantity']:g} {e['unit'] or ''}".strip())
    if e["symptom"]:
        parts.append(f'symptom="{e["symptom"]}"')
    parts.append(f"[{e['date_certainty']}]")
    return "  ".join(parts)


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description="Chronological timeline from a farm-record CSV.")
    p.add_argument("csv")
    p.add_argument("--symptom-date", help="YYYY-MM-DD; limits output to the window before it")
    p.add_argument("--window", type=int, default=14)
    p.add_argument("--field")
    p.add_argument("--json", action="store_true")
    a = p.parse_args(argv)
    start = end = None
    if a.symptom_date:
        start, end = window_bounds(date.fromisoformat(a.symptom_date), a.window)
    items = timeline(load_events(a.csv), start, end, a.field)
    if a.json:
        print(json.dumps([to_jsonable(e) for e in items], ensure_ascii=False, indent=2))
    else:
        for e in items:
            print(format_line(e))
    return 0


if __name__ == "__main__":
    sys.exit(main())
