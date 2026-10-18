import React, { useState } from 'react';
import { 
  ShieldAlert, 
  CheckCircle2, 
  XCircle, 
  Play, 
  Sparkles, 
  FileCode
} from 'lucide-react';
import { BANNED_PATTERNS } from '../services/api';
import type { Language } from '../types';

interface VerifierInspectorProps {
  language?: Language;
}

export const VerifierInspector: React.FC<VerifierInspectorProps> = () => {
  const [testClaim, setTestClaim] = useState(
    'The tomatoes definitely have early blight fungal infection and you should spray 200ml Mancozeb per acre.'
  );
  const [testEventId, setTestEventId] = useState('E-005');
  const [verificationResult, setVerificationResult] = useState<{
    passed: boolean;
    errors: string[];
    bannedMatches: string[];
  } | null>(null);

  const sampleTestPhrases = [
    {
      label: '❌ Hallucinatory Diagnosis (Early Blight)',
      text: 'The tomato plants have an early blight fungus infection caused by excess watering.',
      hasCite: true,
    },
    {
      label: '❌ Chemical Treatment Prescription',
      text: 'The farmer should apply 250ml fungicide spray per acre immediately.',
      hasCite: true,
    },
    {
      label: '❌ Uncited Factual Statement',
      text: '45 mm of rain fell in the district yesterday.',
      hasCite: false,
    },
    {
      label: '✅ Permitted Evidence-Cited Statement',
      text: 'The records show fertilizer application increased by 100% (E-005) 7 days before yellowing was recorded.',
      hasCite: true,
    },
    {
      label: '✅ Permitted Nuanced Possibility',
      text: 'High rainfall (E-006) right before irrigation (E-007) may be worth investigating as a moisture stress factor.',
      hasCite: true,
    },
  ];

  const runVerification = (textToTest: string, eventIdToTest: string) => {
    const text = textToTest.trim();
    const errors: string[] = [];
    const bannedMatches: string[] = [];

    // 1. Citation check: Every factual claim must cite an event or photo
    const idRegex = /\b[EP]-\d{3,}\b/;
    const hasCite = idRegex.test(text) || Boolean(eventIdToTest.trim());
    if (!hasCite) {
      errors.push('Rule Violation: Claim makes factual assertions but provides NO event ID (E-###) citation.');
    }

    // 2. Check banned diagnosis and cause-as-fact wording
    for (const pat of BANNED_PATTERNS) {
      const match = text.match(pat);
      if (match) {
        bannedMatches.push(match[0]);
        errors.push(`Banned Wording Detected: "${match[0]}" violates anti-diagnosis guardrail (matches pattern ${pat.toString()}).`);
      }
    }

    // 3. Treatment / dosage recommendation check
    if (/\b(spray|dawai|fungicide|pesticide)\b.*\b(apply|use|spray|dalein)\b/i.test(text) || /\b\d+\s*(ml|g|kg)\b/i.test(text)) {
      errors.push('Prescription Guardrail: System is strictly forbidden from recommending chemical treatments or dosages.');
    }

    setVerificationResult({
      passed: errors.length === 0,
      errors,
      bannedMatches,
    });
  };

  return (
    <div style={{
      maxWidth: 1400,
      margin: '24px auto',
      padding: '0 24px',
      display: 'grid',
      gridTemplateColumns: '1.2fr 1fr',
      gap: 24,
      alignItems: 'start'
    }}>
      {/* Left Column: Interactive Verifier Sandbox */}
      <div className="glass-panel" style={{ padding: 24 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 16 }}>
          <ShieldAlert size={24} style={{ color: 'var(--amber-400)' }} />
          <div>
            <h2 style={{ fontSize: '1.2rem', fontWeight: 800 }}>
              Mechanical Verifier Sandbox
            </h2>
            <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
              Inspect how FasalNama mechanically filters AI hallucination and rejects ungrounded diagnoses.
            </p>
          </div>
        </div>

        {/* Quick test buttons */}
        <div style={{ marginBottom: 16 }}>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginBottom: 8, fontWeight: 600 }}>
            Choose a test case to evaluate against the verifier:
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {sampleTestPhrases.map((phrase, idx) => (
              <button
                key={idx}
                onClick={() => {
                  setTestClaim(phrase.text);
                  const cite = phrase.hasCite ? 'E-005' : '';
                  setTestEventId(cite);
                  runVerification(phrase.text, cite);
                }}
                style={{
                  textAlign: 'left',
                  background: 'rgba(30, 41, 59, 0.5)',
                  border: '1px solid var(--border-subtle)',
                  borderRadius: 'var(--radius-sm)',
                  padding: '8px 12px',
                  color: 'var(--text-secondary)',
                  fontSize: '0.8rem',
                  cursor: 'pointer',
                  transition: 'var(--transition)'
                }}
                onMouseOver={(e) => {
                  (e.currentTarget as HTMLElement).style.background = 'rgba(51, 65, 85, 0.7)';
                }}
                onMouseOut={(e) => {
                  (e.currentTarget as HTMLElement).style.background = 'rgba(30, 41, 59, 0.5)';
                }}
              >
                <div style={{ fontWeight: 700, color: phrase.label.startsWith('✅') ? 'var(--emerald-400)' : 'var(--rose-400)' }}>
                  {phrase.label}
                </div>
                <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: 2 }}>
                  "{phrase.text}"
                </div>
              </button>
            ))}
          </div>
        </div>

        {/* Custom Textarea for Sandbox */}
        <div style={{ marginBottom: 16 }}>
          <label style={{ display: 'block', fontSize: '0.75rem', color: 'var(--text-muted)', marginBottom: 6 }}>
            Type any candidate claim or LLM report sentence:
          </label>
          <textarea
            rows={3}
            value={testClaim}
            onChange={(e) => setTestClaim(e.target.value)}
            style={{
              width: '100%',
              background: 'rgba(15, 23, 42, 0.8)',
              border: '1px solid var(--border-medium)',
              borderRadius: 'var(--radius-md)',
              padding: '12px',
              color: '#fff',
              fontSize: '0.875rem',
              outline: 'none',
              lineHeight: 1.5
            }}
          />
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 20 }}>
          <div style={{ flex: 1 }}>
            <label style={{ display: 'block', fontSize: '0.75rem', color: 'var(--text-muted)', marginBottom: 4 }}>
              Cited Event ID (Optional if cited in text):
            </label>
            <input
              type="text"
              value={testEventId}
              placeholder="e.g. E-005"
              onChange={(e) => setTestEventId(e.target.value)}
              style={{
                width: '100%',
                background: 'rgba(15, 23, 42, 0.8)',
                border: '1px solid var(--border-medium)',
                borderRadius: 'var(--radius-sm)',
                padding: '6px 10px',
                color: '#fff',
                fontSize: '0.8rem'
              }}
            />
          </div>

          <button
            onClick={() => runVerification(testClaim, testEventId)}
            className="btn btn-primary"
            style={{ height: 38, marginTop: 18 }}
          >
            <Play size={15} />
            <span>Test Verifier</span>
          </button>
        </div>

        {/* Verification Verdict Box */}
        {verificationResult && (
          <div style={{
            background: verificationResult.passed ? 'rgba(16, 185, 129, 0.1)' : 'rgba(244, 63, 94, 0.1)',
            border: `1px solid ${verificationResult.passed ? 'var(--emerald-500)' : 'var(--rose-500)'}`,
            borderRadius: 'var(--radius-md)',
            padding: 16,
            animation: 'spotlightGlow 1.2s ease-out'
          }}>
            <div style={{
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              fontWeight: 800,
              fontSize: '0.95rem',
              color: verificationResult.passed ? 'var(--emerald-400)' : 'var(--rose-400)',
              marginBottom: 10
            }}>
              {verificationResult.passed ? (
                <>
                  <CheckCircle2 size={20} />
                  <span>VERIFIER PASS: Claim Approved (Cited & Deterministic)</span>
                </>
              ) : (
                <>
                  <XCircle size={20} />
                  <span>VERIFIER REJECT: Claim Blocked by Guardrails</span>
                </>
              )}
            </div>

            {verificationResult.passed ? (
              <p style={{ fontSize: '0.8rem', color: 'var(--emerald-400)', margin: 0 }}>
                This sentence complies with all FasalNama principles: it cites verifiable evidence, avoids claiming cause-as-fact, and makes no prohibited medical/chemical prescriptions.
              </p>
            ) : (
              <ul style={{ paddingLeft: 18, fontSize: '0.8rem', color: '#fecdd3', display: 'flex', flexDirection: 'column', gap: 6 }}>
                {verificationResult.errors.map((err, i) => (
                  <li key={i}>{err}</li>
                ))}
              </ul>
            )}
          </div>
        )}
      </div>

      {/* Right Column: Ground Truth & Principles */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
        {/* Anti-Diagnosis Principles Card */}
        <div className="glass-panel" style={{ padding: 20 }}>
          <h3 style={{ fontSize: '1rem', fontWeight: 800, color: '#fff', marginBottom: 12, display: 'flex', alignItems: 'center', gap: 8 }}>
            <FileCode size={18} style={{ color: 'var(--emerald-400)' }} />
            <span>Product Rules & Banned Patterns</span>
          </h3>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 12, fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
            <div style={{
              padding: '10px 14px',
              borderRadius: 'var(--radius-sm)',
              background: 'rgba(15, 23, 42, 0.7)',
              borderLeft: '3px solid var(--emerald-400)'
            }}>
              <strong style={{ color: '#fff' }}>Permitted Phrasing:</strong>
              <div style={{ marginTop: 4, color: 'var(--emerald-400)' }}>
                "The records show...", "May be worth investigating...", "Cannot be concluded because records are missing..."
              </div>
            </div>

            <div style={{
              padding: '10px 14px',
              borderRadius: 'var(--radius-sm)',
              background: 'rgba(15, 23, 42, 0.7)',
              borderLeft: '3px solid var(--rose-400)'
            }}>
              <strong style={{ color: '#fff' }}>Strictly Banned:</strong>
              <div style={{ marginTop: 4, color: '#fca5a5' }}>
                "is caused by", "the disease is", "blight", "fungus", "definitely", "pakka", "ye bimari hai", "spray karein"
              </div>
            </div>

            <div style={{
              padding: '10px 14px',
              borderRadius: 'var(--radius-sm)',
              background: 'rgba(15, 23, 42, 0.7)',
              borderLeft: '3px solid var(--amber-400)'
            }}>
              <strong style={{ color: '#fff' }}>Mandatory Closing Disclaimer:</strong>
              <div style={{ marginTop: 4, color: 'var(--amber-400)', fontStyle: 'italic' }}>
                "This is an evidence summary built from records, not a diagnosis."
              </div>
            </div>
          </div>
        </div>

        {/* Progressive Disclosure Architecture Card */}
        <div className="glass-panel" style={{ padding: 20 }}>
          <h3 style={{ fontSize: '1rem', fontWeight: 800, color: '#fff', marginBottom: 10, display: 'flex', alignItems: 'center', gap: 8 }}>
            <Sparkles size={18} style={{ color: 'var(--amber-400)' }} />
            <span>Why FasalNama Works</span>
          </h3>
          <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', lineHeight: 1.6 }}>
            Most AI agricultural tools guess diseases from blurry photos and hallucinate dangerous chemical sprays. FasalNama flips this: 
            <strong> code computes the dates, intervals, and gaps</strong>; the model only translates and formats; the verifier mechanically vetoes any ungrounded claim.
          </p>
        </div>
      </div>
    </div>
  );
};
