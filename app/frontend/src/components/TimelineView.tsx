import React, { useState, useEffect } from 'react';
import { 
  Calendar, 
  Filter, 
  Search, 
  AlertTriangle, 
  ArrowUpRight, 
  ArrowDownRight, 
  CheckCircle2, 
  Droplet, 
  Zap, 
  Leaf, 
  CloudRain, 
  Eye, 
  Camera, 
  RefreshCw
} from 'lucide-react';
import type { Comparison, Field, GapReport, Language, TimelineItem } from '../types';
import { FasalNamaAPI } from '../services/api';

interface TimelineViewProps {
  currentField: Field | null;
  language?: Language;
  highlightedEventId?: string | null;
}

export const TimelineView: React.FC<TimelineViewProps> = ({
  currentField,
  highlightedEventId,
}) => {
  const [timelineItems, setTimelineItems] = useState<TimelineItem[]>([]);
  const [gaps, setGaps] = useState<GapReport | null>(null);
  const [comparisons, setComparisons] = useState<Comparison[]>([]);
  const [selectedTypeFilter, setSelectedTypeFilter] = useState<string>('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [windowDays, setWindowDays] = useState(14);
  const [isLoading, setIsLoading] = useState(false);

  const loadData = async () => {
    if (!currentField) return;
    setIsLoading(true);
    try {
      const items = await FasalNamaAPI.getTimeline(currentField.id);
      const gapReport = await FasalNamaAPI.findGaps(currentField.id, windowDays);
      const fertComps = await FasalNamaAPI.compareValues(currentField.id, 'fertilizer');
      setTimelineItems(items);
      setGaps(gapReport);
      setComparisons(fertComps);
    } catch (err) {
      console.error('Failed to load timeline', err);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [currentField, windowDays]);

  // Scroll to highlighted event if requested
  useEffect(() => {
    if (highlightedEventId) {
      const el = document.getElementById(`timeline-item-${highlightedEventId}`);
      if (el) {
        el.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }
    }
  }, [highlightedEventId]);

  const filteredItems = timelineItems.filter((item) => {
    if (selectedTypeFilter !== 'all') {
      if (selectedTypeFilter === 'photo' && item.kind !== 'photo') return false;
      if (selectedTypeFilter !== 'photo' && item.type !== selectedTypeFilter) return false;
    }
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      const matchId = item.display_id.toLowerCase().includes(q);
      const matchProd = item.product?.toLowerCase().includes(q);
      const matchSymptom = item.symptom?.toLowerCase().includes(q);
      const matchType = item.type?.toLowerCase().includes(q);
      return matchId || matchProd || matchSymptom || matchType;
    }
    return true;
  });

  const getEventIcon = (type?: string | null, kind?: string) => {
    if (kind === 'photo') return <Camera size={15} style={{ color: '#e879f9' }} />;
    switch (type) {
      case 'fertilizer': return <Zap size={15} style={{ color: 'var(--amber-400)' }} />;
      case 'irrigation': return <Droplet size={15} style={{ color: 'var(--cyan-400)' }} />;
      case 'planting': return <Leaf size={15} style={{ color: 'var(--emerald-400)' }} />;
      case 'weather': return <CloudRain size={15} style={{ color: '#60a5fa' }} />;
      case 'observation': return <Eye size={15} style={{ color: 'var(--rose-400)' }} />;
      default: return <Calendar size={15} />;
    }
  };

  return (
    <div style={{
      maxWidth: 1400,
      margin: '24px auto',
      padding: '0 24px',
      display: 'grid',
      gridTemplateColumns: '1fr 340px',
      gap: 24,
      alignItems: 'start'
    }}>
      {/* Left Column: Timeline Feed & Filters */}
      <div>
        {/* Controls Bar */}
        <div className="glass-panel" style={{ padding: '16px 20px', marginBottom: 20 }}>
          <div style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            flexWrap: 'wrap',
            gap: 14
          }}>
            {/* Search Input */}
            <div style={{
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              background: 'rgba(15, 23, 42, 0.8)',
              border: '1px solid var(--border-medium)',
              borderRadius: 'var(--radius-md)',
              padding: '6px 12px',
              minWidth: 260
            }}>
              <Search size={16} style={{ color: 'var(--text-muted)' }} />
              <input
                type="text"
                placeholder="Search event ID, product, symptom..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                style={{
                  background: 'transparent',
                  border: 'none',
                  color: '#fff',
                  fontSize: '0.85rem',
                  outline: 'none',
                  width: '100%',
                  fontFamily: 'inherit'
                }}
              />
            </div>

            {/* Filter Pills */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
              <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginRight: 4, display: 'flex', alignItems: 'center', gap: 4 }}>
                <Filter size={13} /> Filter:
              </span>
              {[
                { id: 'all', label: 'All' },
                { id: 'fertilizer', label: 'Fertilizer' },
                { id: 'irrigation', label: 'Irrigation' },
                { id: 'pesticide', label: 'Pesticide' },
                { id: 'weather', label: 'Weather' },
                { id: 'observation', label: 'Observation' },
                { id: 'photo', label: 'Photos' },
              ].map((f) => (
                <button
                  key={f.id}
                  onClick={() => setSelectedTypeFilter(f.id)}
                  style={{
                    background: selectedTypeFilter === f.id ? 'var(--emerald-600)' : 'rgba(30, 41, 59, 0.6)',
                    color: selectedTypeFilter === f.id ? '#fff' : 'var(--text-muted)',
                    border: '1px solid var(--border-subtle)',
                    borderRadius: 'var(--radius-full)',
                    padding: '4px 10px',
                    fontSize: '0.75rem',
                    fontWeight: 600,
                    cursor: 'pointer',
                    transition: 'var(--transition)'
                  }}
                >
                  {f.label}
                </button>
              ))}
            </div>

            <button
              onClick={loadData}
              className="btn btn-secondary"
              style={{ padding: '6px 10px', fontSize: '0.75rem' }}
              title="Refresh timeline records"
            >
              <RefreshCw size={13} className={isLoading ? 'spin' : ''} />
              <span>Refresh</span>
            </button>
          </div>
        </div>

        {/* Timeline Events Feed */}
        <div style={{ position: 'relative', paddingLeft: 24 }}>
          {/* Vertical Connecting Line */}
          <div style={{
            position: 'absolute',
            left: 7,
            top: 10,
            bottom: 10,
            width: 2,
            background: 'linear-gradient(to bottom, var(--emerald-500) 0%, rgba(255, 255, 255, 0.1) 100%)',
            borderRadius: 2
          }} />

          {filteredItems.length === 0 ? (
            <div className="glass-panel" style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)' }}>
              No events found matching the filter criteria.
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
              {filteredItems.map((item) => {
                const isHighlighted = highlightedEventId === item.display_id;
                return (
                  <div
                    key={item.display_id}
                    id={`timeline-item-${item.display_id}`}
                    className={`glass-panel ${isHighlighted ? 'spotlight-pulse' : ''}`}
                    style={{
                      padding: '14px 18px',
                      position: 'relative',
                      borderLeft: isHighlighted ? '3px solid var(--emerald-400)' : undefined,
                      transition: 'var(--transition)'
                    }}
                  >
                    {/* Node Dot on Connector Line */}
                    <div style={{
                      position: 'absolute',
                      left: -23,
                      top: 18,
                      width: 12,
                      height: 12,
                      borderRadius: '50%',
                      background: isHighlighted ? 'var(--emerald-400)' : '#0f172a',
                      border: `2px solid ${isHighlighted ? '#fff' : 'var(--emerald-500)'}`,
                      boxShadow: isHighlighted ? '0 0 10px var(--emerald-400)' : 'none'
                    }} />

                    {/* Card Header Row */}
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                        <span className="citation-pill" style={{ cursor: 'default' }}>
                          {item.display_id}
                        </span>

                        <span className={`badge badge-${item.kind === 'photo' ? 'photo_observation' : item.type}`}>
                          {getEventIcon(item.type, item.kind)}
                          {item.kind === 'photo' ? 'Photo Observation' : item.type}
                        </span>

                        <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', fontWeight: 600 }}>
                          {item.occurred_at}
                        </span>
                      </div>

                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        {item.verified_by_farmer && (
                          <span style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: 4,
                            fontSize: '0.7rem',
                            color: 'var(--emerald-400)',
                            background: 'rgba(16, 185, 129, 0.1)',
                            padding: '2px 8px',
                            borderRadius: 'var(--radius-full)',
                            border: '1px solid rgba(16, 185, 129, 0.25)'
                          }}>
                            <CheckCircle2 size={12} />
                            Verified
                          </span>
                        )}
                      </div>
                    </div>

                    {/* Card Content Body */}
                    <div style={{ fontSize: '0.875rem', color: 'var(--text-primary)', lineHeight: 1.5 }}>
                      {item.product && (
                        <div style={{ marginBottom: 4 }}>
                          <span style={{ color: 'var(--text-muted)' }}>Product: </span>
                          <strong style={{ color: '#fff' }}>{item.product}</strong>
                          {item.quantity != null && (
                            <span style={{ marginLeft: 8, color: 'var(--emerald-400)', fontWeight: 700 }}>
                              {item.quantity} {item.unit || ''}
                            </span>
                          )}
                        </div>
                      )}

                      {item.symptom && (
                        <div style={{
                          background: 'rgba(244, 63, 94, 0.1)',
                          border: '1px solid rgba(244, 63, 94, 0.25)',
                          borderRadius: 'var(--radius-sm)',
                          padding: '6px 10px',
                          color: 'var(--rose-400)',
                          fontSize: '0.8rem',
                          marginTop: 6
                        }}>
                          <strong>Reported Observation:</strong> "{item.symptom}"
                        </div>
                      )}

                      {item.type === 'weather' && (
                        <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: 4 }}>
                          ℹ️ Weather data is area-level station data, not field-level sensor.
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>

      {/* Right Column: Deterministic Gaps & Dose Change Engine Insights */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
        {/* Gap Detector Card */}
        <div className="glass-panel" style={{ padding: 20 }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
            <h3 style={{ fontSize: '1rem', fontWeight: 800, display: 'flex', alignItems: 'center', gap: 8, color: 'var(--amber-400)' }}>
              <AlertTriangle size={18} />
              <span>Gaps Detected ({windowDays}d)</span>
            </h3>

            <select
              aria-label="Gap window lookback days"
              value={windowDays}
              onChange={(e) => setWindowDays(Number(e.target.value))}
              style={{
                background: '#0f172a',
                border: '1px solid var(--border-medium)',
                borderRadius: 'var(--radius-sm)',
                color: 'var(--text-secondary)',
                fontSize: '0.75rem',
                padding: '3px 6px'
              }}
            >
              <option value={7}>7 Days Window</option>
              <option value={14}>14 Days (Default)</option>
              <option value={30}>30 Days Window</option>
            </select>
          </div>

          <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginBottom: 14 }}>
            Deterministic rule: missing irrigation/fertilizer/weather or null quantity events are flagged.
          </p>

          {gaps && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {/* Irrigation Flag */}
              <div style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '8px 12px',
                borderRadius: 'var(--radius-sm)',
                background: gaps.missing_irrigation ? 'rgba(244, 63, 94, 0.12)' : 'rgba(16, 185, 129, 0.08)',
                border: `1px solid ${gaps.missing_irrigation ? 'rgba(244, 63, 94, 0.3)' : 'rgba(16, 185, 129, 0.2)'}`,
                fontSize: '0.8rem'
              }}>
                <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <Droplet size={14} style={{ color: gaps.missing_irrigation ? 'var(--rose-400)' : 'var(--emerald-400)' }} />
                  Irrigation Recorded
                </span>
                <strong style={{ color: gaps.missing_irrigation ? 'var(--rose-400)' : 'var(--emerald-400)' }}>
                  {gaps.missing_irrigation ? 'MISSING' : 'OK'}
                </strong>
              </div>

              {/* Fertilizer Flag */}
              <div style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '8px 12px',
                borderRadius: 'var(--radius-sm)',
                background: gaps.missing_fertilizer ? 'rgba(244, 63, 94, 0.12)' : 'rgba(16, 185, 129, 0.08)',
                border: `1px solid ${gaps.missing_fertilizer ? 'rgba(244, 63, 94, 0.3)' : 'rgba(16, 185, 129, 0.2)'}`,
                fontSize: '0.8rem'
              }}>
                <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <Zap size={14} style={{ color: gaps.missing_fertilizer ? 'var(--rose-400)' : 'var(--emerald-400)' }} />
                  Fertilizer Recorded
                </span>
                <strong style={{ color: gaps.missing_fertilizer ? 'var(--rose-400)' : 'var(--emerald-400)' }}>
                  {gaps.missing_fertilizer ? 'MISSING' : 'OK'}
                </strong>
              </div>

              {/* Weather Flag */}
              <div style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '8px 12px',
                borderRadius: 'var(--radius-sm)',
                background: gaps.missing_weather ? 'rgba(244, 63, 94, 0.12)' : 'rgba(16, 185, 129, 0.08)',
                border: `1px solid ${gaps.missing_weather ? 'rgba(244, 63, 94, 0.3)' : 'rgba(16, 185, 129, 0.2)'}`,
                fontSize: '0.8rem'
              }}>
                <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <CloudRain size={14} style={{ color: gaps.missing_weather ? 'var(--rose-400)' : 'var(--emerald-400)' }} />
                  Weather Recorded
                </span>
                <strong style={{ color: gaps.missing_weather ? 'var(--rose-400)' : 'var(--emerald-400)' }}>
                  {gaps.missing_weather ? 'MISSING' : 'OK'}
                </strong>
              </div>

              {/* Null Quantity Events */}
              {gaps.null_quantity_events.length > 0 && (
                <div style={{
                  padding: '10px 12px',
                  background: 'rgba(245, 158, 11, 0.1)',
                  border: '1px solid rgba(245, 158, 11, 0.25)',
                  borderRadius: 'var(--radius-sm)',
                  fontSize: '0.75rem',
                  color: 'var(--amber-400)'
                }}>
                  <div style={{ fontWeight: 700, marginBottom: 4 }}>Null Quantity Events:</div>
                  <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                    {gaps.null_quantity_events.map((id) => (
                      <span key={id} className="citation-pill" style={{ background: 'rgba(245, 158, 11, 0.2)', color: 'var(--amber-400)' }}>
                        {id}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Unknown Date Events */}
              {gaps.unknown_date_events.length > 0 && (
                <div style={{
                  padding: '10px 12px',
                  background: 'rgba(245, 158, 11, 0.1)',
                  border: '1px solid rgba(245, 158, 11, 0.25)',
                  borderRadius: 'var(--radius-sm)',
                  fontSize: '0.75rem',
                  color: 'var(--amber-400)'
                }}>
                  <div style={{ fontWeight: 700, marginBottom: 4 }}>Unknown Date (Off Timeline):</div>
                  <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                    {gaps.unknown_date_events.map((id) => (
                      <span key={id} className="citation-pill" style={{ background: 'rgba(245, 158, 11, 0.2)', color: 'var(--amber-400)' }}>
                        {id}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Dose Comparison Insights Card */}
        <div className="glass-panel" style={{ padding: 20 }}>
          <h3 style={{ fontSize: '1rem', fontWeight: 800, display: 'flex', alignItems: 'center', gap: 8, color: 'var(--emerald-400)', marginBottom: 8 }}>
            <ArrowUpRight size={18} />
            <span>Dosage Changes</span>
          </h3>
          <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginBottom: 14 }}>
            Deterministic percentage change vs prior application (compare_values).
          </p>

          {comparisons.length === 0 ? (
            <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', fontStyle: 'italic' }}>
              No sequential comparison points for fertilizer yet.
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {comparisons.map((c, i) => (
                <div
                  key={i}
                  style={{
                    padding: '10px 12px',
                    borderRadius: 'var(--radius-sm)',
                    background: 'rgba(30, 41, 59, 0.6)',
                    border: '1px solid var(--border-subtle)',
                    fontSize: '0.8rem'
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 4 }}>
                    <strong style={{ color: '#fff', textTransform: 'capitalize' }}>{c.product || c.type}</strong>
                    {c.percent_change != null && (
                      <span style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: 2,
                        fontWeight: 700,
                        color: c.percent_change > 0 ? 'var(--amber-400)' : 'var(--cyan-400)'
                      }}>
                        {c.percent_change > 0 ? <ArrowUpRight size={14} /> : <ArrowDownRight size={14} />}
                        {c.percent_change > 0 ? `+${c.percent_change}%` : `${c.percent_change}%`}
                      </span>
                    )}
                  </div>

                  <div style={{ color: 'var(--text-muted)', fontSize: '0.75rem', marginBottom: 6 }}>
                    From {c.previous_value} {c.unit} ({c.previous_event_id}) to {c.current_value} {c.unit} ({c.event_id})
                  </div>

                  {c.percent_change != null && Math.abs(c.percent_change) >= 50 && (
                    <div style={{
                      fontSize: '0.7rem',
                      color: 'var(--amber-400)',
                      background: 'rgba(245, 158, 11, 0.1)',
                      padding: '2px 6px',
                      borderRadius: 3
                    }}>
                      ⚡ Significant dose fluctuation ({c.percent_change > 0 ? 'increase' : 'decrease'})
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
