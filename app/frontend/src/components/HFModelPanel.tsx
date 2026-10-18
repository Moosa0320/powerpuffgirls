/**
 * HuggingFace Model Panel
 *
 * Shows the 4 HF-hosted AI models used by FasalNama:
 * LLM · STT · Vision · TTS
 *
 * Lets the user enter their HF token (stored in sessionStorage only),
 * ping each model and see real latency + status.
 */
import React, { useState, useCallback } from 'react';
import {
  Brain,
  Mic,
  Eye,
  Volume2,
  CheckCircle2,
  XCircle,
  RefreshCw,
  Lock,
  Unlock,
  ExternalLink,
  Zap,
  AlertCircle,
  ChevronDown,
  ChevronUp,
} from 'lucide-react';
import {
  HF_MODELS,
  checkAllHFModels,
  getHFToken,
  hasHFToken,
  setHFToken,
  type HFModelStatus,
} from '../services/hfApi';

interface HFModelPanelProps {
  language?: 'en' | 'ur' | 'roman';
}

const MODEL_ICONS: Record<string, React.ReactNode> = {
  llm:    <Brain size={20} />,
  stt:    <Mic size={20} />,
  vision: <Eye size={20} />,
  tts:    <Volume2 size={20} />,
};

const INITIAL_STATUSES: HFModelStatus[] = [
  { id: 'llm',    modelId: HF_MODELS.llm,    label: 'Qwen2.5-72B-Instruct',        task: 'Chat / Text Completion',         icon: '🧠', available: false },
  { id: 'stt',    modelId: HF_MODELS.stt,    label: 'Whisper Large v3',            task: 'Speech-to-Text (Urdu/English)',  icon: '🎙️', available: false },
  { id: 'vision', modelId: HF_MODELS.vision, label: 'Qwen2-VL-7B-Instruct',        task: 'Vision / Crop Observation',      icon: '👁️', available: false },
  { id: 'tts',    modelId: HF_MODELS.tts,    label: 'MMS TTS (Urdu Arabic Script)', task: 'Text-to-Speech (Urdu)',          icon: '🔊', available: false },
];

export const HFModelPanel: React.FC<HFModelPanelProps> = ({ language = 'en' }) => {
  const [expanded, setExpanded] = useState(false);
  const [token, setToken]       = useState(getHFToken());
  const [showToken, setShowToken] = useState(false);
  const [statuses, setStatuses] = useState<HFModelStatus[]>(INITIAL_STATUSES);
  const [checking, setChecking] = useState(false);
  const [lastChecked, setLastChecked] = useState<Date | null>(null);
  const [tokenSaved, setTokenSaved] = useState(hasHFToken());

  const handleSaveToken = () => {
    setHFToken(token);
    setTokenSaved(!!token.trim());
  };

  const handleClearToken = () => {
    setToken('');
    setHFToken('');
    setTokenSaved(false);
  };

  const handleCheckAll = useCallback(async () => {
    if (checking) return;
    if (!hasHFToken()) {
      alert('Please enter and save your Hugging Face token first.');
      return;
    }
    setChecking(true);
    // Reset statuses to "checking" state
    setStatuses((prev) => prev.map((s) => ({ ...s, available: false, latencyMs: undefined, error: undefined })));
    try {
      const results = await checkAllHFModels();
      setStatuses(results);
      setLastChecked(new Date());
    } catch (e) {
      console.error('HF check failed', e);
    } finally {
      setChecking(false);
    }
  }, [checking]);

  const anyAvailable = statuses.some((s) => s.available);

  return (
    <div style={{
      background: 'linear-gradient(135deg, rgba(17,24,39,0.95) 0%, rgba(12,18,34,0.98) 100%)',
      border: '1px solid rgba(99,102,241,0.3)',
      borderRadius: 16,
      overflow: 'hidden',
      marginBottom: 24,
      boxShadow: '0 4px 24px rgba(99,102,241,0.08)',
    }}>
      {/* ── Header ─────────────────────────────────────────────────────────── */}
      <button
        onClick={() => setExpanded((p) => !p)}
        style={{
          width: '100%',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '16px 20px',
          background: 'transparent',
          border: 'none',
          cursor: 'pointer',
          color: '#fff',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          {/* HF logo-ish */}
          <div style={{
            width: 36, height: 36, borderRadius: 10,
            background: 'linear-gradient(135deg, #ff9d00, #ff6b00)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 18, fontWeight: 800, color: '#fff',
            boxShadow: '0 0 12px rgba(255,157,0,0.4)',
          }}>🤗</div>
          <div style={{ textAlign: 'left' }}>
            <div style={{ fontWeight: 700, fontSize: '0.95rem', color: '#fff' }}>
              Hugging Face AI Models
            </div>
            <div style={{ fontSize: '0.75rem', color: 'rgba(255,255,255,0.5)' }}>
              {anyAvailable
                ? `${statuses.filter((s) => s.available).length}/4 models reachable`
                : tokenSaved
                ? 'Token saved — click to check models'
                : 'Enter HF token to enable AI features'}
            </div>
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {anyAvailable && (
            <span style={{
              background: 'rgba(52,211,153,0.15)',
              color: '#34d399',
              borderRadius: 8,
              padding: '2px 10px',
              fontSize: '0.72rem',
              fontWeight: 700,
              border: '1px solid rgba(52,211,153,0.25)',
            }}>LIVE</span>
          )}
          {expanded ? <ChevronUp size={16} color="rgba(255,255,255,0.4)" /> : <ChevronDown size={16} color="rgba(255,255,255,0.4)" />}
        </div>
      </button>

      {/* ── Expanded body ───────────────────────────────────────────────────── */}
      {expanded && (
        <div style={{ padding: '0 20px 20px' }}>
          {/* Token input */}
          <div style={{
            background: 'rgba(255,255,255,0.04)',
            border: '1px solid rgba(255,255,255,0.08)',
            borderRadius: 12,
            padding: 16,
            marginBottom: 16,
          }}>
            <div style={{ fontSize: '0.8rem', color: 'rgba(255,255,255,0.6)', marginBottom: 8, display: 'flex', alignItems: 'center', gap: 6 }}>
              <Lock size={13} />
              HuggingFace Token (hf_…) — stored in session only, never sent to any server except HF
            </div>
            <div style={{ display: 'flex', gap: 8 }}>
              <input
                type={showToken ? 'text' : 'password'}
                value={token}
                onChange={(e) => setToken(e.target.value)}
                placeholder="hf_xxxxxxxxxxxxxxxxxxxx"
                style={{
                  flex: 1,
                  background: 'rgba(0,0,0,0.4)',
                  border: '1px solid rgba(255,255,255,0.12)',
                  borderRadius: 8,
                  padding: '8px 12px',
                  color: '#fff',
                  fontSize: '0.85rem',
                  outline: 'none',
                  fontFamily: 'monospace',
                }}
              />
              <button
                onClick={() => setShowToken((p) => !p)}
                title={showToken ? 'Hide' : 'Show'}
                style={{
                  background: 'rgba(255,255,255,0.06)',
                  border: '1px solid rgba(255,255,255,0.1)',
                  borderRadius: 8,
                  padding: '0 12px',
                  color: 'rgba(255,255,255,0.5)',
                  cursor: 'pointer',
                }}
              >
                {showToken ? <Lock size={14} /> : <Unlock size={14} />}
              </button>
              <button
                onClick={handleSaveToken}
                style={{
                  background: 'rgba(99,102,241,0.2)',
                  border: '1px solid rgba(99,102,241,0.4)',
                  borderRadius: 8,
                  padding: '0 14px',
                  color: '#a5b4fc',
                  cursor: 'pointer',
                  fontSize: '0.8rem',
                  fontWeight: 600,
                }}
              >Save</button>
              {tokenSaved && (
                <button
                  onClick={handleClearToken}
                  style={{
                    background: 'rgba(239,68,68,0.1)',
                    border: '1px solid rgba(239,68,68,0.3)',
                    borderRadius: 8,
                    padding: '0 12px',
                    color: '#f87171',
                    cursor: 'pointer',
                    fontSize: '0.8rem',
                  }}
                >Clear</button>
              )}
            </div>
            <div style={{ marginTop: 8, fontSize: '0.72rem', color: 'rgba(255,255,255,0.35)', display: 'flex', alignItems: 'center', gap: 6 }}>
              <a
                href="https://huggingface.co/settings/tokens"
                target="_blank"
                rel="noopener noreferrer"
                style={{ color: '#818cf8', display: 'flex', alignItems: 'center', gap: 3 }}
              >
                Get token at huggingface.co/settings/tokens <ExternalLink size={10} />
              </a>
              · Needs Inference API access (free tier works)
            </div>
          </div>

          {/* Check all button */}
          <button
            onClick={handleCheckAll}
            disabled={checking || !tokenSaved}
            style={{
              width: '100%',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: 8,
              padding: '10px 0',
              borderRadius: 10,
              border: '1px solid rgba(99,102,241,0.4)',
              background: checking
                ? 'rgba(99,102,241,0.08)'
                : 'linear-gradient(135deg, rgba(99,102,241,0.2), rgba(139,92,246,0.2))',
              color: tokenSaved ? '#a5b4fc' : 'rgba(255,255,255,0.3)',
              cursor: checking || !tokenSaved ? 'not-allowed' : 'pointer',
              fontSize: '0.85rem',
              fontWeight: 600,
              marginBottom: 16,
              transition: 'all 0.2s',
            }}
          >
            <RefreshCw size={15} style={{ animation: checking ? 'spin 1s linear infinite' : 'none' }} />
            {checking ? 'Checking all models…' : 'Ping All 4 HF Models'}
            {lastChecked && !checking && (
              <span style={{ fontSize: '0.7rem', color: 'rgba(255,255,255,0.35)', fontWeight: 400 }}>
                last: {lastChecked.toLocaleTimeString()}
              </span>
            )}
          </button>

          {/* Model cards */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))', gap: 12 }}>
            {statuses.map((model) => (
              <ModelCard key={model.id} model={model} checking={checking} />
            ))}
          </div>

          {/* Info note */}
          <div style={{
            marginTop: 16,
            padding: '10px 14px',
            background: 'rgba(251,191,36,0.06)',
            border: '1px solid rgba(251,191,36,0.15)',
            borderRadius: 10,
            fontSize: '0.75rem',
            color: 'rgba(255,255,255,0.5)',
            display: 'flex',
            gap: 8,
          }}>
            <AlertCircle size={13} style={{ flexShrink: 0, color: '#fbbf24', marginTop: 2 }} />
            <span>
              {language === 'ur'
                ? 'یہ ماڈل HuggingFace پر ہوسٹ ہیں اور آپ کے HF ٹوکن کے ذریعے استعمال ہوتے ہیں۔ backend بھی انہی ماڈلز کو استعمال کرتا ہے۔'
                : language === 'roman'
                ? 'Yeh models HuggingFace par host hain aur HF_TOKEN se chalte hain. Backend bhi yehi models use karta hai.'
                : 'These open-weight models are hosted on HuggingFace Inference API and consumed via your HF_TOKEN. The backend (harness/) uses the same models. No data is stored by HuggingFace beyond the API call.'}
            </span>
          </div>
        </div>
      )}

      <style>{`
        @keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
        @keyframes pulse-dot { 0%,100% { opacity: 1; } 50% { opacity: 0.3; } }
      `}</style>
    </div>
  );
};

// ── Model Card ────────────────────────────────────────────────────────────────

interface ModelCardProps {
  model: HFModelStatus;
  checking: boolean;
}

const ModelCard: React.FC<ModelCardProps> = ({ model, checking }) => {
  const statusColor = checking
    ? '#94a3b8'
    : model.available
    ? '#34d399'
    : '#f87171';

  const bgColor = checking
    ? 'rgba(148,163,184,0.05)'
    : model.available
    ? 'rgba(52,211,153,0.05)'
    : 'rgba(248,113,113,0.04)';

  const borderColor = checking
    ? 'rgba(148,163,184,0.15)'
    : model.available
    ? 'rgba(52,211,153,0.2)'
    : 'rgba(248,113,113,0.15)';

  return (
    <div style={{
      background: bgColor,
      border: `1px solid ${borderColor}`,
      borderRadius: 12,
      padding: 14,
      transition: 'all 0.3s',
    }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 8 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ color: statusColor, display: 'flex', alignItems: 'center' }}>
            {MODEL_ICONS[model.id]}
          </span>
          <div>
            <div style={{ fontWeight: 700, fontSize: '0.82rem', color: '#fff' }}>
              {model.label}
            </div>
            <div style={{ fontSize: '0.7rem', color: 'rgba(255,255,255,0.45)', marginTop: 1 }}>
              {model.task}
            </div>
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
          {checking ? (
            <div style={{
              width: 8, height: 8, borderRadius: '50%',
              background: '#94a3b8',
              animation: 'pulse-dot 1s ease-in-out infinite',
            }} />
          ) : model.available ? (
            <CheckCircle2 size={16} color="#34d399" />
          ) : (
            <XCircle size={16} color="#f87171" />
          )}
        </div>
      </div>

      <div style={{
        fontFamily: 'monospace',
        fontSize: '0.68rem',
        color: 'rgba(255,255,255,0.35)',
        wordBreak: 'break-all',
        marginBottom: 6,
      }}>
        {model.modelId}
      </div>

      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <span style={{
          fontSize: '0.72rem',
          fontWeight: 700,
          color: model.available ? '#34d399' : model.error ? '#f87171' : 'rgba(255,255,255,0.35)',
        }}>
          {checking
            ? 'pinging…'
            : model.available
            ? '✓ Reachable'
            : model.error
            ? `✗ ${model.error.slice(0, 30)}`
            : '— not checked'}
        </span>

        {model.latencyMs != null && model.available && (
          <span style={{
            display: 'flex', alignItems: 'center', gap: 3,
            fontSize: '0.7rem', color: '#fbbf24',
          }}>
            <Zap size={10} />
            {model.latencyMs}ms
          </span>
        )}
      </div>

      <a
        href={`https://huggingface.co/${model.modelId}`}
        target="_blank"
        rel="noopener noreferrer"
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 4,
          fontSize: '0.68rem',
          color: '#818cf8',
          marginTop: 8,
          textDecoration: 'none',
        }}
      >
        View on HuggingFace <ExternalLink size={9} />
      </a>
    </div>
  );
};

export default HFModelPanel;
