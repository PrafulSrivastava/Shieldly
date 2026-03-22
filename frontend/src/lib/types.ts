/* ── Auth ──────────────────────────────────────────────────────────────── */

export interface VerifyTokenRequest {
  firebase_id_token: string;
  name: string;
  role: "person" | "shield";
  emergency_contact_name?: string;
  emergency_contact_phone?: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  user_id: string;
  phone: string;
  role: "person" | "shield";
}

/* ── Incidents ────────────────────────────────────────────────────────── */

export interface ConvergencePoint {
  lat: number;
  lng: number;
}

export interface TriggerSOSRequest {
  lat: number;
  lng: number;
}

export interface TriggerSOSResponse {
  incident_id: string;
  shields_notified: number;
  convergence_point: ConvergencePoint | null;
  tracking_url: string;
}

export interface ShieldStatusInfo {
  shield_id: string;
  name: string;
  status: string;
  lat: number;
  lng: number;
  eta_seconds: number | null;
}

export interface IncidentDetailResponse {
  incident_id: string;
  status: "active" | "resolved" | "escalated";
  trigger_lat: number;
  trigger_lng: number;
  convergence_point: ConvergencePoint | null;
  triggered_at: string;
  resolved_at: string | null;
  shields_notified: number;
  shields: ShieldStatusInfo[];
  person_polyline: string | null;
  tracking_url: string;
}

export interface IncidentContextResponse {
  shield_count: number;
  nearest_distance: number | null;
  nearest_eta: number | null;
  convergence_address: string | null;
  incident_status: string;
  area_safety_note: string | null;
}

export interface AllClearResponse {
  status: string;
  zone_summary: string | null;
}

export interface ElevenLabsTokenResponse {
  signed_url: string;
  incident_id: string;
}

/* ── Location ─────────────────────────────────────────────────────────── */

export interface LatLng {
  lat: number;
  lng: number;
}

export interface PersonLocationResponse {
  lat: number;
  lng: number;
  updated_at: string;
}

export interface ShieldLocationResponse {
  shield_id: string;
  lat: number;
  lng: number;
  updated_at: string;
}

export interface IncidentLocationsResponse {
  incident_id: string;
  person: PersonLocationResponse | null;
  shields: ShieldLocationResponse[];
}

/* ── Hotspots ─────────────────────────────────────────────────────────── */

export interface HotspotContextResponse {
  risk_level: string;
  total_incidents: number;
  gemini_summary: string | null;
  shield_count_nearby: number;
}

/* ── Tracking (public) ────────────────────────────────────────────────── */

export interface ShieldTrackingInfo {
  shield_index: number;
  lat: number;
  lng: number;
  eta_seconds: number | null;
  status: string;
}

export interface TrackingResponse {
  incident_id: string;
  status: string;
  person_lat: number;
  person_lng: number;
  responding_shields: ShieldTrackingInfo[];
  convergence_lat: number | null;
  convergence_lng: number | null;
  triggered_at: string;
  resolved_at: string | null;
}

/* ── WebSocket messages ───────────────────────────────────────────────── */

export type WSIncoming =
  | { type: "person_location"; lat: number; lng: number }
  | { type: "shield_location"; shield_id: string; lat: number; lng: number }
  | { type: "convergence_update"; lat: number; lng: number }
  | { type: "incident_resolved"; resolved_at: string }
  | { type: "pong" };

/* ── Shield management ────────────────────────────────────────────────── */

export interface RespondToIncidentRequest {
  action: "responding" | "declined";
}

export interface RespondToIncidentResponse {
  convergence_point: ConvergencePoint | null;
  other_responding_shields: Array<{
    shield_id: string;
    name: string;
    lat: number;
    lng: number;
  }>;
}

/* ── Geo helpers ──────────────────────────────────────────────────────── */

export function bearing(from: LatLng, to: LatLng): number {
  const dLon = ((to.lng - from.lng) * Math.PI) / 180;
  const lat1 = (from.lat * Math.PI) / 180;
  const lat2 = (to.lat * Math.PI) / 180;
  const y = Math.sin(dLon) * Math.cos(lat2);
  const x =
    Math.cos(lat1) * Math.sin(lat2) -
    Math.sin(lat1) * Math.cos(lat2) * Math.cos(dLon);
  return (Math.atan2(y, x) * (180 / Math.PI) + 360) % 360;
}

export function haversine(a: LatLng, b: LatLng): number {
  const R = 6_371_000;
  const dLat = ((b.lat - a.lat) * Math.PI) / 180;
  const dLon = ((b.lng - a.lng) * Math.PI) / 180;
  const s =
    Math.sin(dLat / 2) ** 2 +
    Math.cos((a.lat * Math.PI) / 180) *
      Math.cos((b.lat * Math.PI) / 180) *
      Math.sin(dLon / 2) ** 2;
  return R * 2 * Math.atan2(Math.sqrt(s), Math.sqrt(1 - s));
}
