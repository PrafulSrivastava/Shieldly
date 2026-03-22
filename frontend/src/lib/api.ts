import { useStore } from "./store";
import type {
  VerifyTokenRequest,
  TokenResponse,
  TriggerSOSRequest,
  TriggerSOSResponse,
  IncidentDetailResponse,
  IncidentContextResponse,
  ElevenLabsTokenResponse,
  AllClearResponse,
  HotspotContextResponse,
  IncidentLocationsResponse,
  TrackingResponse,
  RespondToIncidentRequest,
  RespondToIncidentResponse,
  NearbyShieldInfo,
} from "./types";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(
  method: string,
  path: string,
  body?: unknown,
): Promise<T> {
  const { token, adminKey } = useStore.getState();

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  if (adminKey) headers["X-Admin-Key"] = adminKey;

  const res = await fetch(path, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

  if (res.status === 204) return undefined as T;

  const data = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }));

  if (!res.ok) {
    throw new ApiError(res.status, data?.detail ?? `HTTP ${res.status}`);
  }
  return data as T;
}

export const api = {
  /* ── Auth ──────────────────────────────────────────────────────────── */
  verifyToken: (req: VerifyTokenRequest) =>
    request<TokenResponse>("POST", "/api/v1/auth/verify-token", req),

  /* ── Incidents ────────────────────────────────────────────────────── */
  triggerSOS: (req: TriggerSOSRequest) =>
    request<TriggerSOSResponse>("POST", "/api/v1/incidents/trigger", req),

  getIncident: (id: string) =>
    request<IncidentDetailResponse>("GET", `/api/v1/incidents/${id}`),

  getIncidentContext: (id: string) =>
    request<IncidentContextResponse>("GET", `/api/v1/incidents/${id}/context`),

  getElevenLabsToken: (id: string) =>
    request<ElevenLabsTokenResponse>(
      "GET",
      `/api/v1/incidents/${id}/elevenlabs-token`,
    ),

  allClear: (id: string) =>
    request<AllClearResponse>("POST", `/api/v1/incidents/${id}/all-clear`),

  respondToIncident: (id: string, req: RespondToIncidentRequest) =>
    request<RespondToIncidentResponse>(
      "POST",
      `/api/v1/incidents/${id}/respond`,
      req,
    ),

  /* ── Location ─────────────────────────────────────────────────────── */
  updatePersonLocation: (incidentId: string, lat: number, lng: number) =>
    request<void>("PATCH", `/api/v1/location/incident/${incidentId}`, {
      lat,
      lng,
    }),

  updateShieldLocation: (lat: number, lng: number) =>
    request<void>("PATCH", "/api/v1/location/shield", { lat, lng }),

  getIncidentLocations: (incidentId: string) =>
    request<IncidentLocationsResponse>(
      "GET",
      `/api/v1/location/incident/${incidentId}/all`,
    ),

  /* ── Nearby shields ──────────────────────────────────────────────── */
  getNearbyShields: (lat: number, lng: number) =>
    request<NearbyShieldInfo[]>(
      "GET",
      `/api/v1/location/shields/nearby?lat=${lat}&lng=${lng}`,
    ),

  /* ── Hotspots ─────────────────────────────────────────────────────── */
  getHotspotContext: (lat: number, lng: number) =>
    request<HotspotContextResponse>(
      "GET",
      `/api/v1/hotspots/context?lat=${lat}&lng=${lng}`,
    ),

  /* ── Tracking (public) ────────────────────────────────────────────── */
  getTracking: (token: string) =>
    request<TrackingResponse>("GET", `/api/v1/track/${token}`),

  /* ── Dev / Seed ───────────────────────────────────────────────────── */
  seed: () => request<unknown>("POST", "/api/v1/dev/seed"),

  triggerTestSOS: () =>
    request<TriggerSOSResponse>("POST", "/api/v1/dev/trigger-test-sos"),

  seedHotspots: () => request<unknown>("POST", "/api/v1/dev/seed-hotspots"),

  mockShieldRespond: (incidentId: string, shieldId: string) =>
    request<unknown>(
      "POST",
      `/api/v1/dev/mock-shield-respond/${incidentId}/${shieldId}`,
    ),
};
