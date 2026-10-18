import React, { useState, useEffect } from 'react';
import { 
  Mic, 
  MicOff, 
  Sparkles, 
  CheckCircle2, 
  Trash2, 
  Leaf, 
  Droplet, 
  Zap, 
  CloudRain, 
  Eye, 
  HelpCircle
} from 'lucide-react';
import type { DateCertainty, EventType, Field, Language, ProposedEvent } from '../types';
import { FasalNamaAPI, normalizeUnit } from '../services/api';
import confetti from 'canvas-confetti';

interface EventLoggerProps {
  currentField: Field | null;
  language: Language;
  onEventConfirmed: () => void;
}

export const EventLogger: React.FC<EventLoggerProps> = ({
  currentField,
  language,
  onEventConfirmed,
}) => {
  const [inputText, setInputText] = useState('');
  const [isRecording, setIsRecording] = useState(false);
  const [recordingSeconds, setRecordingSeconds] = useState(0);
  const [isParsing, setIsParsing] = useState(false);
  const [proposals, setProposals] = useState<ProposedEvent[]>([]);
  const [successToast, setSuccessToast] = useState<string | null>(null);

  // Quick Agro Prompts
  const quickPrompts = [
    { text: 'aaj 2 bori urea dali', label: '2 bori Urea (Today)', tag: 'fertilizer' },
    { text: 'kal khet ko pani diya 1 tanki', label: '1 tanki Irrigation (Yesterday)', tag: 'irrigation' },
    { text: 'parson spray kiya tha keeron ke liye', label: 'Pesticide Spray (2 days ago)', tag: 'pesticide' },
    { text: 'tamatar ke nichlay patte peele ho rahe hain', label: 'Yellow Leaves (Observation)', tag: 'observation' },
    { text: '45 mm barish hui tez hawa ke sath', label: '45 mm Rainfall (Weather)', tag: 'weather' },
    { text: 'آج دو بوری یوریا ڈالی', label: 'Urdu: دو بوری یوریا', tag: 'fertilizer' },
  ];

  // Voice recording simulation with 30s timer
  useEffect(() => {
    let timer: number;
    if (isRecording) {
      timer = window.setInterval(() => {
        setRecordingSeconds((prev) => {
          if (prev >= 29) {
            handleStopRecording();
            return 30;
          }
          return prev + 1;
        });
      }, 1000);
    } else {
      setRecordingSeconds(0);
    }
    return () => clearInterval(timer);
  }, [isRecording]);

  const handleStartRecording = () => {
    setIsRecording(true);
    setRecordingSeconds(0);
  };

  const handleStopRecording = () => {
    setIsRecording(false);
    // Simulate STT transcribe result with agro initial_prompt
    const sampleVoicePhrases = [
      'audio: kal shaam ko do bori urea dali thi',
      'audio: pichle hafte canal se 1 tanki pani lagaya tha',
      'audio: parson tamatar ke patte peele nazar aaye',
      'audio: takreeban do din pehle spray kiya tha',
    ];
    const picked = sampleVoicePhrases[Math.floor(Math.random() * sampleVoicePhrases.length)];
    setInputText(picked);
  };

  const handleParse = async () => {
    if (!inputText.trim()) return;
    setIsParsing(true);
    try {
      const results = await FasalNamaAPI.parseFarmerNote(inputText);
      setProposals(results);
    } catch (err) {
      console.error('Parse failed', err);
    } finally {
      setIsParsing(false);
    }
  };

  const handleConfirmProposal = async (index: number) => {
    if (!currentField) return;
    const item = proposals[index];
    try {
      const saved = await FasalNamaAPI.confirmAndSaveEvent(currentField.id, item);
      // Trigger subtle celebration
      confetti({
        particleCount: 40,
        spread: 60,
        origin: { y: 0.7 },
        colors: ['#10b981', '#34d399', '#f59e0b'],
      });

      setSuccessToast(`Saved to Timeline as ${saved.display_id} (${saved.type})!`);
      setTimeout(() => setSuccessToast(null), 4000);

      // Remove from proposals
      setProposals((prev) => prev.filter((_, i) => i !== index));
      if (proposals.length === 1) {
        setInputText('');
      }
      onEventConfirmed();
    } catch (err) {
      console.error('Save failed', err);
    }
  };

  const handleUpdateProposal = (index: number, fieldKey: keyof ProposedEvent, value: any) => {
    setProposals((prev) => {
      const next = [...prev];
      next[index] = { ...next[index], [fieldKey]: value };
      return next;
    });
  };

  const handleDeleteProposal = (index: number) => {
    setProposals((prev) => prev.filter((_, i) => i !== index));
  };

  const getEventIcon = (type: EventType) => {
    switch (type) {
      case 'fertilizer': return <Zap size={16} className="text-amber-400" />;
      case 'irrigation': return <Droplet size={16} className="text-cyan-400" />;
      case 'planting': return <Leaf size={16} className="text-emerald-400" />;
      case 'weather': return <CloudRain size={16} className="text-blue-400" />;
      case 'observation': return <Eye size={16} className="text-rose-400" />;
      default: return <Sparkles size={16} />;
    }
  };

  return (
    <div style={{
      maxWidth: 1400,
      margin: '24px auto',
      padding: '0 24px',
      display: 'grid',
      gridTemplateColumns: proposals.length > 0 ? '1fr 1fr' : '1fr',
      gap: 24,
      transition: 'var(--transition)'
    }}>
      {/* Left Column: Multi-Modal Logger */}
      <div className="glass-panel" style={{ padding: 24 }}>
        {/* Header Title */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
          <div>
            <h2 style={{ fontSize: '1.25rem', fontWeight: 800, color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: 10 }}>
              <Mic size={22} style={{ color: 'var(--emerald-400)' }} />
              <span>{language === 'ur' ? 'کھیت کی ڈائری لاگ کریں' : 'Log Field Activity'}</span>
            </h2>
            <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
              {language === 'ur' 
                ? 'اردو، رومن یا انگریزی میں بولیں یا لکھیں۔ اے آئی تبدیلیاں نکالے گا، مگر آپ کی اجازت کے بغیر کچھ محفوظ نہیں ہوگا۔'
                : 'Speak or type in Urdu, Roman Urdu, or English. Parsed into structured proposals — nothing saved until you confirm.'}
            </p>
          </div>

          <div style={{
            background: 'rgba(16, 185, 129, 0.1)',
            border: '1px solid rgba(16, 185, 129, 0.25)',
            borderRadius: 'var(--radius-full)',
            padding: '4px 12px',
            fontSize: '0.75rem',
            color: 'var(--emerald-400)',
            fontWeight: 700
          }}>
            Target: {currentField?.name || 'Selected Field'}
          </div>
        </div>

        {/* Success Toast */}
        {successToast && (
          <div style={{
            background: 'rgba(16, 185, 129, 0.2)',
            border: '1px solid var(--emerald-500)',
            color: 'var(--emerald-400)',
            padding: '10px 16px',
            borderRadius: 'var(--radius-md)',
            marginBottom: 16,
            display: 'flex',
            alignItems: 'center',
            gap: 10,
            fontSize: '0.85rem',
            fontWeight: 600,
            animation: 'spotlightGlow 1.5s ease-out'
          }}>
            <CheckCircle2 size={18} />
            <span>{successToast}</span>
          </div>
        )}

        {/* Voice Recording Control */}
        <div style={{
          background: isRecording ? 'rgba(244, 63, 94, 0.1)' : 'rgba(30, 41, 59, 0.5)',
          border: `1px solid ${isRecording ? 'var(--rose-500)' : 'var(--border-subtle)'}`,
          borderRadius: 'var(--radius-lg)',
          padding: '16px',
          marginBottom: 18,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 16
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
            <button
              onClick={isRecording ? handleStopRecording : handleStartRecording}
              style={{
                width: 52,
                height: 52,
                borderRadius: '50%',
                background: isRecording 
                  ? 'linear-gradient(135deg, #f43f5e 0%, #e11d48 100%)' 
                  : 'linear-gradient(135deg, var(--emerald-600) 0%, var(--emerald-500) 100%)',
                border: 'none',
                color: '#fff',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                cursor: 'pointer',
                boxShadow: isRecording ? '0 0 20px rgba(244, 63, 94, 0.5)' : '0 0 15px var(--emerald-glow)',
                transition: 'var(--transition)'
              }}
              title={isRecording ? 'Stop Recording' : 'Record Voice in Urdu/English'}
            >
              {isRecording ? <MicOff size={24} /> : <Mic size={24} />}
            </button>

            <div>
              <div style={{ fontWeight: 700, fontSize: '0.9rem', color: isRecording ? 'var(--rose-400)' : 'var(--text-primary)' }}>
                {isRecording ? `Recording Audio (${recordingSeconds}s / 30s max)...` : 'Voice Input (STT)'}
              </div>
              <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                {isRecording 
                  ? 'Speaking in Urdu / Roman Urdu / English. Silence trimmed automatically.' 
                  : 'Click mic to speak your irrigation, fertilizer or symptom note.'}
              </div>
            </div>
          </div>

          {isRecording && (
            <div className="waveform-container">
              <span className="waveform-bar" />
              <span className="waveform-bar" />
              <span className="waveform-bar" />
              <span className="waveform-bar" />
              <span className="waveform-bar" />
              <span className="waveform-bar" />
            </div>
          )}
        </div>

        {/* Text Input Area */}
        <div style={{ position: 'relative', marginBottom: 16 }}>
          <textarea
            value={inputText}
            onChange={(e) => setInputText(e.target.value)}
            placeholder={
              language === 'ur'
                ? 'یہاں لکھیں، مثلاً: "آج دو بوری یوریا ڈالی" یا "کل کھیت کو پانی دیا" یا "ٹماٹر کے پتے پیلے ہو رہے ہیں"...'
                : 'Enter note in Roman Urdu, Urdu, or English. E.g. "aaj 2 bori urea dali" or "kal 1 tanki pani lagaya"...'
            }
            rows={4}
            style={{
              width: '100%',
              background: 'rgba(15, 23, 42, 0.8)',
              border: '1px solid var(--border-medium)',
              borderRadius: 'var(--radius-md)',
              padding: '14px',
              color: 'var(--text-primary)',
              fontSize: '0.925rem',
              outline: 'none',
              resize: 'vertical',
              fontFamily: /[\u0600-\u06FF]/.test(inputText) ? 'var(--font-urdu), sans-serif' : 'inherit',
              lineHeight: 1.6
            }}
          />
        </div>

        {/* Quick Example Chips */}
        <div style={{ marginBottom: 20 }}>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginBottom: 8, fontWeight: 600 }}>
            Quick Examples (Click to test):
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
            {quickPrompts.map((p, idx) => (
              <button
                key={idx}
                onClick={() => setInputText(p.text)}
                style={{
                  background: 'rgba(30, 41, 59, 0.5)',
                  border: '1px solid var(--border-subtle)',
                  borderRadius: 'var(--radius-full)',
                  padding: '5px 12px',
                  color: 'var(--text-secondary)',
                  fontSize: '0.75rem',
                  cursor: 'pointer',
                  transition: 'var(--transition)',
                  fontFamily: p.text.includes('یوریا') ? 'var(--font-urdu), sans-serif' : 'inherit'
                }}
                onMouseOver={(e) => {
                  (e.currentTarget as HTMLElement).style.borderColor = 'var(--emerald-500)';
                  (e.currentTarget as HTMLElement).style.color = '#fff';
                }}
                onMouseOut={(e) => {
                  (e.currentTarget as HTMLElement).style.borderColor = 'var(--border-subtle)';
                  (e.currentTarget as HTMLElement).style.color = 'var(--text-secondary)';
                }}
              >
                {p.label}
              </button>
            ))}
          </div>
        </div>

        {/* Parse Action Button */}
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 12 }}>
          {inputText && (
            <button
              onClick={() => setInputText('')}
              className="btn btn-secondary"
            >
              Clear
            </button>
          )}

          <button
            onClick={handleParse}
            disabled={!inputText.trim() || isParsing}
            className="btn btn-primary"
            style={{ minWidth: 160 }}
          >
            {isParsing ? (
              <>
                <span className="pulse-dot green" />
                <span>Parsing with LLM...</span>
              </>
            ) : (
              <>
                <Sparkles size={16} />
                <span>Extract Proposed Events</span>
              </>
            )}
          </button>
        </div>

        {/* Principle Alert Box */}
        <div style={{
          marginTop: 24,
          padding: '12px 16px',
          background: 'rgba(16, 185, 129, 0.05)',
          borderLeft: '3px solid var(--emerald-500)',
          borderRadius: '0 var(--radius-md) var(--radius-md) 0',
          fontSize: '0.75rem',
          color: 'var(--text-secondary)',
          display: 'flex',
          alignItems: 'flex-start',
          gap: 10
        }}>
          <HelpCircle size={16} style={{ color: 'var(--emerald-400)', flexShrink: 0, marginTop: 2 }} />
          <div>
            <strong>FasalNama Verification Rule:</strong> The LLM resolves relative dates (e.g. <em>parson</em> = 2 days ago) into calendar dates and standardizes units (e.g. <em>bori</em> = 50kg), but <strong>never</strong> commits data directly. You must review and confirm below.
          </div>
        </div>
      </div>

      {/* Right Column: Proposed Events Confirmation Tray */}
      {proposals.length > 0 && (
        <div className="glass-panel" style={{ padding: 24, borderColor: 'var(--emerald-500)' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
            <div>
              <h3 style={{ fontSize: '1.15rem', fontWeight: 800, color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: 8 }}>
                <CheckCircle2 size={20} style={{ color: 'var(--emerald-400)' }} />
                <span>Proposed Events ({proposals.length})</span>
              </h3>
              <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                Review, adjust fields, and click "Confirm" to assign official event ID.
              </p>
            </div>

            <span style={{
              background: 'rgba(245, 158, 11, 0.15)',
              color: 'var(--amber-400)',
              border: '1px solid rgba(245, 158, 11, 0.3)',
              borderRadius: 'var(--radius-full)',
              padding: '3px 10px',
              fontSize: '0.7rem',
              fontWeight: 700
            }}>
              Awaiting Farmer Approval
            </span>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            {proposals.map((item, idx) => {
              const norm = normalizeUnit(item.quantity, item.unit);
              return (
                <div 
                  key={idx}
                  style={{
                    background: 'rgba(30, 41, 59, 0.75)',
                    border: '1px solid var(--border-medium)',
                    borderRadius: 'var(--radius-md)',
                    padding: '16px',
                    position: 'relative'
                  }}
                >
                  {/* Top Bar of Proposal Card */}
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <span className={`badge badge-${item.type}`}>
                        {getEventIcon(item.type)}
                        {item.type}
                      </span>

                      <span style={{
                        fontSize: '0.7rem',
                        color: 'var(--text-muted)',
                        background: 'rgba(255, 255, 255, 0.05)',
                        padding: '2px 6px',
                        borderRadius: 'var(--radius-sm)'
                      }}>
                        Source: {item.source}
                      </span>
                    </div>

                    <button
                      onClick={() => handleDeleteProposal(idx)}
                      title="Discard proposal"
                      style={{
                        background: 'transparent',
                        border: 'none',
                        color: 'var(--text-muted)',
                        cursor: 'pointer',
                        padding: 4
                      }}
                    >
                      <Trash2 size={16} />
                    </button>
                  </div>

                  {/* Editable Proposal Fields Grid */}
                  <div style={{
                    display: 'grid',
                    gridTemplateColumns: '1fr 1fr',
                    gap: 12,
                    marginBottom: 12,
                    fontSize: '0.8rem'
                  }}>
                    {/* Occurred At Date */}
                    <div>
                      <label style={{ display: 'block', color: 'var(--text-muted)', fontSize: '0.7rem', marginBottom: 4 }}>
                        Date (Calendar Resolved)
                      </label>
                      <input
                        type="date"
                        value={item.occurred_at || ''}
                        onChange={(e) => handleUpdateProposal(idx, 'occurred_at', e.target.value)}
                        style={{
                          width: '100%',
                          background: '#0f172a',
                          border: '1px solid var(--border-subtle)',
                          borderRadius: 'var(--radius-sm)',
                          padding: '6px 8px',
                          color: '#fff',
                          fontSize: '0.8rem'
                        }}
                      />
                    </div>

                    {/* Date Certainty */}
                    <div>
                      <label style={{ display: 'block', color: 'var(--text-muted)', fontSize: '0.7rem', marginBottom: 4 }}>
                        Certainty
                      </label>
                      <select
                        value={item.date_certainty}
                        onChange={(e) => handleUpdateProposal(idx, 'date_certainty', e.target.value as DateCertainty)}
                        style={{
                          width: '100%',
                          background: '#0f172a',
                          border: '1px solid var(--border-subtle)',
                          borderRadius: 'var(--radius-sm)',
                          padding: '6px 8px',
                          color: '#fff',
                          fontSize: '0.8rem'
                        }}
                      >
                        <option value="exact">Exact (قطعی)</option>
                        <option value="approximate">Approximate (تقریبی)</option>
                        <option value="unknown">Unknown (نامعلوم)</option>
                      </select>
                    </div>

                    {/* Product */}
                    <div>
                      <label style={{ display: 'block', color: 'var(--text-muted)', fontSize: '0.7rem', marginBottom: 4 }}>
                        Product / Material
                      </label>
                      <input
                        type="text"
                        value={item.product || ''}
                        placeholder="e.g. Urea, DAP, spray"
                        onChange={(e) => handleUpdateProposal(idx, 'product', e.target.value)}
                        style={{
                          width: '100%',
                          background: '#0f172a',
                          border: '1px solid var(--border-subtle)',
                          borderRadius: 'var(--radius-sm)',
                          padding: '6px 8px',
                          color: '#fff',
                          fontSize: '0.8rem'
                        }}
                      />
                    </div>

                    {/* Quantity & Unit */}
                    <div>
                      <label style={{ display: 'block', color: 'var(--text-muted)', fontSize: '0.7rem', marginBottom: 4 }}>
                        Quantity & Unit
                      </label>
                      <div style={{ display: 'flex', gap: 6 }}>
                        <input
                          type="number"
                          value={item.quantity ?? ''}
                          placeholder="Amount"
                          onChange={(e) => handleUpdateProposal(idx, 'quantity', e.target.value ? parseFloat(e.target.value) : null)}
                          style={{
                            flex: 1,
                            background: '#0f172a',
                            border: '1px solid var(--border-subtle)',
                            borderRadius: 'var(--radius-sm)',
                            padding: '6px 8px',
                            color: '#fff',
                            fontSize: '0.8rem'
                          }}
                        />
                        <input
                          type="text"
                          value={item.unit || ''}
                          placeholder="bori, tanki, kg"
                          onChange={(e) => handleUpdateProposal(idx, 'unit', e.target.value)}
                          style={{
                            width: 70,
                            background: '#0f172a',
                            border: '1px solid var(--border-subtle)',
                            borderRadius: 'var(--radius-sm)',
                            padding: '6px 8px',
                            color: '#fff',
                            fontSize: '0.8rem'
                          }}
                        />
                      </div>
                    </div>
                  </div>

                  {/* Symptom Note if present */}
                  {item.symptom && (
                    <div style={{
                      background: 'rgba(244, 63, 94, 0.08)',
                      border: '1px solid rgba(244, 63, 94, 0.2)',
                      padding: '8px 12px',
                      borderRadius: 'var(--radius-sm)',
                      fontSize: '0.75rem',
                      color: 'var(--rose-400)',
                      marginBottom: 12
                    }}>
                      <strong>Farmer's Observed Symptom:</strong> "{item.symptom}"
                    </div>
                  )}

                  {/* Normalized Unit Conversion Pill */}
                  {norm.quantity != null && norm.unit && norm.unit !== item.unit && (
                    <div style={{ fontSize: '0.7rem', color: 'var(--emerald-400)', marginBottom: 12 }}>
                      ℹ️ Engine canonical normalization: <strong>{norm.quantity} {norm.unit}</strong>
                    </div>
                  )}

                  {/* Raw Text Quote */}
                  <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', fontStyle: 'italic', marginBottom: 14 }}>
                    From note: "{item.raw_text}"
                  </div>

                  {/* Confirm Button */}
                  <button
                    onClick={() => handleConfirmProposal(idx)}
                    className="btn btn-primary"
                    style={{ width: '100%', padding: '8px 14px' }}
                  >
                    <CheckCircle2 size={16} />
                    <span>Approve & Save Event</span>
                  </button>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
};
