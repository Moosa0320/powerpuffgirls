export type EventType =
  | 'planting'
  | 'irrigation'
  | 'fertilizer'
  | 'pesticide'
  | 'weather'
  | 'observation'
  | 'harvest'
  | 'photo_observation';

export type DateCertainty = 'exact' | 'approximate' | 'unknown';

export type EventSource = 'farmer_text' | 'farmer_voice' | 'weather_api' | 'vision_model';

export interface Farm {
  id: number;
  name: string;
  created_at?: string;
  fields: Field[];
}

export interface Field {
  id: number;
  farm_id: number;
  name: string;
  crop?: string;
  planting_date?: string;
  area?: number;
  latitude?: number;
  longitude?: number;
}

export interface FarmEvent {
  id?: number;
  display_id: string; // E-001, E-002
  field_id: number;
  type: EventType;
  occurred_at: string; // YYYY-MM-DD
  date_certainty: DateCertainty;
  product?: string | null;
  quantity?: number | null;
  unit?: string | null;
  symptom?: string | null;
  source: EventSource;
  raw_text?: string | null;
  confidence?: number | null;
  verified_by_farmer: boolean;
  created_at?: string;
}

export interface PhotoRecord {
  id?: number;
  display_id: string; // P-001
  field_id: number;
  event_id?: number | null;
  taken_at: string;
  image_url?: string;
  quality_flags?: {
    blur_score?: number; // 0-1
    lighting?: 'good' | 'low' | 'overexposed';
    leaf_visible?: boolean;
    passed?: boolean;
  };
  vision_observation?: {
    symptom_description?: string;
    affected_part?: string;
    confidence?: number;
  };
  verified_by_farmer: boolean;
}

export interface TimelineItem {
  kind: 'event' | 'photo';
  display_id: string;
  occurred_at: string;
  type?: string | null;
  product?: string | null;
  quantity?: number | null;
  unit?: string | null;
  symptom?: string | null;
  verified_by_farmer?: boolean;
}

export interface GapReport {
  missing_irrigation: boolean;
  missing_fertilizer: boolean;
  missing_weather: boolean;
  null_quantity_events: string[];
  unknown_date_events: string[];
  has_gaps: boolean;
  window_days: number;
}

export interface Comparison {
  event_id: string;
  previous_event_id: string;
  type: string;
  product: string | null;
  previous_value: number;
  current_value: number;
  unit: string | null;
  percent_change: number | null;
}

export interface ProposedEvent {
  type: EventType;
  product?: string | null;
  quantity?: number | null;
  unit?: string | null;
  occurred_at?: string | null;
  days_ago?: number | null;
  date_certainty: DateCertainty;
  symptom?: string | null;
  confidence?: number | null;
  raw_text: string;
  source: EventSource;
}

export interface ClaimItem {
  text: string;
  type: 'fact' | 'possibility' | 'question';
  event_ids: string[];
  photo_ids?: string[];
  unconfirmed?: boolean;
}

export interface ReportSections {
  records_show: ClaimItem[];
  worth_investigating: ClaimItem[];
  questions_next: ClaimItem[];
  missing_records: ClaimItem[];
  photo_observations: ClaimItem[];
}

export interface InvestigationReport {
  sections: ReportSections;
  disclaimer: string;
  used_fallback: boolean;
  model_info?: Record<string, any>;
}

export interface InvestigationOutcome {
  id?: number;
  field_id: number;
  symptom_date: string;
  window_days: number;
  report: InvestigationReport;
  used_fallback: boolean;
  verifier_log: Array<{
    step?: number;
    event: string;
    ok?: boolean;
    errors?: string[];
    name?: string;
    reason?: string;
  }>;
  model_info?: Record<string, any>;
  steps?: number;
  created_at?: string;
}

export type Language = 'en' | 'roman' | 'ur';
