# Model licenses

Every model used by FasalNama is documented here with its license and link.
Open-weight models are the default. Groq and Hugging Face hosting and ElevenLabs are optional.
Verify exact names/licenses on Ollama, Hugging Face and the Groq console before building; they change quickly.

| Role   | Model (example)        | License        | Link | Notes |
|--------|------------------------|----------------|------|-------|
| LLM    | Qwen2.5 (TBD size)     | Apache-2.0*    | TODO | Verify current name/license |
| STT    | Whisper (faster-whisper)| MIT*          | TODO | Verify |
| Vision | Open VLM (e.g. LLaVA)  | TBD            | TODO | Check training data + license |
| Vision | Qwen3-VL-2B-Instruct   | Apache-2.0     | https://huggingface.co/Qwen/Qwen3-VL-2B-Instruct | Optional hosted vision (`VISION_BACKEND=hf`) via the Hugging Face router; default `HF_VISION_MODEL=Qwen/Qwen3-VL-2B-Instruct:featherless-ai`. License from the model card. |
| TTS    | Piper voice            | voice-specific | TODO | Per-voice license |

## Optional proprietary services (not required in LOCAL mode)
- Groq — hosted inference of open-weight models. Proprietary platform; models remain open-weight.
- Hugging Face router (router.huggingface.co) — hosted inference of open-weight models, used for
  vision when `VISION_BACKEND=hf` and `HF_TOKEN` is set. The `:featherless-ai` model suffix routes
  requests to the Featherless AI inference provider. Models remain open-weight.
- ElevenLabs — optional TTS for cloud report playback only.

*Marked licenses are placeholders pending verification. The repo (Apache-2.0) does not override model licenses.