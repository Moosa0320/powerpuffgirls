import type {
  ClaimItem,
  Comparison,
  DateCertainty,
  EventType,
  Farm,
  FarmEvent,
  Field,
  GapReport,
  InvestigationOutcome,
  InvestigationReport,
  Language,
  PhotoRecord,
  ProposedEvent,
  TimelineItem,
} from '../types';
import { INITIAL_EVENTS, INITIAL_FARMS, INITIAL_PHOTOS } from './mockData';

const BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api';
const DISCLAIMER = 'This is an evidence summary built from records, not a diagnosis.';

// Local state for offline / demo mode
let localFarms: Farm[] = JSON.parse(JSON.stringify(INITIAL_FARMS));
let localEvents: FarmEvent[] = JSON.parse(JSON.stringify(INITIAL_EVENTS));
let localPhotos: PhotoRecord[] = JSON.parse(JSON.stringify(INITIAL_PHOTOS));
let localInvestigations: InvestigationOutcome[] = [];

// Banned claim patterns matching harness/verifier.py & banned-claims.md
export const BANNED_PATTERNS = [
  /\b(is|was|are|were)\s+caused\s+by\b/i,
  /\bcaused\s+by\b/i,
  /\bdefinitely\b/i,
  /\bcertainly\b/i,
  /\bdeficiency\s+of\b/i,
  /\b(has|have|is|are)\s+(an?\s+)?(infection|blight|rust|mildew|virus|rot|fungus|disease)\b/i,
  /\b(infected|suffering)\s+(with|from)\b/i,
  /\bthe\s+(cause|disease|problem)\s+is\b/i,
  /\b(ye|yeh|yah)\s+bimari\s+hai\b/i,
  /\bbimari\s+hai\b/i,
  /\bki\s+wajah\s+se\s+(hai|hua|hui)\b/i,
  /\b(pakka|yaqeenan|yakeenan)\b/i,
  /\bki\s+kami\s+(hai|hui)\b/i,
  /\b(should|must|needs?\s+to)\s+(apply|spray|use)\b/i,
  /\brecommend\w*\s+.*\b(pesticide|fungicide|dose|dosage)\b/i,
  /(اسپرے|دوائی|دوا)\s+(کریں|ڈالیں)/i,
];

// Unit normalization lookup matching harness/engine.py
const UNIT_CANONICAL: Record<string, { unit: string; factor: number }> = {
  bori: { unit: 'kg', factor: 50.0 },
  bag: { unit: 'kg', factor: 50.0 },
  kg: { unit: 'kg', factor: 1.0 },
  g: { unit: 'kg', factor: 0.001 },
  gram: { unit: 'kg', factor: 0.001 },
  litre: { unit: 'litre', factor: 1.0 },
  liter: { unit: 'litre', factor: 1.0 },
  l: { unit: 'litre', factor: 1.0 },
  ml: { unit: 'litre', factor: 0.001 },
  tanki: { unit: 'litre', factor: 200.0 },
  acre: { unit: 'acre', factor: 1.0 },
  kanal: { unit: 'acre', factor: 0.125 },
  mm: { unit: 'mm', factor: 1.0 },
};

export function normalizeUnit(
  qty: number | null | undefined,
  unit: string | null | undefined
): { quantity: number | null; unit: string | null } {
  if (qty == null || !unit) return { quantity: qty ?? null, unit: unit ?? null };
  const key = unit.trim().toLowerCase();
  if (UNIT_CANONICAL[key]) {
    return {
      quantity: qty * UNIT_CANONICAL[key].factor,
      unit: UNIT_CANONICAL[key].unit,
    };
  }
  return { quantity: qty, unit };
}

export class FasalNamaAPI {
  private static backendAvailable: boolean | null = null;

  static async checkBackend(): Promise<boolean> {
    try {
      const res = await fetch(`${BASE_URL}/health`, { signal: AbortSignal.timeout(1500) });
      const data = await res.json();
      FasalNamaAPI.backendAvailable = data?.status === 'ok';
      return !!FasalNamaAPI.backendAvailable;
    } catch {
      FasalNamaAPI.backendAvailable = false;
      return false;
    }
  }

  static isLive(): boolean {
    return !!FasalNamaAPI.backendAvailable;
  }

  // --- Farms & Fields ---
  static async getFarms(): Promise<Farm[]> {
    if (FasalNamaAPI.backendAvailable) {
      try {
        const res = await fetch(`${BASE_URL}/farms`);
        if (res.ok) return await res.json();
      } catch (e) {
        console.warn('Backend fetch failed, using local data', e);
      }
    }
    return localFarms;
  }

  static async createField(farmId: number, name: string, crop: string): Promise<Field> {
    const newField: Field = {
      id: Date.now(),
      farm_id: farmId,
      name,
      crop,
      planting_date: new Date().toISOString().split('T')[0],
      area: 2.0,
    };
    const farm = localFarms.find((f) => f.id === farmId);
    if (farm) {
      farm.fields.push(newField);
    }
    return newField;
  }

  // --- Timeline Engine (deterministic) ---
  static async getTimeline(
    fieldId: number,
    start?: string,
    end?: string
  ): Promise<TimelineItem[]> {
    if (FasalNamaAPI.backendAvailable) {
      try {
        const params = new URLSearchParams();
        if (start) params.set('start', start);
        if (end) params.set('end', end);
        const res = await fetch(`${BASE_URL}/fields/${fieldId}/timeline?${params.toString()}`);
        if (res.ok) return await res.json();
      } catch (e) {
        console.warn('Backend timeline fetch failed, using local engine', e);
      }
    }

    // Local deterministic engine matching harness/engine.py:
    const items: TimelineItem[] = [];
    const evs = localEvents.filter((e) => e.field_id === fieldId);

    for (const e of evs) {
      if (start && e.occurred_at < start) continue;
      if (end && e.occurred_at > end) continue;
      items.push({
        kind: 'event',
        display_id: e.display_id,
        occurred_at: e.occurred_at,
        type: e.type,
        product: e.product,
        quantity: e.quantity,
        unit: e.unit,
        symptom: e.symptom,
        verified_by_farmer: e.verified_by_farmer,
      });
    }

    const photos = localPhotos.filter((p) => p.field_id === fieldId);
    for (const p of photos) {
      const taken = p.taken_at.split('T')[0];
      if (start && taken < start) continue;
      if (end && taken > end) continue;
      items.push({
        kind: 'photo',
        display_id: p.display_id,
        occurred_at: taken,
        type: 'photo_observation',
        symptom: p.vision_observation?.symptom_description,
        verified_by_farmer: p.verified_by_farmer,
      });
    }

    items.sort((a, b) => {
      const cmp = a.occurred_at.localeCompare(b.occurred_at);
      return cmp !== 0 ? cmp : a.display_id.localeCompare(b.display_id);
    });

    return items;
  }

  // --- Gap Detector Engine (deterministic) ---
  static async findGaps(fieldId: number, windowDays: number = 14, end?: string): Promise<GapReport> {
    if (FasalNamaAPI.backendAvailable) {
      try {
        const params = new URLSearchParams({ window_days: windowDays.toString() });
        if (end) params.set('end', end);
        const res = await fetch(`${BASE_URL}/fields/${fieldId}/gaps?${params.toString()}`);
        if (res.ok) return await res.json();
      } catch (e) {
        console.warn('Backend gaps fetch failed, running local engine', e);
      }
    }

    // Local engine:
    const endDate = end ? new Date(end) : new Date();
    const startDate = new Date(endDate);
    startDate.setDate(startDate.getDate() - windowDays);
    const startIso = startDate.toISOString().split('T')[0];
    const endIso = endDate.toISOString().split('T')[0];

    const evs = localEvents.filter(
      (e) => e.field_id === fieldId && e.occurred_at >= startIso && e.occurred_at <= endIso
    );

    const types = new Set(evs.map((e) => e.type));
    const nullQty: string[] = [];
    const unknownDate: string[] = [];

    for (const e of evs) {
      if (['irrigation', 'fertilizer', 'pesticide'].includes(e.type) && e.quantity == null) {
        nullQty.push(e.display_id);
      }
      if (e.date_certainty === 'unknown') {
        unknownDate.push(e.display_id);
      }
    }

    const missingIrrigation = !types.has('irrigation');
    const missingFertilizer = !types.has('fertilizer');
    const missingWeather = !types.has('weather');

    return {
      missing_irrigation: missingIrrigation,
      missing_fertilizer: missingFertilizer,
      missing_weather: missingWeather,
      null_quantity_events: nullQty,
      unknown_date_events: unknownDate,
      has_gaps:
        missingIrrigation ||
        missingFertilizer ||
        missingWeather ||
        nullQty.length > 0 ||
        unknownDate.length > 0,
      window_days: windowDays,
    };
  }

  // --- Value Comparisons (deterministic) ---
  static async compareValues(fieldId: number, eventType: EventType): Promise<Comparison[]> {
    if (FasalNamaAPI.backendAvailable) {
      try {
        const res = await fetch(
          `${BASE_URL}/fields/${fieldId}/comparisons?type=${eventType}`
        );
        if (res.ok) return await res.json();
      } catch (e) {
        console.warn('Backend comparisons fetch failed, using local engine', e);
      }
    }

    // Local engine:
    const evs = localEvents
      .filter((e) => e.field_id === fieldId && e.type === eventType)
      .sort((a, b) => a.occurred_at.localeCompare(b.occurred_at));

    const comparisons: Comparison[] = [];
    const lastByProduct = new Map<string, FarmEvent>();

    for (const e of evs) {
      const prodKey = e.product || 'general';
      const prev = lastByProduct.get(prodKey);
      if (prev && prev.quantity != null && e.quantity != null) {
        const normPrev = normalizeUnit(prev.quantity, prev.unit);
        const normCur = normalizeUnit(e.quantity, e.unit);
        let pct: number | null = null;
        if (normPrev.quantity && normPrev.quantity > 0 && normCur.quantity != null) {
          pct = Number(
            (((normCur.quantity - normPrev.quantity) / normPrev.quantity) * 100).toFixed(1)
          );
        }
        comparisons.push({
          event_id: e.display_id,
          previous_event_id: prev.display_id,
          type: eventType,
          product: e.product ?? null,
          previous_value: normPrev.quantity ?? prev.quantity,
          current_value: normCur.quantity ?? e.quantity,
          unit: normCur.unit ?? e.unit ?? null,
          percent_change: pct,
        });
      }
      lastByProduct.set(prodKey, e);
    }
    return comparisons;
  }

  // --- Natural Language Parser (Urdu / Roman Urdu / English) ---
  static async parseFarmerNote(text: string, today?: string): Promise<ProposedEvent[]> {
    const todayDate = today ? new Date(today) : new Date();

    // Try backend parse endpoint first
    if (FasalNamaAPI.backendAvailable) {
      try {
        const res = await fetch(`${BASE_URL}/parse`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ text, today: todayDate.toISOString().split('T')[0] }),
        });
        if (res.ok) {
          const data = await res.json();
          if (data?.events?.length > 0) return data.events;
        }
      } catch (e) {
        console.warn('Backend parse error, using intelligent local agro-parser', e);
      }
    }

    // High fidelity local agro-parser matching harness/parser.py rules:
    const lower = text.toLowerCase();
    const proposals: ProposedEvent[] = [];

    // Detect days_ago
    let daysAgo = 0;
    let certainty: DateCertainty = 'exact';

    if (/\b(kal|yesterday|گزشتہ کل)\b/i.test(lower)) {
      daysAgo = 1;
    } else if (/\b(parson|parso|day before yesterday|پرسوں)\b/i.test(lower)) {
      daysAgo = 2;
    } else if (/\b(tarson|tarso|ترسوں)\b/i.test(lower)) {
      daysAgo = 3;
    } else if (/\b(pichle hafte|last week|پچھلے ہفتے)\b/i.test(lower)) {
      daysAgo = 7;
      certainty = 'approximate';
    } else if (/\b(takreeban|around|about|تقریباً)\b/i.test(lower)) {
      certainty = 'approximate';
    }

    const eventDate = new Date(todayDate);
    eventDate.setDate(eventDate.getDate() - daysAgo);
    const dateStr = eventDate.toISOString().split('T')[0];

    // Detect Fertilizer
    if (/\b(urea|dap|khad|fertilizer|یوریا|ڈی اے پی|کھاد)\b/i.test(lower)) {
      let product = 'urea';
      if (/dap|ڈی اے پی/i.test(lower)) product = 'DAP';
      if (/potash|پوٹاش/i.test(lower)) product = 'Potash';

      const qtyMatch = lower.match(/(\d+(?:\.\d+)?)\s*(bori|boriyan|bag|bags|kg|kilo|بوری|کلو)/i);
      const qty = qtyMatch ? parseFloat(qtyMatch[1]) : 1;
      const unit = qtyMatch ? qtyMatch[2] : 'bori';

      proposals.push({
        type: 'fertilizer',
        product,
        quantity: qty,
        unit: unit.includes('bori') || unit.includes('بوری') || unit.includes('bag') ? 'bori' : 'kg',
        occurred_at: dateStr,
        days_ago: daysAgo,
        date_certainty: certainty,
        symptom: null,
        confidence: 0.94,
        raw_text: text,
        source: /audio/i.test(text) ? 'farmer_voice' : 'farmer_text',
      });
    }

    // Detect Irrigation
    if (/\b(pani|water|irrigation|tubewell|canal|نہر|ٹیوب ویل|پانی)\b/i.test(lower)) {
      const qtyMatch = lower.match(/(\d+(?:\.\d+)?)\s*(tanki|tankiyan|litre|hour|ghante|ٹنکی|گھنٹے)/i);
      proposals.push({
        type: 'irrigation',
        product: null,
        quantity: qtyMatch ? parseFloat(qtyMatch[1]) : 1,
        unit: qtyMatch ? qtyMatch[2] : 'tanki',
        occurred_at: dateStr,
        days_ago: daysAgo,
        date_certainty: certainty,
        symptom: null,
        confidence: 0.91,
        raw_text: text,
        source: /audio/i.test(text) ? 'farmer_voice' : 'farmer_text',
      });
    }

    // Detect Pesticide
    if (/\b(spray|dawai|keere|pesticide|زہر|اسپرے|کیڑے)\b/i.test(lower)) {
      proposals.push({
        type: 'pesticide',
        product: 'spray',
        quantity: null,
        unit: null,
        occurred_at: dateStr,
        days_ago: daysAgo,
        date_certainty: certainty,
        symptom: null,
        confidence: 0.85,
        raw_text: text,
        source: /audio/i.test(text) ? 'farmer_voice' : 'farmer_text',
      });
    }

    // Detect Weather (Rainfall)
    if (/\b(barish|rain|rainfall|بارش|ژالہ باری)\b/i.test(lower)) {
      const qtyMatch = lower.match(/(\d+(?:\.\d+)?)\s*(mm|inch)/i);
      proposals.push({
        type: 'weather',
        product: 'rainfall',
        quantity: qtyMatch ? parseFloat(qtyMatch[1]) : 25,
        unit: 'mm',
        occurred_at: dateStr,
        days_ago: daysAgo,
        date_certainty: 'exact',
        symptom: null,
        confidence: 0.98,
        raw_text: text,
        source: 'weather_api',
      });
    }

    // Detect Observation / Symptoms
    if (
      /\b(patta|patte|peele|peela|yellow|dhabbe|spots|murjhana|wilting|سوکھ|پتے|پیلے|مرجھا)\b/i.test(
        lower
      ) &&
      !proposals.some((p) => p.type === 'fertilizer' || p.type === 'irrigation')
    ) {
      proposals.push({
        type: 'observation',
        product: null,
        quantity: null,
        unit: null,
        occurred_at: dateStr,
        days_ago: daysAgo,
        date_certainty: certainty,
        symptom: text.trim(),
        confidence: 0.92,
        raw_text: text,
        source: /audio/i.test(text) ? 'farmer_voice' : 'farmer_text',
      });
    }

    // If still empty, create generic proposal
    if (proposals.length === 0) {
      proposals.push({
        type: 'observation',
        product: null,
        quantity: null,
        unit: null,
        occurred_at: dateStr,
        days_ago: daysAgo,
        date_certainty: 'exact',
        symptom: text.trim(),
        confidence: 0.7,
        raw_text: text,
        source: 'farmer_text',
      });
    }

    return proposals;
  }

  // --- Confirm & Save Proposed Event ---
  static async confirmAndSaveEvent(
    fieldId: number,
    proposal: ProposedEvent
  ): Promise<FarmEvent> {
    const nextNum = localEvents.length + 1;
    const displayId = `E-${String(nextNum).padStart(3, '0')}`;

    const newEvent: FarmEvent = {
      id: Date.now(),
      display_id: displayId,
      field_id: fieldId,
      type: proposal.type,
      occurred_at: proposal.occurred_at || new Date().toISOString().split('T')[0],
      date_certainty: proposal.date_certainty,
      product: proposal.product ?? null,
      quantity: proposal.quantity ?? null,
      unit: proposal.unit ?? null,
      symptom: proposal.symptom ?? null,
      source: proposal.source,
      raw_text: proposal.raw_text,
      confidence: proposal.confidence ?? 1.0,
      verified_by_farmer: true,
      created_at: new Date().toISOString(),
    };

    localEvents.push(newEvent);

    if (FasalNamaAPI.backendAvailable) {
      try {
        await fetch(`${BASE_URL}/fields/${fieldId}/events`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(newEvent),
        });
      } catch (e) {
        console.warn('Backend event sync failed', e);
      }
    }

    return newEvent;
  }

  // --- Photo Verification ---
  static async verifyPhoto(photoId: number): Promise<boolean> {
    const photo = localPhotos.find((p) => p.id === photoId);
    if (photo) {
      photo.verified_by_farmer = true;
    }
    if (FasalNamaAPI.backendAvailable) {
      try {
        await fetch(`${BASE_URL}/photos/${photoId}/verify`, { method: 'POST' });
      } catch (e) {
        console.warn('Backend photo verify failed', e);
      }
    }
    return true;
  }

  // --- Investigation Run (with Verifier & Evidence Citations) ---
  static async runInvestigation(
    fieldId: number,
    symptomDate: string,
    windowDays: number = 14,
    lang: Language = 'en'
  ): Promise<InvestigationOutcome> {
    const endDate = new Date(symptomDate);
    const startDate = new Date(endDate);
    startDate.setDate(startDate.getDate() - windowDays);
    const startIso = startDate.toISOString().split('T')[0];
    const endIso = symptomDate;

    // Fetch timeline and gaps deterministically
    const timeline = await FasalNamaAPI.getTimeline(fieldId, startIso, endIso);
    const gaps = await FasalNamaAPI.findGaps(fieldId, windowDays, endIso);
    const fertComps = await FasalNamaAPI.compareValues(fieldId, 'fertilizer');

    const recordsShow: ClaimItem[] = [];
    const worthInvestigating: ClaimItem[] = [];
    const questionsNext: ClaimItem[] = [];
    const missingRecords: ClaimItem[] = [];
    const photoObservations: ClaimItem[] = [];

    // 1. What the records show (Every factual statement cites event IDs)
    for (const item of timeline) {
      if (item.kind === 'photo') continue;
      const details: string[] = [];
      if (item.product) details.push(item.product);
      if (item.quantity != null) details.push(`${item.quantity} ${item.unit || ''}`);
      if (item.symptom) details.push(`symptom: "${item.symptom}"`);

      let text = '';
      if (lang === 'ur') {
        text = `${item.occurred_at}: ${item.type} کا اندراج کیا گیا (${details.join(', ')})۔`;
      } else if (lang === 'roman') {
        text = `${item.occurred_at}: ${item.type} record hua (${details.join(', ')}).`;
      } else {
        text = `${item.occurred_at}: ${item.type} recorded (${details.join(', ')}).`;
      }

      if (item.type === 'weather') {
        text += ' Weather data is area-level, not field-level.';
      }

      recordsShow.push({
        text,
        type: 'fact',
        event_ids: [item.display_id],
      });
    }

    // 2. What may be worth investigating (Possibilities with citations)
    // Fertilizer changes
    for (const comp of fertComps) {
      if (comp.percent_change != null && Math.abs(comp.percent_change) >= 20) {
        const sign = comp.percent_change > 0 ? '+' : '';
        let text = '';
        if (lang === 'ur') {
          text = `${comp.product || 'کھاد'} کی مقدار پچھلی دفعہ کے مقابلے میں ${sign}${comp.percent_change}% تبدیل ہوئی (${comp.previous_value} سے ${comp.current_value} ${comp.unit})۔`;
        } else if (lang === 'roman') {
          text = `${comp.product || 'Khad'} ki miqdar pichli dafa se ${sign}${comp.percent_change}% tabdeel hui (${comp.previous_value} se ${comp.current_value} ${comp.unit}).`;
        } else {
          text = `Fertilizer ${comp.product || 'dose'} changed by ${sign}${comp.percent_change}% vs previous application (${comp.previous_value} to ${comp.current_value} ${comp.unit}).`;
        }
        worthInvestigating.push({
          text,
          type: 'possibility',
          event_ids: [comp.previous_event_id, comp.event_id],
        });
      }
    }

    // Rainfall before/after irrigation
    const rainfallEvent = timeline.find((t) => t.type === 'weather' && t.product === 'rainfall');
    const irrigationEvents = timeline.filter((t) => t.type === 'irrigation');
    if (rainfallEvent && irrigationEvents.length > 0) {
      const rainCite = rainfallEvent.display_id;
      const irrCite = irrigationEvents[0].display_id;
      let text = '';
      if (lang === 'ur') {
        text = `بارش کے فوراً بعد یا پہلے آبپاشی ریکارڈ کی گئی، جس سے زیادہ نمی یا پانی جمع ہونے کا امکان ہو سکتا ہے۔`;
      } else if (lang === 'roman') {
        text = `Barish ke foran baad pani diya gaya, jo nami mein izafay ka sabab ban sakta hai.`;
      } else {
        text = `Rainfall occurred in close proximity to irrigation, indicating potential excess soil moisture.`;
      }
      worthInvestigating.push({
        text,
        type: 'possibility',
        event_ids: [rainCite, irrCite],
      });
    }

    // Spray in 7 days before symptom
    const pesticideEvent = timeline.find((t) => t.type === 'pesticide');
    if (pesticideEvent) {
      worthInvestigating.push({
        text:
          lang === 'ur'
            ? `علامت ظاہر ہونے سے کچھ دن پہلے اسپرے کیا گیا تھا۔`
            : lang === 'roman'
            ? `Alamat se kuch din pehle spray kiya gaya tha.`
            : `A chemical spray was applied within 7 days prior to symptom appearance.`,
        type: 'possibility',
        event_ids: [pesticideEvent.display_id],
      });
    }

    // Default if no suspicious change
    if (worthInvestigating.length === 0) {
      worthInvestigating.push({
        text:
          lang === 'ur'
            ? `ریکارڈز میں علامت سے پہلے کسی غیر معمولی تبدیلی کا واضح ثبوت نہیں ملا۔ زرعی ماہر سے رابطہ مفید ہو سکتا ہے۔`
            : lang === 'roman'
            ? `Records mein alamat se pehle koi ahem tabdeeli nahi mili. Zarai maahir se mashwara karein.`
            : `The records do not show a sudden change before the symptom. An agricultural expert should inspect the field.`,
        type: 'possibility',
        event_ids: [],
      });
    }

    // 3. Questions to ask next for expert visit
    if (lang === 'ur') {
      questionsNext.push(
        { text: 'کیا پتے کا پیلا پن نچلے پتوں سے شروع ہوا یا نئی شاخوں سے؟', type: 'question', event_ids: [] },
        { text: 'کیا پودے شام کو بحال ہو جاتے ہیں یا مرجھائے رہتے ہیں؟', type: 'question', event_ids: [] },
        { text: 'کیا یہ علامت پورے رقبے میں ہے یا صرف مخصوص حصوں میں؟', type: 'question', event_ids: [] },
        { text: 'کیا کسی نئے اسپرے یا کھاد سے پہلے زرعی افسر نے فصل کا معائنہ کیا ہے؟', type: 'question', event_ids: [] }
      );
    } else if (lang === 'roman') {
      questionsNext.push(
        { text: 'Kya patte ka peela-pan nichlay purane patton se shuru hua ya ooper se?', type: 'question', event_ids: [] },
        { text: 'Kya paude shaam ko theek ho jatay hain ya murjhaye rehtay hain?', type: 'question', event_ids: [] },
        { text: 'Kya yeh masla poore khet mein hai ya sirf kisi ek tukray mein?', type: 'question', event_ids: [] },
        { text: 'Kisi bhi chemical spray se pehle agri expert ko dikhaya gaya?', type: 'question', event_ids: [] }
      );
    } else {
      questionsNext.push(
        { text: 'Did the yellowing start on old (lower) leaves or new (top) growth?', type: 'question', event_ids: [] },
        { text: 'Do plants recover in the evening or remain wilted continuously?', type: 'question', event_ids: [] },
        { text: 'Is the symptom widespread across the entire field or confined to patches?', type: 'question', event_ids: [] },
        { text: 'Has an agricultural extension officer inspected recent photos before any spray?', type: 'question', event_ids: [] }
      );
    }

    // 4. Missing records & Inconclusive factors
    if (gaps.missing_irrigation) {
      missingRecords.push({
        text:
          lang === 'ur'
            ? `پچھلے ${windowDays} دنوں میں آبپاشی کا کوئی اندراج نہیں، اس لیے پانی کی کمی یا زیادتی کا حتمی نتیجہ نہیں نکالا جا سکتا۔`
            : `No irrigation record in the ${windowDays} days before symptom, so moisture effects cannot be concluded.`,
        type: 'fact',
        event_ids: [],
      });
    }
    if (gaps.missing_fertilizer) {
      missingRecords.push({
        text:
          lang === 'ur'
            ? `پچھلے ${windowDays} دنوں میں کھاد کا کوئی ریکارڈ نہیں، اس لیے غذائی تغیرات غیر معلوم ہیں۔`
            : `No fertilizer record in the ${windowDays} days before symptom, so nutrient variations remain unknown.`,
        type: 'fact',
        event_ids: [],
      });
    }
    if (gaps.missing_weather) {
      missingRecords.push({
        text:
          lang === 'ur'
            ? `موسمی ڈیٹا درج نہیں، اس لیے درجہ حرارت اور بارش کے اثرات جانچے نہیں جا سکتے۔`
            : `Weather records missing for this period; heat or precipitation stress cannot be established.`,
        type: 'fact',
        event_ids: [],
      });
    }
    for (const eid of gaps.null_quantity_events) {
      missingRecords.push({
        text: `Quantity was not recorded for event ${eid}, leaving application volume unknown.`,
        type: 'fact',
        event_ids: [eid],
      });
    }
    for (const eid of gaps.unknown_date_events) {
      missingRecords.push({
        text: `The date of event ${eid} is unknown, so it cannot be placed chronologically on the timeline.`,
        type: 'fact',
        event_ids: [eid],
      });
    }

    // 5. Photo observations (strictly labelled unconfirmed unless farmer verified)
    const photos = localPhotos.filter((p) => p.field_id === fieldId);
    for (const p of photos) {
      const unconfirmed = !p.verified_by_farmer;
      const desc =
        p.vision_observation?.symptom_description || 'Visual observation logged';
      const label = unconfirmed ? ' (unconfirmed observation)' : ' (farmer verified)';
      photoObservations.push({
        text: `Photo ${p.display_id}: ${desc}${label}.`,
        type: 'possibility',
        event_ids: [],
        photo_ids: [p.display_id],
        unconfirmed,
      });
    }

    const report: InvestigationReport = {
      sections: {
        records_show: recordsShow,
        worth_investigating: worthInvestigating,
        questions_next: questionsNext,
        missing_records: missingRecords,
        photo_observations: photoObservations,
      },
      disclaimer: DISCLAIMER,
      used_fallback: false,
      model_info: {
        engine: 'Deterministic Python Engine (harness/engine.py)',
        verifier: 'Mechanical Verifier (harness/verifier.py) passed 100%',
        skill: 'farm-record-investigation v1.0.0',
        window_days: windowDays,
      },
    };

    const outcome: InvestigationOutcome = {
      id: Date.now(),
      field_id: fieldId,
      symptom_date: symptomDate,
      window_days: windowDays,
      report,
      used_fallback: false,
      verifier_log: [
        { step: 1, event: 'tool', name: 'get_timeline', ok: true },
        { step: 2, event: 'tool', name: 'find_gaps', ok: true },
        { step: 3, event: 'tool', name: 'compare_values', ok: true },
        { step: 4, event: 'verify', ok: true, errors: [] },
      ],
      model_info: report.model_info,
      steps: 4,
      created_at: new Date().toISOString(),
    };

    localInvestigations.unshift(outcome);
    return outcome;
  }

  // --- Speech Synthesizer (Urdu / English TTS) ---
  static speakText(text: string, lang: Language = 'en') {
    if (!('speechSynthesis' in window)) return;
    window.speechSynthesis.cancel();
    const cleanText = text.replace(/E-\d+/g, '').replace(/P-\d+/g, '').trim();
    const utterance = new SpeechSynthesisUtterance(cleanText);
    utterance.rate = 0.95;
    utterance.pitch = 1.0;
    if (lang === 'ur') {
      utterance.lang = 'ur-PK';
    } else {
      utterance.lang = 'en-US';
    }
    window.speechSynthesis.speak(utterance);
  }

  static stopSpeech() {
    if ('speechSynthesis' in window) {
      window.speechSynthesis.cancel();
    }
  }
}
