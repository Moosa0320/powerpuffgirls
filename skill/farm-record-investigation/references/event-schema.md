# Event schema

| Field | Values | Notes |
|---|---|---|
| event_id | E-001, E-002 ... | Per-farm display ID. Cite exactly. |
| type | planting, irrigation, fertilizer, pesticide, weather, observation, harvest, photo_observation | |
| date | YYYY-MM-DD or empty | Empty means unknown. Never invent a date. |
| date_certainty | exact, approximate, unknown | Approximate dates come from phrases like "pichle hafte". |
| product | free text or empty | urea, DAP, spray, rainfall ... |
| quantity | number or empty | Empty means unknown, not zero. |
| unit | bori, kg, litre, tanki, mm, acre | bori = 50 kg, tanki = about 200 litre by convention. |
| symptom | free text | Farmer's own words, only on observation events. |
| source | farmer_text, farmer_voice, weather_api, vision_model | |

Photo observations (P-001 ...) are unconfirmed until the farmer confirms them.
Weather events are area-level, not field-level.