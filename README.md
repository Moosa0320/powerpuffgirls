# FasalNama

A farm record investigator built on open-weight AI.

Farmers log irrigation, fertilizer, pesticide, weather and photos by voice, text or camera.
FasalNama builds an evidence-cited timeline of what changed before a crop problem appeared,
flags missing records, and prepares questions for an agricultural expert. It never diagnoses.

## Run modes

Default is fully local (private, offline). Cloud mode sends audio, text and photos to
Groq-hosted open-weight models for speed and is optional. Voice playback of reports in cloud
mode (ElevenLabs) is the only place a proprietary service may appear, and it is optional.

| Capability | LOCAL (default)   | CLOUD (Render)                 |
|------------|-------------------|--------------------------------|
| DB         | SQLite file       | Render Postgres                |
| STT        | faster-whisper    | Groq Whisper (open-weight)     |
| LLM        | Ollama (Qwen)     | Groq-hosted open-weight model  |
| Vision     | Local VLM (Ollama)| Groq-hosted open-weight vision |
| TTS        | Piper             | ElevenLabs / browser / none    |
| Weather    | Open-Meteo        | Open-Meteo                     |

## Principles
- Evidence timeline, not diagnosis.
- Code does deterministic work; AI does language, speech, vision and prose only.
- Every factual claim cites event IDs; the verifier rejects anything else.
- Open-weight by default; proprietary services are optional and removable in LOCAL mode.

## Quick start (LOCAL)
See app/backend requirements-local.txt, then run alembic migrations and start the API.

Built with AI-assisted development (Kiro).