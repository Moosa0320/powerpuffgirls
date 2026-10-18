# FasalNama tech rules

- Python 3.11, type hints everywhere, FastAPI, SQLAlchemy 2.0, Alembic, pytest. Frontend: React with Vite and TypeScript.
- DATABASE_URL drives the DB. SQLite locally, Postgres on Render. No SQLite-only SQL.
- Every model provider (STT, LLM, vision, TTS) is behind an abstract base class with a local open-weight implementation and optional cloud implementations. Selection by env vars.
- Secrets only in .env. Commit .env.example only. Never log API keys or farmer audio paths.
- Every function in engine/ and verifier/ has unit tests. No network calls in unit tests (use fakes).
- Open-weight models are the default. Proprietary services (Groq hosting aside, ElevenLabs) are optional plug-ins and the app must work with them removed in LOCAL mode.
- Pin dependency versions. Document every model and its license in MODEL_LICENSES.md.
