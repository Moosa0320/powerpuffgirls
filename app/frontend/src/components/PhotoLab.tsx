import React, { useState } from 'react';
import { 
  Camera, 
  CheckCircle2, 
  ShieldCheck, 
  HelpCircle, 
  Upload
} from 'lucide-react';
import type { Field, Language, PhotoRecord } from '../types';
import { INITIAL_PHOTOS } from '../services/mockData';
import { FasalNamaAPI } from '../services/api';
import confetti from 'canvas-confetti';

interface PhotoLabProps {
  currentField: Field | null;
  language: Language;
  onPhotoVerified: () => void;
}

export const PhotoLab: React.FC<PhotoLabProps> = ({
  currentField,
  language,
  onPhotoVerified,
}) => {
  const [photos, setPhotos] = useState<PhotoRecord[]>(INITIAL_PHOTOS);
  const [selectedPhoto, setSelectedPhoto] = useState<PhotoRecord | null>(photos[0] || null);

  const handleVerify = async (photo: PhotoRecord) => {
    if (!photo.id) return;
    await FasalNamaAPI.verifyPhoto(photo.id);
    setPhotos((prev) =>
      prev.map((p) => (p.id === photo.id ? { ...p, verified_by_farmer: true } : p))
    );
    if (selectedPhoto?.id === photo.id) {
      setSelectedPhoto((prev) => prev ? { ...prev, verified_by_farmer: true } : null);
    }
    confetti({
      particleCount: 35,
      spread: 50,
      colors: ['#e879f9', '#10b981'],
    });
    onPhotoVerified();
  };

  return (
    <div style={{
      maxWidth: 1400,
      margin: '24px auto',
      padding: '0 24px',
      display: 'grid',
      gridTemplateColumns: '1fr 1.1fr',
      gap: 24,
      alignItems: 'start'
    }}>
      {/* Left Column: Photo Gallery & Cards */}
      <div className="glass-panel" style={{ padding: 24 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
          <div>
            <h2 style={{ fontSize: '1.2rem', fontWeight: 800, display: 'flex', alignItems: 'center', gap: 10 }}>
              <Camera size={22} style={{ color: '#e879f9' }} />
              <span>{language === 'ur' ? 'کھیت کی تصاویر اور مشاہدات' : 'Field Photo Evidence'}</span>
            </h2>
            <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
              Vision model inspects quality & symptoms. Remains unconfirmed until you verify.
            </p>
          </div>

          <button
            onClick={() => {
              const newId = photos.length + 1;
              const newPhoto: PhotoRecord = {
                id: Date.now(),
                display_id: `P-00${newId}`,
                field_id: currentField?.id || 101,
                taken_at: new Date().toISOString(),
                image_url: 'leaf_macro_sample',
                quality_flags: { blur_score: 0.1, lighting: 'good', leaf_visible: true, passed: true },
                vision_observation: {
                  symptom_description: 'Fine stippling observed on upper leaf epidermis',
                  affected_part: 'leaf upper surface',
                  confidence: 0.84,
                },
                verified_by_farmer: false,
              };
              setPhotos([newPhoto, ...photos]);
              setSelectedPhoto(newPhoto);
            }}
            className="btn btn-secondary"
            style={{ fontSize: '0.75rem', padding: '6px 12px' }}
          >
            <Upload size={14} />
            <span>Simulate Photo Upload</span>
          </button>
        </div>

        {/* Gallery Grid */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))', gap: 14 }}>
          {photos.map((p) => {
            const isSelected = selectedPhoto?.id === p.id;
            return (
              <div
                key={p.display_id}
                onClick={() => setSelectedPhoto(p)}
                style={{
                  background: isSelected ? 'rgba(217, 70, 239, 0.15)' : 'rgba(30, 41, 59, 0.6)',
                  border: `2px solid ${isSelected ? '#e879f9' : 'var(--border-subtle)'}`,
                  borderRadius: 'var(--radius-md)',
                  padding: 12,
                  cursor: 'pointer',
                  transition: 'var(--transition)'
                }}
              >
                {/* SVG Visual Demonstration */}
                <div style={{
                  height: 110,
                  borderRadius: 'var(--radius-sm)',
                  background: 'linear-gradient(135deg, #064e3b 0%, #0f172a 100%)',
                  marginBottom: 10,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  position: 'relative',
                  overflow: 'hidden'
                }}>
                  {/* Decorative Leaf SVG graphic */}
                  <svg width="60" height="60" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                    <path d="M11 20A7 7 0 0 1 9.8 6.1C15.5 5 17 4.48 19 2c1 2 2 4.18 2 8 0 5.5-4.78 10-10 10Z" stroke="#34d399" fill="rgba(16, 185, 129, 0.2)" />
                    <path d="M2 21c0-3 1.85-5.36 5.08-6C9.5 14.52 12 13 13 12" stroke="#fbbf24" strokeWidth="1.5" />
                  </svg>

                  <span style={{
                    position: 'absolute',
                    top: 6,
                    left: 6,
                    fontFamily: 'var(--font-mono)',
                    fontSize: '0.65rem',
                    fontWeight: 700,
                    background: 'rgba(0,0,0,0.6)',
                    color: '#e879f9',
                    padding: '1px 5px',
                    borderRadius: 3
                  }}>
                    {p.display_id}
                  </span>

                  <span style={{
                    position: 'absolute',
                    bottom: 6,
                    right: 6,
                    fontSize: '0.65rem',
                    fontWeight: 700,
                    background: p.verified_by_farmer ? 'rgba(16, 185, 129, 0.8)' : 'rgba(217, 70, 239, 0.8)',
                    color: '#fff',
                    padding: '1px 6px',
                    borderRadius: 3
                  }}>
                    {p.verified_by_farmer ? 'Verified' : 'Unconfirmed'}
                  </span>
                </div>

                <div style={{ fontSize: '0.75rem', fontWeight: 700, color: '#fff', marginBottom: 2 }}>
                  Photo {p.display_id}
                </div>
                <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>
                  {p.taken_at.split('T')[0]}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Right Column: Selected Photo Inspection & Vision AI Diagnosis */}
      {selectedPhoto && (
        <div className="glass-panel" style={{ padding: 24, borderColor: '#e879f9' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
            <div>
              <span className="citation-pill photo" style={{ fontSize: '0.85rem' }}>
                {selectedPhoto.display_id}
              </span>
              <span style={{ marginLeft: 8, fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                Taken on {selectedPhoto.taken_at}
              </span>
            </div>

            <div style={{
              display: 'flex',
              alignItems: 'center',
              gap: 6,
              background: selectedPhoto.verified_by_farmer ? 'rgba(16, 185, 129, 0.15)' : 'rgba(217, 70, 239, 0.15)',
              color: selectedPhoto.verified_by_farmer ? 'var(--emerald-400)' : '#e879f9',
              border: `1px solid ${selectedPhoto.verified_by_farmer ? 'rgba(16, 185, 129, 0.3)' : 'rgba(217, 70, 239, 0.3)'}`,
              padding: '4px 10px',
              borderRadius: 'var(--radius-full)',
              fontSize: '0.75rem',
              fontWeight: 700
            }}>
              {selectedPhoto.verified_by_farmer ? (
                <>
                  <CheckCircle2 size={14} />
                  <span>Farmer Verified (قطعی ثبوت)</span>
                </>
              ) : (
                <>
                  <HelpCircle size={14} />
                  <span>Unconfirmed Observation</span>
                </>
              )}
            </div>
          </div>

          {/* Photo Large Inspection Graphic */}
          <div style={{
            height: 220,
            borderRadius: 'var(--radius-md)',
            background: 'linear-gradient(135deg, #091e17 0%, #172554 100%)',
            border: '1px solid var(--border-medium)',
            marginBottom: 20,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            position: 'relative',
            overflow: 'hidden'
          }}>
            <svg width="120" height="120" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.2">
              <path d="M11 20A7 7 0 0 1 9.8 6.1C15.5 5 17 4.48 19 2c1 2 2 4.18 2 8 0 5.5-4.78 10-10 10Z" stroke="#34d399" fill="rgba(16, 185, 129, 0.15)" />
              <circle cx="12" cy="11" r="2.5" fill="#f59e0b" opacity="0.8" />
              <circle cx="15" cy="8" r="1.5" fill="#f59e0b" opacity="0.6" />
              <circle cx="10" cy="14" r="2" fill="#f59e0b" opacity="0.7" />
              <path d="M2 21c0-3 1.85-5.36 5.08-6C9.5 14.52 12 13 13 12" stroke="#f59e0b" strokeWidth="1.2" />
            </svg>

            <div style={{
              position: 'absolute',
              bottom: 10,
              left: 12,
              background: 'rgba(0,0,0,0.7)',
              padding: '4px 10px',
              borderRadius: 'var(--radius-sm)',
              fontSize: '0.75rem',
              color: '#34d399',
              fontFamily: 'var(--font-mono)'
            }}>
              High-Res Macro View · Foliar Chlorosis Inspection
            </div>
          </div>

          {/* Vision AI Quality Checks */}
          <div style={{ marginBottom: 18 }}>
            <h4 style={{ fontSize: '0.85rem', fontWeight: 700, color: '#fff', marginBottom: 8, display: 'flex', alignItems: 'center', gap: 6 }}>
              <ShieldCheck size={16} style={{ color: 'var(--emerald-400)' }} />
              <span>Vision Model Quality Assessment</span>
            </h4>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 10 }}>
              <div style={{
                background: 'rgba(30, 41, 59, 0.6)',
                padding: '8px 12px',
                borderRadius: 'var(--radius-sm)',
                border: '1px solid var(--border-subtle)',
                fontSize: '0.75rem'
              }}>
                <div style={{ color: 'var(--text-muted)' }}>Blur Check</div>
                <strong style={{ color: 'var(--emerald-400)' }}>PASSED (Clear)</strong>
              </div>

              <div style={{
                background: 'rgba(30, 41, 59, 0.6)',
                padding: '8px 12px',
                borderRadius: 'var(--radius-sm)',
                border: '1px solid var(--border-subtle)',
                fontSize: '0.75rem'
              }}>
                <div style={{ color: 'var(--text-muted)' }}>Lighting</div>
                <strong style={{ color: 'var(--emerald-400)' }}>GOOD (Daylight)</strong>
              </div>

              <div style={{
                background: 'rgba(30, 41, 59, 0.6)',
                padding: '8px 12px',
                borderRadius: 'var(--radius-sm)',
                border: '1px solid var(--border-subtle)',
                fontSize: '0.75rem'
              }}>
                <div style={{ color: 'var(--text-muted)' }}>Crop Part</div>
                <strong style={{ color: '#fff' }}>{selectedPhoto.vision_observation?.affected_part || 'Leaf'}</strong>
              </div>
            </div>
          </div>

          {/* Vision Model Observation Description */}
          <div style={{
            background: 'rgba(217, 70, 239, 0.08)',
            border: '1px solid rgba(217, 70, 239, 0.25)',
            borderRadius: 'var(--radius-md)',
            padding: 16,
            marginBottom: 20
          }}>
            <div style={{ fontSize: '0.75rem', color: '#e879f9', fontWeight: 800, marginBottom: 4 }}>
              VISION OBSERVATION (Open-Weight VLM)
            </div>
            <p style={{ fontSize: '0.9rem', color: '#f5d0fe', lineHeight: 1.5, margin: 0 }}>
              "{selectedPhoto.vision_observation?.symptom_description}"
            </p>
          </div>

          {/* Farmer Verification Action */}
          {!selectedPhoto.verified_by_farmer ? (
            <button
              onClick={() => handleVerify(selectedPhoto)}
              className="btn btn-primary"
              style={{ width: '100%', padding: '10px 16px' }}
            >
              <CheckCircle2 size={18} />
              <span>Confirm as Farmer: "I verify this symptom on my crop"</span>
            </button>
          ) : (
            <div style={{
              background: 'rgba(16, 185, 129, 0.1)',
              border: '1px solid var(--emerald-500)',
              borderRadius: 'var(--radius-md)',
              padding: '10px 16px',
              textAlign: 'center',
              color: 'var(--emerald-400)',
              fontSize: '0.85rem',
              fontWeight: 700
            }}>
              ✓ You have verified this observation. It is now treated as confirmed evidence.
            </div>
          )}
        </div>
      )}
    </div>
  );
};
