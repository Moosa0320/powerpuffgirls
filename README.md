# FasalNama

A farm record investigator built on open-weight AI. Farmers log irrigation, fertilizer, pesticide, weather and photos by voice, text or camera, and FasalNama builds an evidence-cited timeline of what changed before a crop problem appeared. It never diagnoses.

This file is a progress note. The full plan is in `.kiro/specs/fasalnama/tasks.md`.

## Done

- **Repo setup**: layout, Apache-2.0 license, `.env.example`, secret scan (gitleaks), CI workflow.
- **Database**: SQLAlchemy models, SQLite or Postgres through `DATABASE_URL`, Alembic migration, `E-###` and `P-###` IDs.
- **Engine** (no AI): timeline, missing records, dose and water changes, day counts, unit conversion.
- **Providers**: speech-to-text, LLM, vision and audio behind one interface. Local models by default; Groq, Hugging Face and ElevenLabs are optional. Fallback chain, timeouts, no keys in error messages.
- **Parser**: notes in Urdu script, Roman Urdu or English become proposed events. The model gives `days_ago`; code works out the date.
- **Speech to text**: faster-whisper and Groq Whisper, 30 s limit, typed-input fallback.
- **Agent Skill** (`skill/farm-record-investigation`): instructions, references, three scripts and a sample farm. Passes the agentskills.io validator.
- **Skill loader**: loads the skill step by step and logs which parts were used.
- **Investigator**: tool-calling loop, 8-step cap, 2 verifier retries, code-written fallback report.
- **Verifier, part 1**: checks citations, dates, amounts and percentages against the records. Rejects diagnosis wording and treatment advice in English, Roman Urdu and Urdu script.

Tests: 482 passed in the last full run (`python -m pytest`), before the API step below. Not re-run since.

## In progress

- **API setup (11.1), interrupted**: dependencies pinned, local startup runs the Alembic migrations, passcode required on every route except `/health`, CORS tightened, shared API test fixture added. The core API tests aren't written yet.

## Remaining

1. **API endpoints** (11.2 to 11.4): tests and fixes for events, farms and photos, investigations, PDF, speech and weather. The routes exist but are untested.
2. **Frontend** (12, 13): React + TypeScript app, Urdu and English with right-to-left layout. Not started.
3. **Vercel deployment** (14): API, Neon Postgres and the web app. Not started; `render.yaml` is out of date.
4. **Verifier, part 2** (10.2 to 10.5, 9.2): more date formats, day counts, Urdu numbers, fixes to the fallback report.
5. **Parse eval** (5.2 to 5.4): 50 labelled notes, scoring and a live run.
6. **From the guide, not planned yet**: investigation eval on synthetic farms, architecture diagram, demo script, model license table, fresh-clone test.

No live parse, transcription or investigation has run yet with Groq, Hugging Face, ElevenLabs or a local Ollama model.

Built with AI-assisted development (Kiro).