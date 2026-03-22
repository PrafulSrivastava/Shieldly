import { get, patch, post } from './client'

// ── Auth ─────────────────────────────────────────────────────────────────────

export interface TokenResponse {
  access_token: string
  token_type: string
  user_id: string
  phone: string
  role: 'person' | 'shield'
}

export const verifyToken = (
  firebase_id_token: string,
  name: string,
  role: 'person' | 'shield',
) =>
  post<TokenResponse>('/api/v1/auth/verify-token', {
    firebase_id_token,
    name,
    role,
  })

// ── Incidents ─────────────────────────────────────────────────────────────────

export interface TriggerSOSResponse {
  incident_id: string
  shields_notified: number
  convergence_point: { lat: number; lng: number } | null
}

export interface ShieldStatusInfo {
  shield_id: string
  name: string
  status: 'notified' | 'responding' | 'arrived' | 'declined'
  lat: number | null
  lng: number | null
  eta_seconds: number | null
}

export interface IncidentDetail {
  incident_id: string
  status: 'active' | 'resolved' | 'escalated'
  trigger_lat: number
  trigger_lng: number
  convergence_point: { lat: number; lng: number } | null
  triggered_at: string
  resolved_at: string | null
  shields_notified: number
  shields: ShieldStatusInfo[]
  person_polyline: string | null
}

export const triggerSOS = (lat: number, lng: number) =>
  post<TriggerSOSResponse>('/api/v1/incidents/trigger', { lat, lng })

export const getIncident = (id: string) =>
  get<IncidentDetail>(`/api/v1/incidents/${id}`)

export const resolveIncident = (id: string) =>
  post<{ status: string; zone_summary: string | null }>(
    `/api/v1/incidents/${id}/all-clear`,
  )

export const respondToIncident = (
  id: string,
  action: 'responding' | 'declined',
) => post<unknown>(`/api/v1/incidents/${id}/respond`, { action })

// ── Hotspots ──────────────────────────────────────────────────────────────────

export interface HotspotContext {
  risk_level: 'low' | 'medium' | 'high'
  total_incidents: number
  gemini_summary: string
  shield_count_nearby: number
}

export const getHotspotContext = (lat: number, lng: number) =>
  get<HotspotContext>(`/api/v1/hotspots/context?lat=${lat}&lng=${lng}`)

// ── Location ──────────────────────────────────────────────────────────────────

export const updateShieldLocation = (lat: number, lng: number) =>
  patch<void>('/api/v1/location/shield', { lat, lng })

// ── Admin ─────────────────────────────────────────────────────────────────────

export interface MapShield {
  id: string
  name: string
  lat: number
  lng: number
  status: 'active' | 'inactive' | 'pending' | 'rejected'
  last_seen: string | null
}

export interface MapHotspot {
  geohash: string
  lat: number
  lng: number
  incident_count: number
  risk_level: 'low' | 'medium' | 'high'
}

export interface MapData {
  shields: MapShield[]
  hotspots: MapHotspot[]
}

export interface AdminStats {
  total_users: number
  total_shields: number
  active_shields: number
  total_incidents: number
  resolved_incidents: number
  avg_response_time_seconds: number | null
}

export const getMapData = () => get<MapData>('/api/v1/admin/map-data')
export const getAdminStats = () => get<AdminStats>('/api/v1/admin/stats')

// ── Dev seeds ─────────────────────────────────────────────────────────────────

export const seedQuick = () => post<unknown>('/api/v1/dev/seed')
export const seedLarge = () => post<unknown>('/api/v1/dev/seed-large')
export const seedHotspots = () => post<unknown>('/api/v1/dev/seed-hotspots')

export interface SimulateRespondResult {
  incident_id: string
  shields_responded: number
}
export const simulateShieldAccept = (incidentId: string) =>
  post<SimulateRespondResult>(`/api/v1/dev/mock-incident-respond/${incidentId}`)
