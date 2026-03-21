# ShieldHer API — Frontend integration specification

**Version:** 0.1.0 (see `app/main.py`)  
**Base path:** `/api/v1` for all domain routes below.  
**Health:** `GET /health` — returns `{"status":"ok","env":"<APP_ENV>"}` (no auth).

This document mirrors the current FastAPI implementation. Interactive OpenAPI UI is available at **`/docs`** and **`/redoc`** only when `APP_ENV=development`.

---

## 1. Conventions

| Topic | Rule |
|--------|------|
| **Protocol** | HTTPS in production |
| **JSON** | `Content-Type: application/json` for bodies; UTF-8 |
| **IDs** | UUIDs (string in JSON), RFC 4122 |
| **Times** | Responses use ISO 8601 datetimes where applicable; stored/processed in UTC |
| **Coordinates** | WGS84 decimal degrees; `lat` ∈ [-90, 90], `lng` ∈ [-180, 180] |
| **CORS** | In development, `allow_origins=["*"]`. In non-development, CORS allows an empty list — configure the deployment (reverse proxy / env) for real origins |

---

## 2. Authentication

### 2.1 Firebase → ShieldHer JWT

**`POST /api/v1/auth/verify-token`**

Exchanges a Firebase Phone Auth **ID token** for a ShieldHer JWT. No `Authorization` header required.

**Request body**

| Field | Type | Required | Notes |
|-------|------|----------|--------|
| `firebase_id_token` | string | yes | Firebase ID token from the client SDK |
| `name` | string | yes | 1–120 chars |
| `role` | string | yes | `"person"` or `"shield"` — initial role |
| `emergency_contact_name` | string \| null | no | max 120 chars |
| `emergency_contact_phone` | string \| null | no | max 20 chars (E.164 typical) |

**Response `200`** — `TokenResponse`

| Field | Type | Notes |
|-------|------|--------|
| `access_token` | string | ShieldHer JWT |
| `token_type` | string | Always `"bearer"` |
| `user_id` | UUID | Internal user id |
| `phone` | string | From Firebase / profile |
| `role` | string | User role after upsert |

**JWT:** Algorithm HS256. Expiry is controlled by **`JWT_EXPIRE_MINUTES`** (default in config: `10080` minutes). Claims are implementation-defined; treat `access_token` as opaque and send it on protected routes.

### 2.2 Bearer token (protected routes)

Send on every authenticated request:

```http
Authorization: Bearer <access_token>
```

Failure modes:

| Status | Typical `detail` |
|--------|-------------------|
| `401` | Missing/invalid JWT, malformed payload, user missing or deactivated |
| `403` | Wrong role or shield not verified (see per-route notes) |

---

## 3. Error format

- **HTTPException:** `{"detail": "<message>"}` (string or structured, depending on FastAPI usage).
- **Validation (422):** FastAPI/Pydantic default validation error body (field-level errors).

---

## 4. Auth API

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/api/v1/auth/verify-token` | None | Exchange Firebase token for JWT (see §2.1) |

---

## 5. Location API

Prefix: **`/api/v1/location`**

All routes require **`Authorization: Bearer`**.

| Method | Path | Role | Request body | Success |
|--------|------|------|--------------|---------|
| PATCH | `/shield` | Verified **shield** (`require_shield`: role `shield`, `id_verified=true`) | `UpdateLocationRequest` | **204** empty |
| PATCH | `/incident/{incident_id}` | **person** (must own active incident) | `UpdateLocationRequest` | **204** empty |
| GET | `/incident/{incident_id}/all` | Any authenticated user | — | **200** `IncidentLocationsResponse` |

**`UpdateLocationRequest`**

| Field | Type |
|-------|------|
| `lat` | float |
| `lng` | float |

**`IncidentLocationsResponse`**

| Field | Type |
|-------|------|
| `incident_id` | string |
| `person` | `PersonLocationResponse` \| null |
| `shields` | array of `ShieldLocationResponse` |

**`PersonLocationResponse`:** `lat`, `lng`, `updated_at` (string \| null)  

**`ShieldLocationResponse`:** `shield_id` (string), `lat`, `lng`, `updated_at` (string \| null)

**Errors:** `404` on PATCH `/incident/{id}` if no active incident owned by caller. Shield endpoints return `403` if not verified shield.

**Note:** Live positions are backed by Redis with TTL semantics (stale keys may be empty). The client should PATCH location on an interval while tracking an incident.

---

## 6. Incidents API (SOS lifecycle)

Prefix: **`/api/v1/incidents`**

All routes require **`Authorization: Bearer`**.

| Method | Path | Role / rule | Request body | Success response |
|--------|------|-------------|--------------|------------------|
| POST | `/trigger` | **`person` only** | `TriggerSOSRequest` | **201** `TriggerSOSResponse` |
| POST | `/{incident_id}/respond` | Verified **shield** | `RespondToIncidentRequest` | **200** `RespondToIncidentResponse` or **204** no body |
| POST | `/{incident_id}/all-clear` | **`person`**, must be incident owner | — | **200** `AllClearResponse` |
| GET | `/{incident_id}` | Any authenticated user | — | **200** `IncidentDetailResponse` |
| GET | `/{incident_id}/elevenlabs-token` | **Incident owner only** | — | **200** `ElevenLabsTokenResponse` |
| GET | `/{incident_id}/context` | Any authenticated user | — | **200** `IncidentContextResponse` |

### Request / response models

**`TriggerSOSRequest`:** `lat`, `lng` (floats)

**`TriggerSOSResponse`**

| Field | Type |
|-------|------|
| `incident_id` | UUID |
| `shields_notified` | int |
| `convergence_point` | `{ lat, lng }` \| null |

**`RespondToIncidentRequest`**

| Field | Type |
|-------|------|
| `action` | `"responding"` \| `"declined"` |

**`RespondToIncidentResponse`** (only when `action === "responding"` and server returns 200)

| Field | Type |
|-------|------|
| `convergence_point` | `{ lat, lng }` \| null |
| `other_responding_shields` | array of `RespondingShieldInfo` |

**`RespondingShieldInfo`:** `shield_id` (UUID), `name`, `lat`, `lng` (optional)

**Declined:** **`204 No Content`** — no JSON body.

**`AllClearResponse`**

| Field | Type |
|-------|------|
| `status` | string (default `"resolved"`) |
| `zone_summary` | string \| null — optional Gemini zone summary |

**`IncidentDetailResponse`**

| Field | Type |
|-------|------|
| `incident_id` | UUID |
| `status` | string |
| `trigger_lat`, `trigger_lng` | float |
| `convergence_point` | `{ lat, lng }` \| null |
| `triggered_at` | datetime |
| `resolved_at` | datetime \| null |
| `shields_notified` | int |
| `shields` | array of `ShieldStatusInfo` |
| `person_polyline` | string \| null — encoded polyline for walking route |

**`ShieldStatusInfo`:** `shield_id`, `name`, `status`, `lat`, `lng`, `eta_seconds` (int \| null)

**`ElevenLabsTokenResponse`:** `signed_url` (string), `incident_id` (UUID) — short-lived URL for the conversational AI client; API key stays server-side.

**`IncidentContextResponse`** — string fields for ElevenLabs `dynamicVariables` (all human-readable strings):

| Field |
|-------|
| `shield_count` |
| `nearest_distance` |
| `nearest_eta` |
| `convergence_address` |
| `incident_status` |
| `area_safety_note` |

**Typical errors:** `403` if role mismatch (e.g. non-person triggers SOS); `404` if incident missing where applicable.

---

## 7. Hotspots API

Prefix: **`/api/v1/hotspots`**

Requires **`Authorization: Bearer`** (any role).

| Method | Path | Query | Response |
|--------|------|-------|----------|
| GET | `/context` | `lat`, `lng` (required floats) | **200** `HotspotContextResponse` |
| GET | `/summary` | `lat`, `lng` (required floats) | **200** `HotspotSummaryResponse` |

**`HotspotContextResponse`**

| Field | Type |
|-------|------|
| `risk_level` | `"low"` \| `"medium"` \| `"high"` |
| `total_incidents` | int |
| `gemini_summary` | string |
| `shield_count_nearby` | int — active verified shields within **1 km** |

**`HotspotSummaryResponse`**

| Field | Type |
|-------|------|
| `summary` | string \| null |
| `incident_count` | int \| null |
| `last_incident` | datetime \| null |

---

## 8. Shields API (volunteer profile)

Prefix: **`/api/v1/shields`**

Requires **`Authorization: Bearer`**.

| Method | Path | Notes | Request | Response |
|--------|------|-------|---------|----------|
| POST | `/apply` | Promotes user to shield applicant | `ApplyShieldRequest` | **201** `ApplyShieldResponse` |
| GET | `/me` | Role must be `shield` | — | **200** `ShieldProfileResponse` |
| PATCH | `/me/status` | Toggle active/inactive; going active requires admin verification | `UpdateShieldStatusRequest` | **200** `UpdateShieldStatusResponse` |
| PATCH | `/me/active-hours` | HH:MM times | `UpdateActiveHoursRequest` | **200** `UpdateActiveHoursResponse` |
| PATCH | `/me/device` | Expo push token | `DeviceRegistrationRequest` | **200** `DeviceRegistrationResponse` |

**`ApplyShieldRequest`:** `name` (1–120), `commitment_accepted` (bool, must be `true` or **422**)

**`ApplyShieldResponse`:** `shield_id`, `status`, `message`

**`UpdateShieldStatusRequest`:** `status`: `"active"` \| `"inactive"`

**`UpdateActiveHoursRequest`:** `active_hours_start`, `active_hours_end` — strings `"HH:MM"` (00:00–23:59)

**`ShieldProfileResponse`:** `shield_id`, `user_id`, `name`, `phone`, `status`, `id_verified`, `commitment_signed`, `active_hours_start`, `active_hours_end` (nullable)

**`DeviceRegistrationRequest`:** `expo_push_token` — must start with `ExponentPushToken[`

**`DeviceRegistrationResponse`:** `registered` (bool), `token_preview` (last 8 characters only)

---

## 9. Admin API

Prefix: **`/api/v1/admin`**

Authentication: **`X-Admin-Key`** header must equal the server’s **`ADMIN_API_KEY`** (not the user JWT).

```http
X-Admin-Key: <ADMIN_API_KEY>
```

| Method | Path | Query / body | Response |
|--------|------|--------------|----------|
| GET | `/shields/pending` | — | **200** `PendingShieldsResponse` |
| PATCH | `/shields/{shield_id}/verify` | `VerifyShieldRequest` | **200** `VerifyShieldResponse` |
| GET | `/incidents` | `status` optional (`active` \| `resolved` \| `escalated`), `limit` (1–200, default 50), `offset` (≥0) | **200** `AdminIncidentListResponse` |
| GET | `/stats` | — | **200** `AdminStatsResponse` |

**`VerifyShieldRequest`:** `approved` (bool), `rejection_reason` (string \| null)

**`PendingShieldsResponse`:** `total`, `shields[]` (`PendingShieldItem`: `shield_id`, `user_id`, `name`, `phone`, `commitment_signed`, `applied_at`)

**`AdminIncidentListResponse`:** `total`, `limit`, `offset`, `incidents[]` (`AdminIncidentItem`)

**`AdminIncidentItem`:** `incident_id`, `triggered_by`, `trigger_lat`, `trigger_lng`, `status`, `triggered_at`, `resolved_at`

**`AdminStatsResponse`:** `total_users`, `total_shields`, `active_shields`, `total_incidents`, `resolved_incidents`, `avg_response_time_seconds` (float \| null)

**Errors:** `403` if `X-Admin-Key` missing or wrong.

---

## 10. Development-only routes

Mounted only when **`APP_ENV=development`**. **Do not rely on these in production** — they are absent or unreachable when `APP_ENV` is not `development`.

Prefix still under **`/api/v1`**.

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| POST | `/dev/seed` | None | Wipe/reseed test users and hotspots |
| POST | `/dev/trigger-test-sos` | None | Fake SOS from seeded person |
| POST | `/dev/mock-shield-respond/{incident_id}/{shield_id}` | None | Simulate shield accepting |
| POST | `/dev/test/sms` | None | Queue test SMS |

See `app/routers/dev.py` for exact response models (`SeedResponse`, `TestSMSResponse`, etc.).

---

## 11. Integration checklist for frontend

1. **Login:** Obtain Firebase ID token → `POST /auth/verify-token` → persist `access_token`.
2. **Attach JWT:** `Authorization: Bearer` on all secured calls.
3. **Person SOS flow:** `POST /incidents/trigger` → poll or refresh `GET /incidents/{id}` and `GET /location/incident/{id}/all`; PATCH person location to `/location/incident/{id}`.
4. **Shield flow:** Ensure admin verification if responding to incidents; use `PATCH /location/shield` when active; `POST /incidents/{id}/respond` with `responding` / `declined`.
5. **Voice (optional):** `GET /incidents/{id}/elevenlabs-token` (owner) and `GET /incidents/{id}/context` for dynamic variables.
6. **Push:** Shields register `PATCH /shields/me/device` with Expo token format.
7. **Admin tools:** Use `X-Admin-Key`, not JWT.

---

## 12. Machine-readable spec

When the server runs with `APP_ENV=development`, export the full OpenAPI schema from:

- **`GET /openapi.json`**

Use this for codegen, mocks, or contract tests alongside this document.
