# Requirements — FasalNama (tasks 1–11)

## Introduction

FasalNama is a farm record investigator. Farmers log irrigation, fertilizer, pesticide,
weather and photos by voice, text or camera. The system builds an evidence-cited timeline
of what changed before a crop problem appeared, flags missing records, and prepares
questions for an agricultural expert. **It never diagnoses.**

This document covers the first phase of delivery (guide tasks 1–11): repo bootstrap, DB
layer, engine, provider interfaces, parser, STT backends, the Agent Skill, the skill
loader, the investigator loop, the verifier, and the backend API. Frontend, deploy,
photos, weather, PDF/TTS, eval and docs (tasks 12–21) follow in later phases.

### Non-negotiable product principles
- Evidence timeline, not diagnosis.
- Code does what code can do (dates, gaps, numeric comparison, validation). AI is used
  only for language, speech, image observation and report writing.
- Every factual claim in a report cites event IDs. The verifier rejects anything else.
- Open-weight models are the default. Groq and ElevenLabs are optional plug-ins and must
  not break the local path when removed.

---

## Requirement 1 — Repo bootstrap (guide task 1)

**User story:** As a developer, I want a correctly laid-out repository with licensing,
secret-safety and CI, so that contributions start from a clean, enforceable baseline.

#### Acceptance criteria
1. WHEN the repo is cloned THEN the directory layout SHALL match section 4 of the guide.
2. THE repo SHALL include `LICENSE` (Apache-2.0), `.env.example`, `README.md`,
   `MODEL_LICENSES.md` and `render.yaml`.
3. THE repo SHALL include a pre-commit configuration that scans for committed secrets.
4. THE repo SHALL include CI that runs `pytest` and skill validation.
5. WHEN CI runs on an empty/placeholder test THEN it SHALL pass (green).

## Requirement 2 — DB layer (guide task 2)

**User story:** As a developer, I want one data layer that runs on SQLite locally and
Postgres on Render, so that the same code is portable across run modes.

#### Acceptance criteria
1. THE system SHALL define SQLAlchemy 2.0 models for farms, fields, events, photos,
   investigations per section 5.
2. THE system SHALL provide an Alembic migration creating all tables.
3. THE DB engine SHALL be selected by `DATABASE_URL` (SQLite locally, Postgres on Render).
4. THE SQL SHALL contain no SQLite-only constructs.
5. WHEN the test suite runs against SQLite AND against Postgres THEN it SHALL pass on both.
6. THE system SHALL reject future `occurred_at` dates and negative quantities.
7. Display IDs SHALL follow `E-014` (events) and `P-007` (photos) formats, generated per farm.

## Requirement 3 — Engine (guide task 3, section 7.4)

**User story:** As an investigator, I want deterministic, AI-free analysis functions, so
that factual claims rest on code, not model output.

#### Acceptance criteria
1. `get_timeline(field_id, start, end)` SHALL return sorted events and photo observations.
2. `find_gaps(field_id, window)` SHALL return days without irrigation/fertilizer/weather
   records and events with null quantity or unknown date.
3. `compare_values(field_id, type)` SHALL return change vs the previous record of the same
   type and product, with percentage change.
4. `days_between(a, b)` SHALL return the day count between two dates.
5. Tests SHALL cover relative-date resolution, month boundaries, empty windows, duplicate
   events, unit conversion and conflicting records.
6. At least 25 unit tests SHALL pass. No network calls in these tests.

## Requirement 4 — Provider interfaces & factory (guide task 4, section 7.1)

**User story:** As a developer, I want model providers behind abstract interfaces selected
by env vars, so that local open-weight implementations are default and cloud ones optional.

#### Acceptance criteria
1. STT, LLM, vision and TTS SHALL each have an abstract base class.
2. A factory SHALL read `STT_BACKEND`, `LLM_BACKEND`, `VISION_BACKEND`, `TTS_BACKEND`.
3. THE factory SHALL implement the fallback chain: configured backend → local backend if
   available → typed input / no audio.
4. Every backend call SHALL have a timeout and return a typed error, never a raw exception.
5. Tests SHALL use fakes and SHALL NOT make network calls.

## Requirement 5 — Parser (guide task 5, section 7.3)

**User story:** As a farmer, I want my Urdu/Roman-Urdu/English text turned into structured,
validated events I can confirm, so that nothing is saved until I approve it.

#### Acceptance criteria
1. Input SHALL be text + today's date + field list; output SHALL be Pydantic-validated events.
2. THE LLM SHALL be called with a JSON schema (structured output locally, JSON mode on Groq).
3. THE prompt SHALL contain 12–15 few-shot examples across Urdu/Roman/mixed with agri words.
4. Model fields SHALL be type, product, quantity, unit, days_ago, symptom, confidence —
   never a calendar date.
5. Code SHALL convert days_ago→date, normalize units, validate, and retry once on invalid JSON.
6. Parsed events SHALL be returned as proposals; nothing is saved until the farmer confirms.
7. 50 labelled sentences SHALL be parsed with accuracy reported in `eval/parse_results.md`.

## Requirement 6 — STT backends (guide task 6, section 9 voice)

**User story:** As a farmer, I want to speak my log entry, so that I can record without typing.

#### Acceptance criteria
1. THE system SHALL provide local (faster-whisper) and Groq Whisper STT backends.
2. Audio SHALL be limited to 30 seconds and have silence trimmed.
3. THE STT call SHALL pass an `initial_prompt` with agri words and language `ur`.
4. ON failure THE system SHALL fall back to typed input.

## Requirement 7 — Agent Skill (guide task 7, section 8)

**User story:** As an agent, I want a standalone Agent Skill, so that the investigation
method is usable without the app.

#### Acceptance criteria
1. Folder name SHALL equal frontmatter `name`: `farm-record-investigation`.
2. SKILL.md SHALL include references, scripts, assets and examples per section 8.
3. `scripts/validate_skill.sh` SHALL pass against the skill.
4. `python scripts/timeline.py examples/sample_farm.csv` SHALL work standalone.

## Requirement 8 — Skill loader (guide task 8, section 7.2)

**User story:** As the harness, I want progressive disclosure of the skill, so that only
needed context is loaded and the level used is logged.

#### Acceptance criteria
1. AT startup THE loader SHALL read only name/description from each SKILL.md frontmatter.
2. WHEN a task matches THEN it SHALL load the full SKILL.md body into the system prompt.
3. References SHALL load only via a `read_reference(name)` tool when instructed.
4. Scripts SHALL be exposed as importable tool functions and remain CLI-runnable.
5. THE loader SHALL log which disclosure level was used per run.

## Requirement 9 — Investigator loop (guide task 9, section 7.5)

**User story:** As an investigator, I want a tool-calling loop that produces a cited report
JSON, so that every claim is traceable.

#### Acceptance criteria
1. System prompt SHALL be SKILL.md body plus harness rules.
2. Tools SHALL include get_timeline, find_gaps, compare_values, get_photos, read_reference.
3. THE loop SHALL cap at 6–8 steps, returning tool results each step.
4. Final output SHALL be report JSON where each claim has text, type
   (fact|possibility|question) and event_ids or photo_ids.
5. Report sections SHALL be: What the records show; What may be worth investigating;
   Questions to ask next; plus Missing records and Photo observations (unconfirmed).

## Requirement 10 — Verifier (guide task 10, section 7.6)

**User story:** As a reviewer, I want every report mechanically verified, so that no
diagnosis, uncited fact or fake citation can pass.

#### Acceptance criteria
1. THE verifier SHALL confirm every cited ID exists and belongs to the field (DB lookup).
2. THE verifier SHALL confirm dates/numbers in a claim match cited records.
3. THE verifier SHALL reject diagnosis/cause-as-fact via banned-claims patterns (+ optional
   LLM judge) and reject pesticide/fungicide/dosage recommendations.
4. Photo observations SHALL be labelled unconfirmed unless verified.
5. THE missing-records section SHALL be non-empty when `find_gaps` returned gaps.
6. Facts SHALL have at least one citation (schema check).
7. ON failure THE verifier SHALL return errors to the model and retry up to 2 times; if
   still failing it SHALL return the code-written safe template report and set
   `used_fallback = true`, logging everything in `verifier_log`.
8. Tests SHALL prove a diagnosis sentence, an uncited fact and a fake event ID are each rejected.

## Requirement 11 — Backend API (guide task 11, section 6)

**User story:** As a client, I want HTTP endpoints with passcode protection and CORS, so
that the app and skill can be driven over the network safely.

#### Acceptance criteria
1. THE API SHALL expose all endpoints in section 6.
2. Write and AI endpoints SHALL require header `X-Passcode` when `APP_PASSCODE` is set.
3. CORS origins SHALL come from env (`CORS_ORIGINS`).
4. `GET /health` SHALL return liveness for Render and demo warm-up.
