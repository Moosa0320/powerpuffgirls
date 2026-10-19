# Requirements Document

## Introduction

FasalNama is a farm record investigator. Farmers log irrigation, fertilizer, pesticide,
weather and photos by voice, text or camera. The system builds an evidence-cited timeline
of what changed before a crop problem appeared, flags missing records, and prepares
questions for an agricultural expert. **It never diagnoses.**

This document covers guide tasks 1-13 plus the cloud deployment. The cloud deployment runs
on Vercel (FastAPI function and static frontend) with hosted Postgres (Neon), replacing the
guide's Render plan. Task 14 in this plan is that deployment (it replaces guide task 15).
The eval harness (guide task 14) and guide tasks 16-21 follow later.

### Non-negotiable product principles
- Evidence timeline, not diagnosis.
- Code does what code can do (dates, gaps, numeric comparison, validation). AI is used
  only for language, speech, image observation and report writing.
- Every factual claim in a report cites event IDs. The verifier rejects anything else.
- Open-weight models are the default. Groq, Hugging Face hosting and ElevenLabs are optional
  plug-ins and must not break the local path when removed.

## Glossary

- **Event ID**: per-farm display ID of a recorded event, e.g. `E-014`.
- **Photo ID**: per-farm display ID of a photo, e.g. `P-007`.
- **days_ago**: relative day offset returned by the model; code converts it to a calendar date.
- **Gap**: a missing record type in the window, or an event with a null quantity or unknown date.
- **Safe template report**: the code-written report used when the model's report fails verification.
- **LOCAL / CLOUD mode**: run modes selected by env vars (local open-weight models or hosted inference).

## Requirements

### Requirement 1: Repo bootstrap (guide task 1)

**User Story:** As a developer, I want a correctly laid-out repository with licensing,
secret-safety and CI, so that contributions start from a clean, enforceable baseline.

#### Acceptance Criteria
1. WHEN the repo is cloned THEN the directory layout SHALL match section 4 of the guide.
2. THE repo SHALL include `LICENSE` (Apache-2.0), `.env.example`, `README.md`,
   `MODEL_LICENSES.md` and a deployment config.
3. THE repo SHALL include a pre-commit configuration that scans for committed secrets.
4. THE repo SHALL include CI that runs `pytest` and skill validation.
5. WHEN CI runs on an empty/placeholder test THEN it SHALL pass (green).

### Requirement 2: DB layer (guide task 2)

**User Story:** As a developer, I want one data layer that runs on SQLite locally and
hosted Postgres in the cloud, so that the same code is portable across run modes.

#### Acceptance Criteria
1. THE system SHALL define SQLAlchemy 2.0 models for farms, fields, events, photos,
   investigations per section 5.
2. THE system SHALL provide an Alembic migration creating all tables.
3. THE DB engine SHALL be selected by `DATABASE_URL` (SQLite locally, hosted Postgres in the cloud).
4. THE SQL SHALL contain no SQLite-only constructs.
5. WHEN the test suite runs against SQLite AND against Postgres THEN it SHALL pass on both.
6. THE system SHALL reject future `occurred_at` dates and negative quantities.
7. Display IDs SHALL follow `E-014` (events) and `P-007` (photos) formats, generated per farm.

### Requirement 3: Engine (guide task 3, section 7.4)

**User Story:** As an investigator, I want deterministic, AI-free analysis functions, so
that factual claims rest on code, not model output.

#### Acceptance Criteria
1. `get_timeline(field_id, start, end)` SHALL return sorted events and photo observations.
2. `find_gaps(field_id, window)` SHALL return days without irrigation/fertilizer/weather
   records and events with null quantity or unknown date.
3. `compare_values(field_id, type)` SHALL return change vs the previous record of the same
   type and product, with percentage change.
4. `days_between(a, b)` SHALL return the day count between two dates.
5. Tests SHALL cover relative-date resolution, month boundaries, empty windows, duplicate
   events, unit conversion and conflicting records.
6. At least 25 unit tests SHALL pass. No network calls in these tests.

### Requirement 4: Provider interfaces and factory (guide task 4, section 7.1)

**User Story:** As a developer, I want model providers behind abstract interfaces selected
by env vars, so that local open-weight implementations are default and cloud ones optional.

#### Acceptance Criteria
1. STT, LLM, vision and TTS SHALL each have an abstract base class.
2. A factory SHALL read `STT_BACKEND`, `LLM_BACKEND`, `VISION_BACKEND`, `TTS_BACKEND`.
3. THE factory SHALL implement the fallback chain: configured backend, then local backend if
   available, then typed input or no audio.
4. Every backend call SHALL have a timeout and return a typed error, never a raw exception.
5. Tests SHALL use fakes and SHALL NOT make network calls.
6. `.env.example` SHALL list every variable the providers read (including `HF_TOKEN`,
   `HF_VISION_MODEL` and `ELEVENLABS_VOICE_ID`) with no secret values.

### Requirement 5: Parser (guide task 5, section 7.3)

**User Story:** As a farmer, I want my Urdu/Roman-Urdu/English text turned into structured,
validated events I can confirm, so that nothing is saved until I approve it.

#### Acceptance Criteria
1. Input SHALL be text + today's date + field list; output SHALL be Pydantic-validated events.
2. THE LLM SHALL be called with a JSON schema (structured output locally, JSON mode on Groq).
3. THE prompt SHALL contain 12-15 few-shot examples across Urdu/Roman/mixed with agri words.
4. Model fields SHALL be type, product, quantity, unit, days_ago, symptom, confidence,
   never a calendar date.
5. Code SHALL convert days_ago to a date, normalize units, validate, and retry once on invalid JSON.
6. Parsed events SHALL be returned as proposals; nothing is saved until the farmer confirms.
7. 50 labelled sentences SHALL be parsed with accuracy reported in `eval/parse_results.md`.

### Requirement 6: STT backends (guide task 6, section 9 voice)

**User Story:** As a farmer, I want to speak my log entry, so that I can record without typing.

#### Acceptance Criteria
1. THE system SHALL provide local (faster-whisper) and Groq Whisper STT backends.
2. Audio SHALL be limited to 30 seconds and have silence trimmed.
3. THE STT call SHALL pass an `initial_prompt` with agri words and language `ur`.
4. ON failure THE system SHALL fall back to typed input.

### Requirement 7: Agent Skill (guide task 7, section 8)

**User Story:** As an agent, I want a standalone Agent Skill, so that the investigation
method is usable without the app.

#### Acceptance Criteria
1. Folder name SHALL equal frontmatter `name`: `farm-record-investigation`.
2. SKILL.md SHALL include references, scripts, assets and examples per section 8.
3. `scripts/validate_skill.sh` SHALL pass against the skill.
4. `python scripts/timeline.py examples/sample_farm.csv` SHALL work standalone.

### Requirement 8: Skill loader (guide task 8, section 7.2)

**User Story:** As the harness, I want progressive disclosure of the skill, so that only
needed context is loaded and the level used is logged.

#### Acceptance Criteria
1. AT startup THE loader SHALL read only name/description from each SKILL.md frontmatter.
2. WHEN a task matches THEN it SHALL load the full SKILL.md body into the system prompt.
3. References SHALL load only via a `read_reference(name)` tool when instructed.
4. Scripts SHALL be exposed as importable tool functions and remain CLI-runnable.
5. THE loader SHALL log which disclosure level was used per run.

### Requirement 9: Investigator loop (guide task 9, section 7.5)

**User Story:** As an investigator, I want a tool-calling loop that produces a cited report
JSON, so that every claim is traceable.

#### Acceptance Criteria
1. System prompt SHALL be SKILL.md body plus harness rules.
2. Tools SHALL include get_timeline, find_gaps, compare_values, get_photos, read_reference.
3. THE loop SHALL cap at 6-8 steps, returning tool results each step.
4. Final output SHALL be report JSON where each claim has text, type
   (fact|possibility|question) and event_ids or photo_ids.
5. Report sections SHALL be: What the records show; What may be worth investigating;
   Questions to ask next; plus Missing records and Photo observations (unconfirmed).

### Requirement 10: Verifier (guide task 10, section 7.6)

**User Story:** As a reviewer, I want every report mechanically verified, so that no
diagnosis, uncited fact or fake citation can pass.

#### Acceptance Criteria
1. THE verifier SHALL confirm every cited ID exists and belongs to the field (DB lookup).
2. THE verifier SHALL confirm dates/numbers in a claim match cited records.
3. THE verifier SHALL reject diagnosis/cause-as-fact via banned-claims patterns (plus optional
   LLM judge) and reject pesticide/fungicide/dosage recommendations.
4. Photo observations SHALL be labelled unconfirmed unless verified.
5. THE missing-records section SHALL be non-empty when `find_gaps` returned gaps.
6. Facts SHALL have at least one citation (schema check).
7. ON failure THE verifier SHALL return errors to the model and retry up to 2 times; if
   still failing it SHALL return the code-written safe template report and set
   `used_fallback = true`, logging everything in `verifier_log`.
8. Tests SHALL prove a diagnosis sentence, an uncited fact and a fake event ID are each rejected.

### Requirement 11: Backend API (guide task 11, section 6)

**User Story:** As a client, I want HTTP endpoints with passcode protection and CORS, so
that the app and skill can be driven over the network safely.

#### Acceptance Criteria
1. THE API SHALL expose all endpoints in section 6.
2. Write and AI endpoints SHALL require header `X-Passcode` when `APP_PASSCODE` is set.
3. CORS origins SHALL come from env (`CORS_ORIGINS`).
4. `GET /health` SHALL return liveness for the cloud host and demo warm-up.
5. THE pinned requirements SHALL include every package the API imports (`python-multipart`,
   `reportlab` and `numpy` are approved).
6. THE schema SHALL be owned by Alembic; app startup SHALL NOT conflict with `alembic upgrade head`.
7. API tests SHALL use FastAPI TestClient with fakes and SHALL NOT make network calls.

### Requirement 12: Frontend core (guide task 12, section 10)

**User Story:** As a farmer on a phone, I want to log, confirm and review my field records in
Urdu or English, so that keeping records is quick.

#### Acceptance Criteria
1. THE frontend SHALL be Vite + React + TypeScript in `app/frontend` with exact-pinned
   dependency versions and a committed lockfile.
2. THE frontend SHALL read the API base URL from `VITE_API_URL` and send `X-Passcode` from a
   passcode screen, stored in memory or sessionStorage only.
3. WHEN `/health` is slow or unreachable THEN THE UI SHALL show a "server is waking up" state and retry.
4. THE Farms page SHALL create and list farms and fields (name, crop, planting date, optional
   area, latitude and longitude).
5. THE Log page SHALL accept text, voice (MediaRecorder, 30 s cap, auto-stop on silence,
   editable transcript, typed-input fallback when STT fails) and photos (client-side resize to
   max 1280 px JPEG before upload, three-shot guidance, quality flags shown).
6. THE Confirm page SHALL show proposed events as editable rows; nothing SHALL be saved until
   the farmer confirms.
7. THE Timeline page SHALL show events and photo thumbnails in date order with gaps highlighted.
8. THE UI SHALL be mobile-first, use an Urdu font (Noto Nastaliq Urdu), and switch to RTL when
   Urdu is active.
9. `npm run build` SHALL pass with no TypeScript errors.

### Requirement 13: Investigate and report pages (guide task 13)

**User Story:** As a farmer preparing for an expert visit, I want to run an investigation and
read, hear or download the evidence report, so that I can share what the records show.

#### Acceptance Criteria
1. THE Investigate page SHALL take a symptom date, a window (7, 14 or 30 days) and a report
   language, and call `/investigate`.
2. THE Report page SHALL show What the records show, What may be worth investigating,
   Questions to ask next, Missing records and Photo observations (unconfirmed), with the cited
   event and photo IDs visible on each claim.
3. THE Report page SHALL always show the disclaimer and SHALL indicate when the safe fallback
   report was used.
4. THE Report page SHALL offer Listen (`/speak`, falling back to browser speech when the API
   returns 501) and PDF download.
5. A language toggle SHALL switch every UI string between Urdu and English without an i18n library.
6. THE UI SHALL NOT add diagnosis or treatment wording of its own.

### Requirement 14: Vercel deployment (replaces guide task 15)

**User Story:** As the team, I want the API and web app deployable on Vercel, so that the demo
runs on a public URL.

#### Acceptance Criteria
1. THE API SHALL deploy as a Vercel FastAPI function using the pinned cloud requirements, with
   the skill files available at runtime.
2. THE DB SHALL be hosted Postgres (Neon via the Vercel Marketplace); `postgres://` and
   `postgresql://` URLs SHALL be normalized to the psycopg 3 driver, and connections SHALL be
   serverless-safe.
3. Migrations SHALL run with `alembic upgrade head` before deploy; startup SHALL NOT create
   tables on Postgres.
4. THE `/investigate` function SHALL have a `maxDuration` that covers the investigator loop
   within the plan's limit.
5. THE frontend SHALL keep uploads under Vercel's 4.5 MB request limit, and THE API SHALL
   return 413 for oversized uploads.
6. THE web app SHALL deploy as a separate Vercel project rooted at `app/frontend` with SPA
   rewrites; `VITE_API_URL` and `CORS_ORIGINS` SHALL link the two.
7. `render.yaml` SHALL be replaced by Vercel config, and the README SHALL list env vars and
   exact deploy commands. Secrets SHALL only be set in Vercel's environment settings.
8. No production deploy SHALL run without the owner's Vercel login and confirmation.