import React from 'react';
import type { Farm, Field, Language } from '../types';
import { 
  Sprout, 
  Server, 
  ShieldCheck, 
  AlertTriangle, 
  Layers
} from 'lucide-react';

interface HeaderProps {
  farms: Farm[];
  currentFarm: Farm | null;
  currentField: Field | null;
  onSelectFarm: (farm: Farm) => void;
  onSelectField: (field: Field) => void;
  isLiveBackend: boolean;
  onRefreshBackend: () => void;
  language: Language;
  onSelectLanguage: (lang: Language) => void;
  gapsCount: number;
  unverifiedPhotosCount: number;
}

export const Header: React.FC<HeaderProps> = ({
  farms,
  currentFarm,
  currentField,
  onSelectFarm,
  onSelectField,
  isLiveBackend,
  onRefreshBackend,
  language,
  onSelectLanguage,
  gapsCount,
  unverifiedPhotosCount,
}) => {
  return (
    <header className="header-container" style={{
      borderBottom: '1px solid var(--border-subtle)',
      background: 'rgba(9, 14, 23, 0.85)',
      backdropFilter: 'blur(16px)',
      position: 'sticky',
      top: 0,
      zIndex: 40,
      padding: '12px 24px',
    }}>
      <div style={{
        maxWidth: 1400,
        margin: '0 auto',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        flexWrap: 'wrap',
        gap: 16
      }}>
        {/* Brand & Tagline */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
          <div style={{
            width: 44,
            height: 44,
            borderRadius: 'var(--radius-md)',
            background: 'linear-gradient(135deg, var(--emerald-600) 0%, var(--emerald-500) 100%)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            boxShadow: '0 0 16px var(--emerald-glow)',
            color: '#fff',
            flexShrink: 0
          }}>
            <Sprout size={26} strokeWidth={2.5} />
          </div>

          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <h1 style={{ 
                fontSize: '1.4rem', 
                fontWeight: 800, 
                letterSpacing: '-0.02em',
                background: 'linear-gradient(135deg, #ffffff 40%, var(--emerald-400) 100%)',
                WebkitBackgroundClip: 'text',
                WebkitTextFillColor: 'transparent',
                display: 'inline-block'
              }}>
                FasalNama
              </h1>
              <span style={{
                fontFamily: 'var(--font-urdu)',
                fontSize: '1.25rem',
                color: 'var(--amber-400)',
                fontWeight: 700
              }}>
                فصل نامہ
              </span>
              <span style={{
                background: 'rgba(16, 185, 129, 0.12)',
                color: 'var(--emerald-400)',
                border: '1px solid rgba(16, 185, 129, 0.3)',
                padding: '2px 8px',
                borderRadius: 'var(--radius-full)',
                fontSize: '0.7rem',
                fontWeight: 700,
                textTransform: 'uppercase',
                letterSpacing: '0.05em'
              }}>
                Open-Weight AI
              </span>
            </div>
            <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', margin: 0 }}>
              Evidence Timeline, Not Diagnosis · Farm Record Investigator
            </p>
          </div>
        </div>

        {/* Farm & Field Selectors */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
          {/* Farm Dropdown */}
          <div style={{ position: 'relative' }}>
            <div style={{
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              background: 'rgba(30, 41, 59, 0.6)',
              border: '1px solid var(--border-medium)',
              padding: '6px 12px',
              borderRadius: 'var(--radius-md)',
              fontSize: '0.825rem'
            }}>
              <Layers size={15} style={{ color: 'var(--amber-400)' }} />
              <select
                aria-label="Select Farm"
                value={currentFarm?.id || ''}
                onChange={(e) => {
                  const f = farms.find((farm) => farm.id === Number(e.target.value));
                  if (f) onSelectFarm(f);
                }}
                style={{
                  background: 'transparent',
                  border: 'none',
                  color: 'var(--text-primary)',
                  fontWeight: 600,
                  cursor: 'pointer',
                  outline: 'none',
                  fontFamily: 'inherit'
                }}
              >
                {farms.map((f) => (
                  <option key={f.id} value={f.id} style={{ background: '#0f172a', color: '#fff' }}>
                    {f.name}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {/* Field Dropdown */}
          {currentFarm && currentFarm.fields.length > 0 && (
            <div style={{ position: 'relative' }}>
              <div style={{
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                background: 'rgba(30, 41, 59, 0.6)',
                border: '1px solid var(--emerald-500)',
                padding: '6px 12px',
                borderRadius: 'var(--radius-md)',
                fontSize: '0.825rem',
                boxShadow: '0 0 10px rgba(16, 185, 129, 0.15)'
              }}>
                <Sprout size={15} style={{ color: 'var(--emerald-400)' }} />
                <select
                  aria-label="Select Field"
                  value={currentField?.id || ''}
                  onChange={(e) => {
                    const fld = currentFarm.fields.find((field) => field.id === Number(e.target.value));
                    if (fld) onSelectField(fld);
                  }}
                  style={{
                    background: 'transparent',
                    border: 'none',
                    color: 'var(--emerald-400)',
                    fontWeight: 700,
                    cursor: 'pointer',
                    outline: 'none',
                    fontFamily: 'inherit'
                  }}
                >
                  {currentFarm.fields.map((fld) => (
                    <option key={fld.id} value={fld.id} style={{ background: '#0f172a', color: '#fff' }}>
                      {fld.name} ({fld.crop || 'Field'})
                    </option>
                  ))}
                </select>
              </div>
            </div>
          )}

          {/* Gaps Alert Badge */}
          {gapsCount > 0 && (
            <div 
              title={`${gapsCount} missing record alerts in current window`}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 6,
                background: 'rgba(245, 158, 11, 0.12)',
                color: 'var(--amber-400)',
                border: '1px solid rgba(245, 158, 11, 0.3)',
                padding: '5px 10px',
                borderRadius: 'var(--radius-full)',
                fontSize: '0.75rem',
                fontWeight: 600
              }}
            >
              <AlertTriangle size={13} />
              <span>{gapsCount} Gaps</span>
            </div>
          )}

          {/* Unverified Photos Badge */}
          {unverifiedPhotosCount > 0 && (
            <div
              title={`${unverifiedPhotosCount} photo observation pending farmer confirmation`}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 6,
                background: 'rgba(217, 70, 239, 0.12)',
                color: '#e879f9',
                border: '1px solid rgba(217, 70, 239, 0.3)',
                padding: '5px 10px',
                borderRadius: 'var(--radius-full)',
                fontSize: '0.75rem',
                fontWeight: 600
              }}
            >
              <ShieldCheck size={13} />
              <span>{unverifiedPhotosCount} Unconfirmed</span>
            </div>
          )}

          {/* Backend Run Mode Status Pill */}
          <button
            onClick={onRefreshBackend}
            title={isLiveBackend ? 'Connected to FastAPI Backend (port 8000)' : 'Running on Local Deterministic Engine (Offline Safe Mode)'}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 7,
              background: isLiveBackend ? 'rgba(16, 185, 129, 0.15)' : 'rgba(59, 130, 246, 0.15)',
              color: isLiveBackend ? 'var(--emerald-400)' : '#93c5fd',
              border: `1px solid ${isLiveBackend ? 'rgba(16, 185, 129, 0.35)' : 'rgba(59, 130, 246, 0.35)'}`,
              padding: '5px 12px',
              borderRadius: 'var(--radius-full)',
              fontSize: '0.75rem',
              fontWeight: 600,
              cursor: 'pointer',
              fontFamily: 'inherit'
            }}
          >
            <span className={`pulse-dot ${isLiveBackend ? 'green' : 'amber'}`} />
            <Server size={13} />
            <span>{isLiveBackend ? 'FastAPI Live' : 'Deterministic Engine'}</span>
          </button>

          {/* Language Selector */}
          <div style={{
            display: 'flex',
            alignItems: 'center',
            background: 'rgba(30, 41, 59, 0.6)',
            border: '1px solid var(--border-medium)',
            borderRadius: 'var(--radius-md)',
            padding: '2px',
            fontSize: '0.75rem'
          }}>
            <button
              onClick={() => onSelectLanguage('en')}
              style={{
                background: language === 'en' ? 'var(--emerald-600)' : 'transparent',
                color: language === 'en' ? '#fff' : 'var(--text-muted)',
                border: 'none',
                padding: '4px 8px',
                borderRadius: 'var(--radius-sm)',
                fontWeight: 700,
                cursor: 'pointer'
              }}
            >
              EN
            </button>
            <button
              onClick={() => onSelectLanguage('roman')}
              style={{
                background: language === 'roman' ? 'var(--emerald-600)' : 'transparent',
                color: language === 'roman' ? '#fff' : 'var(--text-muted)',
                border: 'none',
                padding: '4px 8px',
                borderRadius: 'var(--radius-sm)',
                fontWeight: 700,
                cursor: 'pointer'
              }}
            >
              Roman
            </button>
            <button
              onClick={() => onSelectLanguage('ur')}
              style={{
                background: language === 'ur' ? 'var(--emerald-600)' : 'transparent',
                color: language === 'ur' ? '#fff' : 'var(--text-muted)',
                border: 'none',
                padding: '4px 8px',
                borderRadius: 'var(--radius-sm)',
                fontWeight: 700,
                cursor: 'pointer',
                fontFamily: 'var(--font-urdu)'
              }}
            >
              اردو
            </button>
          </div>
        </div>
      </div>
    </header>
  );
};
