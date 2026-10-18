import React, { useState, useEffect } from 'react';
import { Header } from './components/Header';
import { Navigation } from './components/Navigation';
import type { TabId } from './components/Navigation';
import { EventLogger } from './components/EventLogger';
import { TimelineView } from './components/TimelineView';
import { InvestigationView } from './components/InvestigationView';
import { PhotoLab } from './components/PhotoLab';
import { VerifierInspector } from './components/VerifierInspector';
import type { Farm, Field, Language } from './types';
import { FasalNamaAPI } from './services/api';
import { INITIAL_FARMS } from './services/mockData';
import { ShieldCheck, Sparkles } from 'lucide-react';

export const App: React.FC = () => {
  const [farms, setFarms] = useState<Farm[]>(INITIAL_FARMS);
  const [currentFarm, setCurrentFarm] = useState<Farm | null>(INITIAL_FARMS[0] || null);
  const [currentField, setCurrentField] = useState<Field | null>(INITIAL_FARMS[0]?.fields[0] || null);
  const [activeTab, setActiveTab] = useState<TabId>('logger');
  const [language, setLanguage] = useState<Language>('en');
  const [isLiveBackend, setIsLiveBackend] = useState<boolean>(false);
  const [highlightedEventId, setHighlightedEventId] = useState<string | null>(null);

  // Status badges
  const [gapsCount, setGapsCount] = useState<number>(2);
  const [unverifiedPhotosCount, setUnverifiedPhotosCount] = useState<number>(1);
  const [eventsCount, setEventsCount] = useState<number>(10);

  const initData = async () => {
    const live = await FasalNamaAPI.checkBackend();
    setIsLiveBackend(live);
    try {
      const farmList = await FasalNamaAPI.getFarms();
      if (farmList.length > 0) {
        setFarms(farmList);
        setCurrentFarm(farmList[0]);
        if (farmList[0].fields.length > 0) {
          setCurrentField(farmList[0].fields[0]);
        }
      }
      if (currentField) {
        const gapRep = await FasalNamaAPI.findGaps(currentField.id);
        let gCount = 0;
        if (gapRep.missing_irrigation) gCount++;
        if (gapRep.missing_fertilizer) gCount++;
        if (gapRep.missing_weather) gCount++;
        gCount += gapRep.null_quantity_events.length + gapRep.unknown_date_events.length;
        setGapsCount(gCount);

        const timeline = await FasalNamaAPI.getTimeline(currentField.id);
        setEventsCount(timeline.length);
      }
    } catch (e) {
      console.warn('Initial load error', e);
    }
  };

  useEffect(() => {
    initData();
  }, []);

  const handleCitationClick = (eventId: string) => {
    setHighlightedEventId(eventId);
    setActiveTab('timeline');
  };

  const handleRefreshData = async () => {
    if (currentField) {
      const gapRep = await FasalNamaAPI.findGaps(currentField.id);
      let gCount = 0;
      if (gapRep.missing_irrigation) gCount++;
      if (gapRep.missing_fertilizer) gCount++;
      if (gapRep.missing_weather) gCount++;
      gCount += gapRep.null_quantity_events.length + gapRep.unknown_date_events.length;
      setGapsCount(gCount);

      const timeline = await FasalNamaAPI.getTimeline(currentField.id);
      setEventsCount(timeline.length);
    }
  };

  return (
    <div 
      className="app-container" 
      dir={language === 'ur' ? 'rtl' : 'ltr'}
      style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}
    >
      {/* Top Header */}
      <Header
        farms={farms}
        currentFarm={currentFarm}
        currentField={currentField}
        onSelectFarm={(f) => {
          setCurrentFarm(f);
          if (f.fields.length > 0) setCurrentField(f.fields[0]);
        }}
        onSelectField={(fld) => setCurrentField(fld)}
        isLiveBackend={isLiveBackend}
        onRefreshBackend={async () => {
          const live = await FasalNamaAPI.checkBackend();
          setIsLiveBackend(live);
        }}
        language={language}
        onSelectLanguage={(l) => setLanguage(l)}
        gapsCount={gapsCount}
        unverifiedPhotosCount={unverifiedPhotosCount}
      />

      {/* Main Tab Navigation */}
      <Navigation
        activeTab={activeTab}
        onTabChange={(tab) => setActiveTab(tab)}
        pendingProposalsCount={0}
        eventsCount={eventsCount}
        unverifiedPhotosCount={unverifiedPhotosCount}
        language={language}
      />

      {/* Active Tab View Body */}
      <main style={{ flex: 1, paddingBottom: 48 }}>
        {activeTab === 'logger' && (
          <EventLogger
            currentField={currentField}
            language={language}
            onEventConfirmed={handleRefreshData}
          />
        )}

        {activeTab === 'timeline' && (
          <TimelineView
            currentField={currentField}
            language={language}
            highlightedEventId={highlightedEventId}
          />
        )}

        {activeTab === 'investigate' && (
          <InvestigationView
            currentField={currentField}
            language={language}
            onCitationClick={handleCitationClick}
          />
        )}

        {activeTab === 'photolab' && (
          <PhotoLab
            currentField={currentField}
            language={language}
            onPhotoVerified={() => {
              setUnverifiedPhotosCount((prev) => Math.max(0, prev - 1));
              handleRefreshData();
            }}
          />
        )}

        {activeTab === 'verifier' && (
          <VerifierInspector language={language} />
        )}
      </main>

      {/* Footer */}
      <footer style={{
        borderTop: '1px solid var(--border-subtle)',
        background: 'rgba(9, 14, 23, 0.9)',
        padding: '24px',
        color: 'var(--text-muted)',
        fontSize: '0.8rem',
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
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <span style={{ fontWeight: 800, color: '#fff' }}>FasalNama (فصل نامہ)</span>
            <span>·</span>
            <span>Evidence timeline, not diagnosis.</span>
            <span>·</span>
            <span>Code does deterministic work; AI does language and vision.</span>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
            <span style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
              <ShieldCheck size={14} style={{ color: 'var(--emerald-400)' }} />
              Mechanical Verifier Active
            </span>
            <span>·</span>
            <span style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
              <Sparkles size={14} style={{ color: 'var(--amber-400)' }} />
              Open-Weight AI (Qwen / Whisper / Piper)
            </span>
            <span>·</span>
            <span>Apache-2.0 License</span>
          </div>
        </div>
      </footer>
    </div>
  );
};
export default App;
