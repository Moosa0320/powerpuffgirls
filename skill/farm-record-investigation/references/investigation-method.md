# Investigation method

## Windows
- 7 days: fast-acting changes (spray, heavy irrigation, heat).
- 14 days (default): fertilizer and irrigation changes.
- 30 days: slow changes, planting conditions, repeated patterns.

## What to compare
- Fertilizer dose versus the previous dose of the same product (scripts/compare.py).
- Irrigation frequency: the longest gap between irrigations in the window (scripts/gaps.py).
- Rainfall right before or after irrigation (possible excess water).
- Any spray in the 7 days before the symptom.

## Approximate and unknown dates
- Approximate dates: say "around" and do not compute exact day counts from them as facts.
- Unknown dates: list under Missing records; they cannot be placed on the timeline.

## Honesty
If nothing relevant is recorded, say so plainly. "The records do not show a change before the symptom" is a valid result.