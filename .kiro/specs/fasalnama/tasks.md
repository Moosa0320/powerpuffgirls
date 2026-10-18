# Implementation Plan Ã¢â‚¬â€ FasalNama (tasks 1Ã¢â‚¬â€œ11)

Rule: do not start a task before the previous one passes its tests/acceptance criteria.
Write tests first where applicable. Ask before adding any dependency not listed in the guide.

- [x] 1. Repo bootstrap
  - Create the section-4 directory layout with package `__init__.py` files and placeholders.
  - Add `LICENSE` (Apache-2.0), `.env.example`, `README.md`, `MODEL_LICENSES.md`, `render.yaml`,
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
  - Write Ã¢â€°Â¥25 unit tests: relative-date resolution, month boundaries, empty windows, duplicates,
    unit conversion, conflicting records. No network calls.
  - _Done when: at least 25 unit tests pass._
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_

- [ ] 4. Provider interfaces and factory
  - Abstract base classes for STT, LLM, vision, TTS.
  - `factory.py` env-based selection + fallback chain; timeouts and typed errors.
  - Fakes for tests; assert fallback behavior with no network calls.
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

- [ ] 5. Parser
  - Pydantic `ParsedEvent` schema; 12Ã¢â‚¬â€œ15 few-shot prompt (Urdu/Roman/mixed, agri words).
  - LLM call with JSON schema; days_agoÃ¢â€ â€™date, unit normalization, validate, retry once.
  - Return proposals only (no save).
  - _Done when: 50 labelled sentences parsed, accuracy in `eval/parse_results.md`._
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7_

- [ ] 6. Local and Groq STT backends
  - `local_whisper` (faster-whisper) and `groq_whisper`; 30 s limit, silence trim, initial_prompt.
  - Fallback to typed input on failure.
  - _Requirements: 6.1, 6.2, 6.3, 6.4_

- [ ] 7. Skill files
  - SKILL.md + references (event-schema, investigation-method, banned-claims, question-bank),
    scripts (timeline.py, gaps.py, compare.py), assets/report-template.md, examples/sample_farm.csv.
  - _Done when: validator passes and `python scripts/timeline.py examples/sample_farm.csv` works._
  - _Requirements: 7.1, 7.2, 7.3, 7.4_

- [ ] 8. Skill loader
  - Progressive disclosure (frontmatter Ã¢â€ â€™ body Ã¢â€ â€™ references via tool); scripts as tools; log level.
  - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_

- [ ] 9. Investigator loop
  - Tool-calling loop, step cap 6Ã¢â‚¬â€œ8, report JSON with cited claim objects and five sections.
  - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_

- [ ] 10. Verifier
  - All section-7.6 checks, retry Ã¢â€°Â¤2, code-written safe template fallback, verifier_log.
  - _Done when: a diagnosis sentence, an uncited fact and a fake event ID are each rejected._
  - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7, 10.8_

- [ ] 11. Backend API
  - All section-6 endpoints, passcode middleware, CORS from env, `/health`.
  - _Requirements: 11.1, 11.2, 11.3, 11.4_
```
