import React from 'react';
import { Mic, Calendar, SearchCheck, Camera, ShieldAlert } from 'lucide-react';
import type { Language } from '../types';

export type TabId = 'logger' | 'timeline' | 'investigate' | 'photolab' | 'verifier';

interface NavigationProps {
  activeTab: TabId;
  onTabChange: (tab: TabId) => void;
  pendingProposalsCount: number;
  eventsCount: number;
  unverifiedPhotosCount: number;
  language: Language;
}

export const Navigation: React.FC<NavigationProps> = ({
  activeTab,
  onTabChange,
  pendingProposalsCount,
  eventsCount,
  unverifiedPhotosCount,
  language,
}) => {
  const tabs = [
    {
      id: 'logger' as TabId,
      label: language === 'ur' ? 'اندراج اور تجزیہ' : language === 'roman' ? 'Log & Parse' : 'Log & Parse',
      sublabel: language === 'ur' ? 'آواز / تحریر' : 'Voice, Text & AI Parser',
      icon: <Mic size={18} />,
      badge: pendingProposalsCount > 0 ? `${pendingProposalsCount} New` : undefined,
      badgeColor: 'var(--amber-400)',
    },
    {
      id: 'timeline' as TabId,
      label: language === 'ur' ? 'شواہد ٹائم لائن' : language === 'roman' ? 'Evidence Timeline' : 'Evidence Timeline',
      sublabel: language === 'ur' ? 'ریکارڈز اور خامیاں' : `${eventsCount} Events & Gaps`,
      icon: <Calendar size={18} />,
    },
    {
      id: 'investigate' as TabId,
      label: language === 'ur' ? 'تحقیقاتی رپورٹ' : language === 'roman' ? 'Investigate' : 'Investigate',
      sublabel: language === 'ur' ? 'بغیر تشخیص شواہد' : 'Cited Evidence Report',
      icon: <SearchCheck size={18} />,
      highlight: true,
    },
    {
      id: 'photolab' as TabId,
      label: language === 'ur' ? 'تصویری لیب' : language === 'roman' ? 'Photo Evidence' : 'Photo Evidence',
      sublabel: language === 'ur' ? 'تصدیق اور کیمرہ' : 'Vision AI & Verify',
      icon: <Camera size={18} />,
      badge: unverifiedPhotosCount > 0 ? `${unverifiedPhotosCount} Pending` : undefined,
      badgeColor: '#e879f9',
    },
    {
      id: 'verifier' as TabId,
      label: language === 'ur' ? 'حفاظتی گارڈریلز' : language === 'roman' ? 'Verifier Rules' : 'Verifier Rules',
      sublabel: language === 'ur' ? 'میکانیکی معائنہ' : 'Anti-Diagnosis Sandbox',
      icon: <ShieldAlert size={18} />,
    },
  ];

  return (
    <nav style={{
      maxWidth: 1400,
      margin: '16px auto 0 auto',
      padding: '0 24px',
    }}>
      <div style={{
        display: 'flex',
        alignItems: 'center',
        gap: 8,
        background: 'rgba(15, 23, 42, 0.75)',
        border: '1px solid var(--border-subtle)',
        borderRadius: 'var(--radius-lg)',
        padding: '6px',
        overflowX: 'auto',
      }}>
        {tabs.map((tab) => {
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => onTabChange(tab.id)}
              style={{
                flex: 1,
                minWidth: 160,
                display: 'flex',
                alignItems: 'center',
                gap: 12,
                padding: '10px 16px',
                borderRadius: 'var(--radius-md)',
                background: isActive 
                  ? 'linear-gradient(135deg, rgba(16, 185, 129, 0.2) 0%, rgba(5, 150, 105, 0.15) 100%)' 
                  : 'transparent',
                border: isActive 
                  ? '1px solid rgba(16, 185, 129, 0.4)' 
                  : '1px solid transparent',
                color: isActive ? 'var(--emerald-400)' : 'var(--text-secondary)',
                cursor: 'pointer',
                transition: 'var(--transition)',
                outline: 'none',
                textAlign: 'left',
                position: 'relative'
              }}
            >
              <div style={{
                color: isActive ? 'var(--emerald-400)' : 'var(--text-muted)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                padding: '8px',
                borderRadius: 'var(--radius-sm)',
                background: isActive ? 'rgba(16, 185, 129, 0.15)' : 'rgba(255, 255, 255, 0.04)'
              }}>
                {tab.icon}
              </div>

              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                  fontWeight: 700,
                  fontSize: '0.875rem'
                }}>
                  <span style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                    {tab.label}
                  </span>
                  {tab.badge && (
                    <span style={{
                      fontSize: '0.65rem',
                      fontWeight: 800,
                      padding: '1px 6px',
                      borderRadius: 'var(--radius-full)',
                      background: 'rgba(255, 255, 255, 0.08)',
                      color: tab.badgeColor || 'var(--emerald-400)',
                      border: `1px solid ${tab.badgeColor || 'rgba(16, 185, 129, 0.3)'}`
                    }}>
                      {tab.badge}
                    </span>
                  )}
                </div>
                <div style={{
                  fontSize: '0.7rem',
                  color: 'var(--text-muted)',
                  whiteSpace: 'nowrap',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis'
                }}>
                  {tab.sublabel}
                </div>
              </div>

              {tab.highlight && !isActive && (
                <div style={{
                  position: 'absolute',
                  top: 6,
                  right: 6,
                  width: 6,
                  height: 6,
                  borderRadius: '50%',
                  background: 'var(--emerald-400)',
                  boxShadow: '0 0 8px var(--emerald-400)'
                }} />
              )}
            </button>
          );
        })}
      </div>
    </nav>
  );
};
