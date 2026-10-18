# FasalNama repo structure

See section 4 of the implementation guide. Skill lives in skill/farm-record-investigation and must stay usable without the app.

```
FasalNama/
├── skill/farm-record-investigation/
│   ├── SKILL.md
│   ├── references/ (event-schema.md, investigation-method.md, banned-claims.md, question-bank.md)
│   ├── scripts/ (timeline.py, gaps.py, compare.py)
│   ├── assets/report-template.md
│   └── examples/sample_farm.csv
├── harness/
│   ├── skill_loader.py
│   ├── parser.py
│   ├── engine.py
│   ├── investigator.py
│   ├── verifier.py
│   ├── providers/ (base.py, factory.py)
│   ├── stt/ (base.py, local_whisper.py, groq_whisper.py)
│   ├── llm/ (base.py, ollama.py, groq.py)
│   ├── vision/ (base.py, local_vlm.py, groq_vlm.py)
│   └── tts/ (base.py, piper_local.py, elevenlabs.py)
├── app/
│   ├── backend/ (main.py, api/, db/, models.py, alembic/, requirements-local.txt, requirements-cloud.txt)
│   └── frontend/ (Vite React TS)
├── eval/ (farms/*.json, expected/*.json, run_eval.py, results.md)
├── tests/
├── scripts/ (export_db.py, validate_skill.sh)
├── docs/ (architecture.png, screenshots)
├── render.yaml
├── .env.example
├── README.md
├── LICENSE (Apache-2.0)
└── MODEL_LICENSES.md
```
