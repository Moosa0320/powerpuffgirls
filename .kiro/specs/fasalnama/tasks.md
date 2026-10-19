# Implementation Plan: FasalNama

## Overview
Rule: do not start a task before the previous one passes its tests/acceptance criteria.
Write tests first where applicable. Ask before adding any dependency not listed in the guide.
Deployment target: Vercel (task 14) instead of Render.
Order: the app first (investigator, API, frontend, Vercel), then hardening (verifier checks, parse eval).
Every open task is a small step that touches a few files.

## Tasks
- [x] 1. Repo bootstrap
  - Create the section-4 directory layout with package `__init__.py` files and placeholders.
  - Add `LICENSE` (Apache-2.0), `.env.example`, `README.md`, `MODEL_LICENSES.md`, deployment config,
    `.gitignore`, root `pyproject.toml`/`requirements` wiring and `pytest` config.
  - Add pre-commit config with a secret scan hook.
  - Add CI (GitHub Actions) running `pytest` and skill validation.
  - Add one placeholder test so CI is green.
  - _Done when: CI is green on an empty test._
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_

- [x] 2. DB layer
  - Define SQLAlchemy 2.0 models for farms, fields, events, photos, investigations (section 5).
  - Implement `DATABASE_URL` engine/session factory (SQLite + Postgres), no SQLite-only SQL.
  - Add Alembic migration creating all tables.
  - Add display-ID helpers (`E-###`, `P-###`) and validation (reject future dates, negative qty).
  - _Done when: the same test suite passes on SQLite and Postgres._
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7_

- [x] 3. Engine plus tests
  - Implement `get_timeline`, `find_gaps`, `compare_values`, `days_between` with unit lookup table.
  - Write at least 25 unit tests: relative-date resolution, month boundaries, empty windows,
    duplicates, unit conversion, conflicting records. No network calls.
  - _Done when: at least 25 unit tests pass._
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_

- [x] 4. Provider interfaces and factory
  - Abstract base classes for STT, LLM, vision, TTS.
  - `factory.py` env-based selection + fallback chain; timeouts and typed errors.
  - Fakes for tests; assert fallback behavior with no network calls.
  - Add `HF_TOKEN`, `HF_VISION_MODEL` and `ELEVENLABS_VOICE_ID` to `.env.example` (no secret values).
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6_

- [ ] 5. Parser
  - [x] 5.1 Parser fixes and unit tests
    - Pydantic `ParsedEvent` schema; 12-15 few-shot prompt (Urdu/Roman/mixed, agri words).
    - LLM call with JSON schema; days_ago -> date, unit normalization, validate, retry once.
    - Normalize product names through an alias table (`compare_values` groups by exact product).
    - Mark approximate dates per event, not for the whole note.
    - Add the missing Urdu-script and Roman spellings of units and date markers.
    - Return proposals only (no save).
    - Unit tests in `tests/test_parser.py` with fakes, no network.
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6_
  - [ ] 5.2 Parse eval dataset
    - `eval/parse_sentences.json`: the 50 notes and 58 labelled events drafted in an earlier attempt
      (today 2026-03-15), written as drafted.
    - Dataset checks in `tests/test_parse_eval.py`: counts, language mix, canonical labels, type
      coverage, no overlap with FEW_SHOT. No network.
    - _Requirements: 5.7_
  - [ ] 5.3 Parse eval script and scoring
    - `eval/run_parse_eval.py`: importable scoring with fixed rules, pacing and 429 backoff, and
      `--pending-only`; scoring tests; a pending `eval/parse_results.md`. No network.
    - _Requirements: 5.7_
  - [ ] 5.4 Live parse eval run
    - Run the script against the configured backend in the background (about 17 minutes at Groq's
      limits) and write `eval/parse_results.md`.
    - _Done when: 50 labelled sentences parsed, accuracy in `eval/parse_results.md`._
    - _Requirements: 5.7_

- [x] 6. Local and Groq STT backends
  - `local_whisper` (faster-whisper) and `groq_whisper`; 30 s limit, silence trim, initial_prompt.
  - Silence trimming: VAD filter on the local path; the browser auto-stops on silence (task 12).
    No new audio dependencies.
  - Fallback to typed input on failure.
  - _Requirements: 6.1, 6.2, 6.3, 6.4_

- [x] 7. Skill files
  - SKILL.md + references (event-schema, investigation-method, banned-claims, question-bank),
    scripts (timeline.py, gaps.py, compare.py), assets/report-template.md, examples/sample_farm.csv.
  - _Done when: validator passes and `python scripts/timeline.py examples/sample_farm.csv` works._
  - _Requirements: 7.1, 7.2, 7.3, 7.4_

- [x] 8. Skill loader
  - Progressive disclosure (frontmatter -> body -> references via tool); scripts as tools; log level.
  - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_

- [ ] 9. Investigator loop
  - [x] 9.1 Investigator tests and per-run disclosure log
    - Call `loader.start_run()` at the start of each run; store the run's disclosure levels and
      deepest level in model_info.
    - `tests/test_investigator.py` with FakeLLM: tool calls and results, five-section report, step
      cap, verifier retry up to 2 times, safe fallback (no LLM, LLM error, persistent rejection),
      verifier_log contents.
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 10.7_
  - [ ] 9.2 Pass the new evidence fields
    - After 10.2-10.4: pass gap event IDs, the window and photo dates into `Evidence`.
    - _Requirements: 10.2, 10.4, 10.5_

- [ ] 10. Verifier
  - [x] 10.1 Banned wording and treatment-advice patterns
    - Close the English gaps ("is a fungal infection", "Urea caused the yellowing") in the skill's
      `banned-claims.md`; keep the example lists in `tests/test_skill.py` in sync; allowed wording still passes.
    - Keep `DEFAULT_BANNED` in sync with the file and log a warning when falling back.
    - Treatment and dosage patterns in English, Roman Urdu and Urdu script, applied to every claim type;
      a recorded dose quoted in a fact still passes.
    - _Requirements: 10.3_
  - [ ] 10.2 Structural checks
    - Optional `Evidence` fields (gap event IDs, window, photo dates) with backward-compatible defaults.
    - Section and claim-type rules; unknown sections rejected; unconfirmed label for unverified
      photos in any section; every gap event ID cited in missing_records; optional LLM judge hook,
      off by default.
    - _Requirements: 10.1, 10.4, 10.5, 10.6_
  - [ ] 10.3 Dates and day counts
    - Verify ISO and month-name dates (English, Urdu); reject ambiguous numeric dates; check day
      counts in three languages against cited event dates, cited photo dates, the symptom date and
      the window start.
    - _Requirements: 10.2_
  - [ ] 10.4 Numbers in three languages
    - Normalize Urdu and Eastern Arabic digits and characters; Urdu/Roman unit and percent words;
      mask IDs and cited product names before the number checks.
    - _Requirements: 10.2_
  - [ ] 10.5 Safe fallback report fixes
    - `safe_template_report` always passes `verify_report`: photo dates, farmer symptom text, plain
      number formatting, unknown-date events, window wording. Seeded random tests.
    - _Done when: a diagnosis sentence, an uncited fact and a fake event ID are each rejected, and the fallback report always passes._
    - _Requirements: 10.7, 10.8_

- [ ] 11. Backend API
  - [ ] 11.1 Requirements, startup and core tests
    - Pin and install `python-multipart`, `reportlab` and `numpy` in both requirements files (approved).
    - Startup must not conflict with Alembic migrations.
    - Passcode on every route except /health and the docs when `APP_PASSCODE` is set; CORS from env.
    - Shared TestClient fixture in `tests/conftest.py`; `tests/test_api_core.py`. No network.
    - _Requirements: 11.2, 11.3, 11.4, 11.5, 11.6, 11.7_
  - [ ] 11.2 Event endpoints
    - /transcribe (STT fallback chain, size limits, typed-input hint), /parse, /events/confirm, timeline.
    - `tests/test_api_events.py` with fakes.
    - _Requirements: 11.1, 11.7_
  - [ ] 11.3 Farm, field and photo endpoints
    - Farms and fields; photo upload (resize, EXIF date, quality flags, 413), observe (unconfirmed), confirm.
    - `tests/test_api_farms_photos.py` with fakes.
    - _Requirements: 11.1, 11.7_
  - [ ] 11.4 Investigation, PDF, speech and weather endpoints
    - /investigate (saves report, verifier_log, used_fallback, model_info), investigation fetch, PDF,
      /speak (501 when no TTS), /weather/sync (Open-Meteo, area-level).
    - `tests/test_api_investigations.py` with fakes and stubbed HTTP.
    - _Requirements: 11.1, 11.7_

- [ ] 12. Frontend core
  - [ ] 12.1 Scaffold
    - Vite + React + TypeScript in `app/frontend`, exact-pinned versions, committed lockfile, no
      router or UI library.
    - _Done when: `npm run build` passes._
    - _Requirements: 12.1, 12.9_
  - [ ] 12.2 App shell, API client and passcode screen
    - Page switcher with stub files for every page and component; typed API client (base URL from
      `VITE_API_URL`, `X-Passcode` from sessionStorage, typed errors, "server is waking up" retry on
      /health); Urdu/English language core with RTL and Noto Nastaliq Urdu; passcode screen.
    - _Requirements: 12.2, 12.3, 12.8, 13.5_
  - [ ] 12.3 Farms and fields page
    - Create and list farms and fields.
    - _Requirements: 12.4_
  - [ ] 12.4 Timeline page
    - Events and photo thumbnails in date order, gaps highlighted.
    - _Requirements: 12.7_
  - [ ] 12.5 Log page and voice recorder
    - Text box; mic with MediaRecorder, 30 s cap, auto-stop on silence, editable transcript, typed fallback.
    - _Requirements: 12.5_
  - [ ] 12.6 Photo capture
    - Client-side resize to max 1280 px JPEG, three-shot guidance, upload, quality flags shown.
    - _Requirements: 12.5, 14.5_
  - [ ] 12.7 Confirm page
    - Editable proposed events from /parse; nothing saved until /events/confirm.
    - _Requirements: 12.6_

- [ ] 13. Investigate and report pages
  - [ ] 13.1 Investigate page
    - Symptom date, window (7, 14, 30), report language; runs /investigate.
    - _Requirements: 13.1_
  - [ ] 13.2 Report page
    - Five sections with cited ID chips, fallback notice, disclaimer, Listen (/speak, browser speech
      on 501), PDF download.
    - _Done when: `npm run build` passes and log -> confirm -> investigate -> report works end to end locally._
    - _Requirements: 13.2, 13.3, 13.4, 13.6_

- [ ] 14. Vercel deployment (replaces the guide's Render deploy)
  - [ ] 14.1 API on Vercel
    - FastAPI entrypoint config, pinned cloud requirements, `maxDuration` for /investigate, skill
      files in the bundle; `DATABASE_URL` normalized to psycopg 3 with serverless-safe pooling; no
      `create_all` on Postgres; local smoke test.
    - _Requirements: 14.1, 14.2, 14.3, 14.4, 14.5_
  - [ ] 14.2 Web on Vercel and docs
    - `app/frontend` Vercel config with SPA rewrites; replace `render.yaml`; README with env vars and
      exact `vercel` CLI steps; MODEL_LICENSES updates. No production deploy.
    - _Done when: `npm run build` passes and the README has exact deploy steps._
    - _Requirements: 14.6, 14.7, 14.8_

## Notes

- Deployment target is Vercel. Task 14 replaces the guide's Render deploy (guide task 15).
- Code for tasks 4-11 already existed from an earlier session. Those tasks verify it, add the
  missing tests and fix what fails.
- Larger tasks stalled after planning (5, 5.2 three times, 10, 10.2). Small tasks finished, so every
  open task is now a small step (user's choice).
- The app comes first. Verifier hardening (10.2-10.5, 9.2) and the parse eval (5.2-5.4) run after the
  Vercel task (user's choice). The current verifier already rejects a diagnosis sentence, an uncited
  fact and a fake event ID.
- Tasks in the same wave touch disjoint files and can run in parallel.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["4", "7"] },
    { "id": 1, "tasks": ["8", "5.1", "6"] },
    { "id": 2, "tasks": ["10.1"] },
    { "id": 3, "tasks": ["9.1", "11.1"] },
    { "id": 4, "tasks": ["11.2", "11.3", "11.4"] },
    { "id": 5, "tasks": ["12.1"] },
    { "id": 6, "tasks": ["12.2"] },
    { "id": 7, "tasks": ["12.3", "12.4", "12.5", "12.6", "12.7"] },
    { "id": 8, "tasks": ["13.1", "13.2"] },
    { "id": 9, "tasks": ["14.1", "14.2"] },
    { "id": 10, "tasks": ["10.2", "5.2"] },
    { "id": 11, "tasks": ["10.3", "5.3"] },
    { "id": 12, "tasks": ["10.4", "5.4"] },
    { "id": 13, "tasks": ["10.5"] },
    { "id": 14, "tasks": ["9.2"] }
  ]
}
```