# Model licenses

Every model used by FasalNama is documented here with its license and link.
Open-weight models are the default. Groq hosting and ElevenLabs are optional.
Verify exact names/licenses on Ollama, Hugging Face and the Groq console before building; they change quickly.

| Role   | Model (example)        | License        | Link | Notes |
|--------|------------------------|----------------|------|-------|
| LLM    | Qwen2.5 (TBD size)     | Apache-2.0*    | TODO | Verify current name/license |
| STT    | Whisper (faster-whisper)| MIT*          | TODO | Verify |
| Vision | Open VLM (e.g. LLaVA)  | TBD            | TODO | Check training data + license |
| TTS    | Piper voice            | voice-specific | TODO | Per-voice license |

## Optional proprietary services (not required in LOCAL mode)
- Groq — hosted inference of open-weight models. Proprietary platform; models remain open-weight.
- ElevenLabs — optional TTS for cloud report playback only.

*Marked licenses are placeholders pending verification. The repo (Apache-2.0) does not override model licenses.