#!/usr/bin/env python3
"""Compare each record with the previous record of the same type and product. Stdlib only.

Usage: python scripts/compare.py examples/sample_farm.csv --type fertilizer
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from timeline import load_events, timeline  # noqa: E402

# Canonical units: mass -> kg, volume -> litre. Conventions documented in references/event-schema.md.
UNIT_TO_CANONICAL: dict[str, tuple[str, float]] = {
    "kg": ("kg", 1.0), "g": ("kg", 0.001), "bori": ("kg", 50.0), "bag": ("kg", 50.0),
    "litre": ("litre", 1.0), "liter": ("litre", 1.0), "l": ("litre", 1.0), "ml": ("litre", 0.001),
    "tanki": ("litre", 200.0), "mm": ("mm", 1.0),
}


def normalize(quantity: float, unit: str | None) -> tuple[float, str | None]:
    if unit is None or unit.lower() not in UNIT_TO_CANONICAL:
        return quantity, unit
    canonical, factor = UNIT_TO_CANONICAL[unit.lower()]
    return quantity * factor, canonical


def compare(events: list[dict[str, Any]], type_: str, field: str | None = None) -> list[dict[str, Any]]:
    last: dict[str | None, dict[str, Any]] = {}
    out: list[dict[str, Any]] = []
    for e in timeline(events, field=field):
        if e["type"] != type_:
            continue
        prev = last.get(e["product"])
        if prev and prev["quantity"] is not None and e["quantity"] is not None:
            pv, _ = normalize(prev["quantity"], prev["unit"])
            cv, unit = normalize(e["quantity"], e["unit"])
            out.append({
                "event_id": e["event_id"], "previous_event_id": prev["event_id"],
                "product": e["product"], "previous_value": pv, "current_value": cv, "unit": unit,
                "percent_change": round((cv - pv) / pv * 100, 2) if pv else None,
            })
        last[e["product"]] = e
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Numeric change versus the previous record.")
    p.add_argument("csv")
    p.add_argument("--type", required=True)
    p.add_argument("--field")
    a = p.parse_args(argv)
    print(json.dumps(compare(load_events(a.csv), a.type, a.field), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())