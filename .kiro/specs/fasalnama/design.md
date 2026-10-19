# Design — FasalNama (tasks 1-14)

## Overview

FasalNama is split into four cooperating layers, matching the guide:

1. **Agent Skill** (`skill/farm-record-investigation/`) — a standalone, app-independent
   package following the Agent Skills standard. Carries the investigation *method*.
2. **Harness** (`harness/`) — the engine (pure code), parser, skill loader, investigator
   loop, verifier, and the provider abstractions (STT/LLM/vision/TTS).
3. **Backend** (`app/backend/`) — FastAPI + SQLAlchemy 2.0 + Alembic. Wraps the harness
   behind HTTP, adds passcode + CORS, serves `/health`.
4. **Frontend** (`app/frontend/`) — Vite + React + TypeScript (phase 2).

The guiding split: **code does deterministic work** (dates, gaps, numeric comparison,
validation); **AI does language work only** (parsing, speech, vision observation, prose).

## Architecture

```
            ┌────────────────────────────────────────────┐
            │                Frontend (React)             │  phase 2
            └───────────────┬────────────────────────────┘
                            │ HTTP (+ X-Passcode)
            ┌───────────────▼────────────────────────────┐
            │              FastAPI backend                │
            │  /health /farms /fields /parse /investigate │
            │  passcode middleware · CORS from env        │
            └───┬───────────────┬───────────────┬─────────┘
                │               │               │
        ┌───────▼──────┐ ┌──────▼───────┐ ┌─────▼──────────┐
        │   Engine     │ │   Parser     │ │  Investigator  │
        │ (pure code)  │ │ (LLM+schema) │ │  (tool loop)   │
        └──────────────┘ └──────┬───────┘ └─────┬──────────┘
                                │               │
                         ┌──────▼───────────────▼───────┐
                         │   Provider factory (env)      │
                         │ STT · LLM · Vision · TTS      │
                         │ local default → cloud → fallback
                         └───────────────────────────────┘
                                │
                         ┌──────▼───────┐
                         │ SQLAlchemy   │  DATABASE_URL
                         │ SQLite│Postgres
                         └──────────────┘
```

## Components and interfaces

### DB layer (`app/backend/db/`, `app/backend/models.py`)
- SQLAlchemy 2.0 declarative models with `Mapped[...]` typing.
- Engine from `DATABASE_URL`; `sqlite:///` locally, `postgresql+psycopg://` in the cloud.
- Portability rules: no `AUTOINCREMENT`, no SQLite pragmas in schema, JSON via SQLAlchemy
  `JSON` type (maps to JSON/JSONB on PG, TEXT on SQLite), bytea via `LargeBinary`.
- Display-ID generation (`E-###`, `P-###`) per farm, computed in a service helper not a
  DB default, so it is testable and DB-agnostic.
- Validation at the model/service boundary: reject future `occurred_at`, negative quantity.

#### Tables (section 5)
- `farms(id, name, created_at)`
- `fields(id, farm_id, name, crop, planting_date, area?, latitude?, longitude?)`
- `events(id, display_id, field_id, type, occurred_at, date_certainty, product?, quantity?,
  unit?, symptom?, source, raw_text?, confidence?, verified_by_farmer, created_at)`
  - type enum: planting, irrigation, fertilizer, pesticide, weather, observation, harvest,
    photo_observation
  - date_certainty: exact | approximate | unknown
  - source: farmer_text | farmer_voice | weather_api | vision_model
- `photos(id, display_id, field_id, event_id?, taken_at?, data|storage_key,
  quality_flags(JSON), vision_observation(JSON)?, verified_by_farmer)`
- `investigations(id, field_id, symptom_date, window_days, report_json, verifier_log,
  used_fallback, model_info, created_at)`

### Engine (`harness/engine.py`) — pure code, no AI
Functions are pure given a DB session + ids; unit for amounts normalized via a lookup table
(`bori`, `kg`, `litre`, `acre`). `days_ago → date` done here. Nulls mean unknown and drive
gap detection.

```python
def get_timeline(session, field_id, start, end) -> list[TimelineItem]
def find_gaps(session, field_id, window_days) -> GapReport
def compare_values(session, field_id, type) -> list[Comparison]
def days_between(a: date, b: date) -> int
```

### Provider abstractions (`harness/providers/`, `stt/`, `llm/`, `vision/`, `tts/`)
Each family: `base.py` abstract class + concrete impls. `providers/factory.py` reads env and
builds the fallback chain. Every call wrapped with a timeout and returns `Result[T, ProviderError]`.

- STT: `local_whisper` (faster-whisper), `groq_whisper`.
- LLM: `ollama`, `groq`.
- Vision: `local_vlm`, `groq_vlm`.
- TTS: `piper_local`, `elevenlabs`, `none`.

### Parser (`harness/parser.py`)
Pydantic `ParsedEvent` schema. Builds a prompt with 12–15 few-shot examples, calls the LLM
with a JSON schema, validates, retries once on invalid JSON. Converts `days_ago` to a date
using today's date, normalizes units, returns proposals (never saves).

### Skill loader (`harness/skill_loader.py`)
Progressive disclosure: startup reads only frontmatter name/description; on match loads body;
`read_reference(name)` tool loads a reference file on demand; scripts imported as tool
functions. Logs disclosure level per run.

### Investigator loop (`harness/investigator.py`)
System prompt = SKILL.md body + harness rules. Registers tools (engine functions + photos +
read_reference). Caps at 6–8 steps. Emits report JSON with claim objects
`{text, type: fact|possibility|question, event_ids|photo_ids}`.

### Verifier (`harness/verifier.py`)
Runs the checks in section 7.6 against the DB and the engine's gap output; banned-claims
regex from the skill's `references/banned-claims.md`. On failure: feed errors back, retry ≤2;
else return a code-written safe template report with `used_fallback=true`. Logs to `verifier_log`.

### Backend API (`app/backend/main.py`, `api/`)
FastAPI app, CORS from `CORS_ORIGINS`, passcode dependency checking `X-Passcode` against
`APP_PASSCODE` on write/AI routes. Endpoints per section 6. `/health` is unprotected.

## Data Models
Report JSON shape (verifier contract):
```json
{
  "sections": {
    "records_show": [{"text": "...", "type": "fact", "event_ids": ["E-014"]}],
    "worth_investigating": [{"text": "...", "type": "possibility", "event_ids": ["E-014","E-016"]}],
    "questions_next": [{"text": "...", "type": "question", "event_ids": []}],
    "missing_records": [{"text": "...", "type": "fact", "event_ids": []}],
    "photo_observations": [{"text": "...", "type": "possibility", "photo_ids": ["P-007"], "unconfirmed": true}]
  },
  "disclaimer": "This is an evidence summary built from records, not a diagnosis.",
  "used_fallback": false,
  "model_info": {}
}
```

## Error handling
- Provider errors are typed and never raw. Timeouts always set. Fallback chain honored.
- Parser invalid JSON → one retry → structured error (no invented events).
- Verifier failure → retry ≤2 → safe fallback report.
- API: 400 on validation, 401 on bad/missing passcode, 501 from `/speak` when no TTS, 5xx mapped
  to typed error payloads.

## Testing strategy
- Engine & verifier: pure unit tests, fakes only, no network (tech.md hard rule).
- DB: run suite against both SQLite and a Postgres service in CI.
- Providers: fakes implementing the base classes; assert fallback chain and timeouts.
- Parser: 50 labelled sentences → accuracy to `eval/parse_results.md`.
- Skill: `validate_skill.sh` + standalone script run in CI.
- API: FastAPI `TestClient`, passcode and CORS covered.

## Dependencies (pinned; ask before adding anything else)
Backend local: fastapi, uvicorn, sqlalchemy, alembic, pydantic, python-dotenv, httpx,
faster-whisper, pytest. Backend cloud: same minus heavy ML (no faster-whisper/torch/piper),
plus groq client, opencv-python-headless or Pillow. Frontend: vite, react, typescript (phase 2).
Any dependency not in the guide's lists requires explicit approval before use.

## Frontend (Vite + React + TypeScript)

- No router or UI library: a small state machine switches pages (Passcode, Farms, Log,
  Confirm, Timeline, Investigate, Report).
- `src/api.ts`: typed client for the section-6 endpoints. Base URL from `VITE_API_URL`, adds
  `X-Passcode`, maps network errors and a slow `/health` to a "server is waking up" state.
- `src/i18n.ts`: Urdu and English string tables. `dir` and font switch with the language.
- Voice: MediaRecorder (audio/webm), 30 s cap, AnalyserNode-based auto-stop on silence.
- Photos: canvas resize to max 1280 px JPEG before upload.
- Verification: `npm run build` (tsc + vite build).

## Deployment (Vercel), replacing the Render plan

The user moved the cloud deployment from Render to Vercel.

- API: a Vercel project at the repo root. Vercel's FastAPI support looks for an `app` instance
  at standard entrypoints (`app.py`, `index.py`, `main.py`, ... or the same names in `src/` or
  `app/`). Ours is `app/backend/main.py`, so the entrypoint is set with `tool.vercel.entrypoint`
  in `pyproject.toml` (check the exact syntax in Vercel's docs). The whole API is one function
  (500 MB Python bundle limit); `maxDuration` is set in `vercel.json` keyed by the entrypoint file.
- Dependencies: the pinned cloud requirements (no faster-whisper, torch or piper).
- DB: Neon Postgres via the Vercel Marketplace. URLs are normalized to `postgresql+psycopg://`;
  pooling is serverless-safe (NullPool or Neon's pooled endpoint). Alembic owns the schema and
  migrations run from a dev machine against the Neon URL before deploy.
- Web: a second Vercel project rooted at `app/frontend` (Vite preset, SPA rewrite to
  `index.html`). `VITE_API_URL` points at the API URL; the API's `CORS_ORIGINS` lists the web URL.
- Limits: 4.5 MB request bodies, so photos are resized client-side and audio is capped at 30 s.
- Secrets: set with `vercel env add` or the dashboard, never committed.