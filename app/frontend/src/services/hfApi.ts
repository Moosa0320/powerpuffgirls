/**
 * Hugging Face Inference API service for FasalNama frontend.
 *
 * Covers all four HF-hosted open-weight models used by the backend:
 *   LLM  → Qwen/Qwen2.5-72B-Instruct   (chat completions, OpenAI-compat)
 *   STT  → openai/whisper-large-v3      (audio/transcriptions)
 *   VLM  → Qwen/Qwen2-VL-7B-Instruct   (vision + text)
 *   TTS  → facebook/mms-tts-urd-script-arabic  (text-to-speech, Urdu)
 *
 * All calls go directly to HuggingFace Router (OpenAI-compatible) or the
 * HF Inference API, mirroring harness/providers/hf_*.py behaviour.
 *
 * Usage: import { HFApi } from './hfApi';
 */

// ── Endpoints ────────────────────────────────────────────────────────────────
const HF_ROUTER_BASE = 'https://router.huggingface.co/v1';
const HF_INFERENCE_BASE = 'https://api-inference.huggingface.co/models';

// ── Default model IDs (match .env.example / harness defaults) ────────────────
export const HF_MODELS = {
  llm: 'Qwen/Qwen2.5-72B-Instruct',
  stt: 'openai/whisper-large-v3',
  vision: 'Qwen/Qwen2-VL-7B-Instruct',
  tts: 'facebook/mms-tts-urd-script-arabic',
} as const;

// ── Shared types ─────────────────────────────────────────────────────────────

export interface HFModelStatus {
  id: keyof typeof HF_MODELS;
  modelId: string;
  label: string;
  task: string;
  icon: string;
  available: boolean;
  latencyMs?: number;
  error?: string;
}

export interface LLMMessage {
  role: 'system' | 'user' | 'assistant';
  content: string;
}

export interface LLMResponse {
  content: string;
  model: string;
  usage?: { prompt_tokens: number; completion_tokens: number; total_tokens: number };
}

export interface STTResponse {
  text: string;
  language?: string;
}

export interface VLMObservation {
  leaf_color: string | null;
  pattern: string | null;
  spots: boolean | null;
  wilting: boolean | null;
  affected_area: string | null;
  symptom_description: string | null;
  notes: string | null;
}

// ── Token management ──────────────────────────────────────────────────────────
// The HF token is stored in sessionStorage (set by the user at runtime).
// It is never persisted to localStorage for security.

const TOKEN_KEY = 'hf_token';

export function setHFToken(token: string): void {
  if (token.trim()) {
    sessionStorage.setItem(TOKEN_KEY, token.trim());
  } else {
    sessionStorage.removeItem(TOKEN_KEY);
  }
}

export function getHFToken(): string {
  return sessionStorage.getItem(TOKEN_KEY) || '';
}

export function hasHFToken(): boolean {
  return !!getHFToken();
}

// ── Helper ────────────────────────────────────────────────────────────────────

function authHeaders(token: string): Record<string, string> {
  return {
    Authorization: `Bearer ${token}`,
    'Content-Type': 'application/json',
  };
}

// ── 1. LLM — Qwen/Qwen2.5-72B-Instruct ───────────────────────────────────────

/**
 * Chat completion via HuggingFace Router (OpenAI-compatible endpoint).
 * Falls back to a simple prompt if tool-calling is not needed.
 */
export async function hfChatCompletion(
  messages: LLMMessage[],
  modelId: string = HF_MODELS.llm,
  options: { temperature?: number; max_tokens?: number; jsonMode?: boolean } = {}
): Promise<LLMResponse> {
  const token = getHFToken();
  if (!token) throw new Error('HF_TOKEN not set. Please enter your Hugging Face token.');

  const body: Record<string, unknown> = {
    model: modelId,
    messages,
    temperature: options.temperature ?? 0,
    max_tokens: options.max_tokens ?? 1024,
  };

  if (options.jsonMode) {
    body['response_format'] = { type: 'json_object' };
  }

  const res = await fetch(`${HF_ROUTER_BASE}/chat/completions`, {
    method: 'POST',
    headers: authHeaders(token),
    body: JSON.stringify(body),
  });

  if (!res.ok) {
    const errText = await res.text().catch(() => '');
    throw new Error(`HF LLM error ${res.status}: ${errText.slice(0, 200)}`);
  }

  const data = await res.json();
  const choice = data.choices?.[0]?.message;
  return {
    content: choice?.content ?? '',
    model: data.model ?? modelId,
    usage: data.usage,
  };
}

/**
 * Convenience: parse a farmer's note using the LLM.
 * Returns structured JSON about detected events.
 */
export async function hfParseFarmerNote(
  note: string,
  today: string,
  lang: 'en' | 'ur' | 'roman' = 'en'
): Promise<Record<string, unknown>> {
  const systemPrompt = `You are an agricultural event extractor for Pakistani farms.
Extract farming events from the farmer's note and return a JSON object with key "events".
Each event must have: type (irrigation|fertilizer|pesticide|weather|observation),
product (string|null), quantity (number|null), unit (string|null),
occurred_at (YYYY-MM-DD, today is ${today}), date_certainty (exact|approximate|unknown),
symptom (string|null), confidence (0-1), source (farmer_text|farmer_voice).
Do not include diagnosis, only factual observations. Return JSON only.`;

  const response = await hfChatCompletion(
    [
      { role: 'system', content: systemPrompt },
      { role: 'user', content: `Note (lang: ${lang}): ${note}` },
    ],
    HF_MODELS.llm,
    { jsonMode: true }
  );

  try {
    return JSON.parse(response.content) as Record<string, unknown>;
  } catch {
    return { events: [] };
  }
}

// ── 2. STT — Whisper Large v3 ─────────────────────────────────────────────────

/**
 * Transcribe a WebM/WAV/MP3 audio Blob using HF-hosted Whisper.
 * Tries the OpenAI-compatible HF Router endpoint first, then the
 * direct Inference API binary endpoint as fallback.
 */
export async function hfTranscribeAudio(
  audioBlob: Blob,
  language: 'ur' | 'en' = 'ur',
  modelId: string = HF_MODELS.stt
): Promise<STTResponse> {
  const token = getHFToken();
  if (!token) throw new Error('HF_TOKEN not set.');

  // Try 1: OpenAI-compat HF Router
  try {
    const form = new FormData();
    form.append('file', audioBlob, 'clip.webm');
    form.append('model', modelId);
    form.append('language', language);
    form.append('response_format', 'json');

    const res = await fetch(`${HF_ROUTER_BASE}/audio/transcriptions`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
      body: form,
    });

    if (res.ok) {
      const data = await res.json();
      return { text: (data.text ?? '').trim(), language };
    }
  } catch {
    // fall through to binary endpoint
  }

  // Try 2: Direct HF Inference API binary POST
  const audioBuf = await audioBlob.arrayBuffer();
  const res2 = await fetch(`${HF_INFERENCE_BASE}/${modelId}`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': audioBlob.type || 'audio/webm',
    },
    body: audioBuf,
  });

  if (!res2.ok) {
    const errText = await res2.text().catch(() => '');
    throw new Error(`HF STT error ${res2.status}: ${errText.slice(0, 200)}`);
  }

  const data2 = await res2.json();
  if (typeof data2 === 'object' && 'text' in data2) {
    return { text: String(data2.text ?? '').trim(), language };
  }
  if (Array.isArray(data2) && data2[0]?.text) {
    return { text: String(data2[0].text).trim(), language };
  }

  return { text: String(data2).trim(), language };
}

// ── 3. Vision — Qwen2-VL-7B-Instruct ─────────────────────────────────────────

/**
 * Describe visible crop symptoms in an image using the VLM.
 * `imageBase64` should be a plain base64 string (no data-URL prefix needed).
 */
export async function hfObserveImage(
  imageBase64: string,
  mimeType: string = 'image/jpeg',
  modelId: string = HF_MODELS.vision
): Promise<VLMObservation> {
  const token = getHFToken();
  if (!token) throw new Error('HF_TOKEN not set.');

  const systemPrompt = `You are a crop symptom observer. Describe ONLY what is visually present in the image.
Do NOT diagnose diseases, do NOT say "caused by". Return JSON with keys:
leaf_color (string|null), pattern (string|null), spots (bool|null),
wilting (bool|null), affected_area (string|null),
symptom_description (1-2 factual sentences|null), notes (string|null).`;

  const body = {
    model: modelId,
    messages: [
      { role: 'system', content: systemPrompt },
      {
        role: 'user',
        content: [
          { type: 'image_url', image_url: { url: `data:${mimeType};base64,${imageBase64}` } },
          { type: 'text', text: 'Describe visible symptoms on the crop leaves.' },
        ],
      },
    ],
    temperature: 0,
    max_tokens: 512,
    response_format: { type: 'json_object' },
  };

  const res = await fetch(`${HF_ROUTER_BASE}/chat/completions`, {
    method: 'POST',
    headers: authHeaders(token),
    body: JSON.stringify(body),
  });

  if (!res.ok) {
    const errText = await res.text().catch(() => '');
    throw new Error(`HF Vision error ${res.status}: ${errText.slice(0, 200)}`);
  }

  const data = await res.json();
  const content = data.choices?.[0]?.message?.content ?? '{}';

  try {
    return JSON.parse(content) as VLMObservation;
  } catch {
    return {
      leaf_color: null,
      pattern: null,
      spots: null,
      wilting: null,
      affected_area: null,
      symptom_description: content.slice(0, 300),
      notes: null,
    };
  }
}

/**
 * Helper: convert a File or Blob to base64 string.
 */
export function fileToBase64(file: File | Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = reader.result as string;
      // Strip data URL prefix if present
      const base64 = result.includes(',') ? result.split(',')[1] : result;
      resolve(base64);
    };
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

// ── 4. TTS — facebook/mms-tts-urd-script-arabic ──────────────────────────────

/**
 * Convert Urdu text to speech using HF Inference API.
 * Returns an audio Blob (wav/mp3 depending on model output).
 */
export async function hfSpeakUrdu(
  text: string,
  modelId: string = HF_MODELS.tts
): Promise<Blob> {
  const token = getHFToken();
  if (!token) throw new Error('HF_TOKEN not set.');

  const res = await fetch(`${HF_INFERENCE_BASE}/${modelId}`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ inputs: text }),
  });

  if (!res.ok) {
    const errText = await res.text().catch(() => '');
    throw new Error(`HF TTS error ${res.status}: ${errText.slice(0, 200)}`);
  }

  return res.blob();
}

// ── 5. Model health / ping ────────────────────────────────────────────────────

/**
 * Ping one HF model and return its status.
 * Uses a minimal payload to verify the model is loaded.
 */
export async function pingHFModel(
  kind: keyof typeof HF_MODELS
): Promise<{ ok: boolean; latencyMs: number; error?: string }> {
  const token = getHFToken();
  if (!token) return { ok: false, latencyMs: 0, error: 'No HF token set' };

  const start = Date.now();

  try {
    if (kind === 'llm') {
      const res = await fetch(`${HF_ROUTER_BASE}/chat/completions`, {
        method: 'POST',
        headers: authHeaders(token),
        body: JSON.stringify({
          model: HF_MODELS.llm,
          messages: [{ role: 'user', content: 'ping' }],
          max_tokens: 1,
          temperature: 0,
        }),
        signal: AbortSignal.timeout(10000),
      });
      return { ok: res.ok || res.status === 422, latencyMs: Date.now() - start };
    }

    if (kind === 'vision') {
      // 1x1 white JPEG base64
      const tinyImg =
        '/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8U' +
        'HRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/2wBDAQkJCQwLDBgN' +
        'DRgyIRwhMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIy' +
        'MjL/wAARCAABAAEDASIAAhEBAxEB/8QAFgABAQEAAAAAAAAAAAAAAAAABgUE/8QAHhAA' +
        'AgIDAQEBAAAAAAAAAAAAAQIDBAUREiH/xAAUAQEAAAAAAAAAAAAAAAAAAAAA/8QAFBEBAA' +
        'AAAAAAAAAAAAAAAAAAAP/aAAwDAQACEQMRAD8Aq2mTHbHuLAy2OFjuMVfyFAH/2Q==';
      const res = await fetch(`${HF_ROUTER_BASE}/chat/completions`, {
        method: 'POST',
        headers: authHeaders(token),
        body: JSON.stringify({
          model: HF_MODELS.vision,
          messages: [
            {
              role: 'user',
              content: [
                { type: 'image_url', image_url: { url: `data:image/jpeg;base64,${tinyImg}` } },
                { type: 'text', text: 'ok?' },
              ],
            },
          ],
          max_tokens: 1,
          temperature: 0,
        }),
        signal: AbortSignal.timeout(15000),
      });
      return { ok: res.ok || res.status === 422, latencyMs: Date.now() - start };
    }

    if (kind === 'stt') {
      // tiny silent WAV (44 bytes)
      const silentWav = new Uint8Array([
        82,73,70,70,36,0,0,0,87,65,86,69,102,109,116,32,16,0,0,0,1,0,1,0,
        68,172,0,0,136,88,1,0,2,0,16,0,100,97,116,97,0,0,0,0,
      ]);
      const form = new FormData();
      form.append('file', new Blob([silentWav], { type: 'audio/wav' }), 'ping.wav');
      form.append('model', HF_MODELS.stt);
      form.append('response_format', 'json');
      const res = await fetch(`${HF_ROUTER_BASE}/audio/transcriptions`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
        body: form,
        signal: AbortSignal.timeout(15000),
      });
      return { ok: res.ok || res.status === 422, latencyMs: Date.now() - start };
    }

    if (kind === 'tts') {
      const res = await fetch(`${HF_INFERENCE_BASE}/${HF_MODELS.tts}`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ inputs: 'آزمائش' }),
        signal: AbortSignal.timeout(20000),
      });
      return { ok: res.ok, latencyMs: Date.now() - start };
    }
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : 'timeout';
    return { ok: false, latencyMs: Date.now() - start, error: msg };
  }

  return { ok: false, latencyMs: 0, error: 'Unknown kind' };
}

/**
 * Check all four HF models and return their status.
 */
export async function checkAllHFModels(): Promise<HFModelStatus[]> {
  const modelMeta: Array<{ id: keyof typeof HF_MODELS; label: string; task: string; icon: string }> = [
    { id: 'llm',    label: 'Qwen2.5-72B-Instruct',      task: 'Chat / Text Completion', icon: '🧠' },
    { id: 'stt',    label: 'Whisper Large v3',           task: 'Speech-to-Text (Urdu/English)', icon: '🎙️' },
    { id: 'vision', label: 'Qwen2-VL-7B-Instruct',       task: 'Vision / Crop Observation',     icon: '👁️' },
    { id: 'tts',    label: 'MMS TTS (Urdu Arabic Script)', task: 'Text-to-Speech (Urdu)',        icon: '🔊' },
  ];

  const results = await Promise.allSettled(
    modelMeta.map(async (meta) => {
      const ping = await pingHFModel(meta.id);
      return {
        id: meta.id,
        modelId: HF_MODELS[meta.id],
        label: meta.label,
        task: meta.task,
        icon: meta.icon,
        available: ping.ok,
        latencyMs: ping.latencyMs,
        error: ping.error,
      } satisfies HFModelStatus;
    })
  );

  return results.map((r, i) =>
    r.status === 'fulfilled'
      ? r.value
      : {
          id: modelMeta[i].id,
          modelId: HF_MODELS[modelMeta[i].id],
          label: modelMeta[i].label,
          task: modelMeta[i].task,
          icon: modelMeta[i].icon,
          available: false,
          error: r.reason instanceof Error ? r.reason.message : 'Failed',
        }
  );
}
