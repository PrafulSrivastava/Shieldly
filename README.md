# Shieldly

Real-time women's safety broadcast network. When a woman triggers an SOS, verified nearby Shields (volunteers) are notified simultaneously and both parties are guided to a convergence point via live GPS navigation.

---

## Features

### SOS & Incident Management
- One-tap SOS trigger — creates an incident and immediately broadcasts to all verified, online Shields within range
- Simultaneous SMS + push notifications sent to nearby Shields
- Convergence point computed via Google Maps Directions API so both parties meet at the safest reachable location
- Real-time location streaming for both the person in danger and responding Shields
- All-clear resolution once the person is safe — notifies responding Shields, sends SMS to the emergency contact, and logs the hotspot bucket
- Gemini-generated zone safety summary returned on all-clear so the person gets contextual feedback about the area

### Shield (Volunteer) System
- Any user can apply to become a Shield (must accept volunteer commitment)
- Admin reviews and verifies Shield identity before they can respond to incidents
- Shields set their own status (active/inactive) and preferred availability window
- Only verified, active Shields within range receive SOS broadcasts
- Shields register their Expo push token on device so notifications reach them on iOS and Android

### Push Notifications
- SOS alerts delivered to Shield devices via the Expo Push API (abstracts FCM for Android and APNs for iOS)
- High-priority `sos-alerts` notification channel with sound
- Stale/expired device tokens are automatically cleared when Expo returns `DeviceNotRegistered`
- Push failures are fully fault-tolerant — the SOS trigger flow never stalls due to a notification failure

### Live Location & Real-Time Updates
- Shields stream their GPS position to Redis as they move; positions are broadcast on each active incident's pub/sub channel
- The person's location is updated independently during the active incident
- Every Shield location update that moves the responder >50 m closer triggers a `context_update` broadcast for ElevenLabs voice agent variable sync
- `GET /location/incident/{id}/all` returns all live positions for a given incident (person + all responding Shields)
- `GET /location/shields/nearby` returns active verified Shields within ~3 km for the idle-phase mini-map

### Public Tracking Page
- Every incident generates a unique tracking token at trigger time
- `GET /track/{token}` — no authentication required; returns anonymised incident status, live positions, convergence point, and per-Shield ETAs
- `WS /track/{token}/live` — public WebSocket that subscribes to the incident's Redis pub/sub channel and forwards `shield_location`, `person_location`, `convergence_update`, and `incident_resolved` events in real-time
- Resolved incidents return only metadata (no live positions); the WebSocket closes cleanly on resolution

### AI-Powered Safety Context
- `GET /hotspots/context?lat=&lng=` aggregates recent incident history across a ~3×3 km geohash grid
- Counts active Shields within 1 km
- Calls Gemini to generate a plain-English safety summary for the area

### ElevenLabs Conversational AI
- Voice agent runs on the frontend (WebRTC, client SDK) — the API key never leaves the server
- `GET /incidents/{id}/elevenlabs-token` — incident owner receives a short-lived signed WebSocket URL to start the session
- `GET /incidents/{id}/context` — flat string dict for ElevenLabs `dynamicVariables` (shield count, nearest distance, ETA, convergence address, status, area safety note)
- Redis Pub/Sub broadcasts `context_update` when the nearest Shield moves >50 m closer — frontend calls `conversation.setVariables()` to keep the voice agent current

### Admin Panel
- Review and approve or reject pending Shield applications (rejected Shields may re-apply)
- View all incidents with optional status filter and pagination
- Platform-wide statistics including total incidents and average resolution time
- All admin endpoints are protected by a static API key (`X-Admin-Key` header)

### Authentication
- Phone number OTP via Firebase Auth
- Server verifies the Firebase ID token and issues an internal JWT
- Roles: `person` (default) and `shield`

### Frontend (Next.js)
- Next.js 14 app with Tailwind CSS
- Interactive Leaflet map for live tracking during active incidents
- Mini-map on the idle screen showing nearby active Shields
- SOSButton, RadarPulse, ShieldCounter, NavigationArrow, and VoiceWaveform components
- TranscriptionFeed displays live ElevenLabs voice conversation transcription
- Public tracking page at `/track/[token]` — shareable with trusted contacts, no login required
- Zustand for global state (`useIncident`, `useGeolocation`, `useElevenLabs`, `useWebSocket` hooks)

---

## Tech Stack

| Layer | Technology |
|---|---|
| API | FastAPI (Python 3.11+), fully async |
| Database | PostgreSQL 15 via SQLAlchemy (asyncpg) |
| Cache / Pub-Sub | Redis 7 |
| Migrations | Alembic |
| Auth | Firebase Phone OTP → internal JWT (python-jose) |
| SMS | Brevo Transactional SMS via httpx |
| Maps | Google Maps Directions API via httpx |
| AI | Gemini via httpx |
| Voice | ElevenLabs Conversational AI |
| Push Notifications | Expo Push API (FCM + APNs) |
| Frontend | Next.js 14, React 18, Tailwind CSS, Leaflet, Zustand |
| Local Dev | Docker Compose |

---

## Project Structure

```
app/
  main.py              # FastAPI app init, router registration, lifespan
  config.py            # pydantic-settings — all env vars live here
  database.py          # async engine, session factory, get_db dependency
  redis_client.py      # Redis init/close helpers
  models/              # SQLAlchemy ORM models (one file per table)
  schemas/             # Pydantic request/response models
  routers/             # FastAPI route handlers (thin — call services only)
    auth.py
    incidents.py
    location.py
    shields.py
    hotspots.py
    tracking.py        # Public tracking page + WebSocket
    admin.py
    dev.py             # Dev/seed endpoints (development only)
  services/            # Business logic
    incident_service.py
    shield_service.py
    location_service.py
    navigation_service.py
    hotspot_service.py
    elevenlabs_service.py
    push_service.py    # Expo push notifications
    sms_service.py
    auth_service.py
    admin_service.py
  utils/               # Pure utility functions (geo math, geohash)
frontend/
  src/
    app/               # Next.js app router (page.tsx, layout.tsx)
    components/        # UI components (SOSButton, MiniMap, ExpandedMap, etc.)
    hooks/             # React hooks (useIncident, useGeolocation, useElevenLabs, …)
    lib/               # API client, Zustand store, shared types
tests/
  conftest.py          # Fixtures: test DB, fakeredis, async HTTP client
  test_auth.py
  test_incidents.py
  test_location.py
  test_tracking.py
  test_push.py
  test_hotspots.py
  test_sms.py
alembic/               # DB migration scripts
docker-compose.yml
Dockerfile
```

---

## Local Setup

### Prerequisites
- Docker Desktop (recommended) **or** Python 3.11+ with local Postgres 15 and Redis 7

### 1. Clone and configure environment

```bash
git clone <repo-url>
cd Shieldly
cp .env.example .env
```

Open `.env` and fill in the required values (see [Environment Variables](#environment-variables) below).

### 2. Start the stack

```bash
docker compose up --build
```

This starts three containers:
- **postgres** — port `5433` (host) → `5432` (container)
- **redis** — port `6379`
- **app** — port `8000` with hot-reload

### 3. Run migrations

```bash
docker compose exec app alembic upgrade head
```

### 4. Verify the server is up

```
GET http://localhost:8000/health
→ { "status": "ok", "env": "development" }
```

### 5. Open Swagger UI

```
http://localhost:8000/docs
```

Swagger UI is only exposed when `APP_ENV=development`.

---

## Testing the Flows

### Full end-to-end via dev seed endpoints

These endpoints are only active when `APP_ENV=development`. Use Swagger UI, curl, or Postman.

**Step 1 — Seed the database**

```
POST /api/v1/dev/seed
```

Wipes all data and inserts 1 person user + 5 verified Shield users positioned around a test location.

**Step 2 — Trigger a test SOS**

```
POST /api/v1/dev/trigger-test-sos
```

Fires an SOS from the seed person. Returns the `incident_id`, the tracking token, and the IDs of the notified Shields.

**Step 3 — Simulate a Shield responding**

```
POST /api/v1/dev/mock-shield-respond/{incident_id}/{shield_id}
```

Simulates a Shield accepting the incident and moves their location 30% toward the convergence point.

**Step 4 — Test SMS delivery**

```
POST /api/v1/dev/test/sms
Body: { "to": "+1234567890" }
```

Fires the SMS pipeline against the real Brevo API.

---

### Auth flow (manual)

```
POST /api/v1/auth/verify-token
Body: { "firebase_token": "<token>", "role": "person" }
→ { "access_token": "...", "user_id": "...", "role": "person" }
```

Use the returned `access_token` as `Authorization: Bearer <token>` on all subsequent requests.

---

### Admin flow

All admin endpoints require the header:

```
X-Admin-Key: <your ADMIN_API_KEY value>
```

```
GET  /api/v1/admin/shields/pending          # list unverified shields
PATCH /api/v1/admin/shields/{id}/verify     # approve or reject a shield
GET  /api/v1/admin/incidents                # all incidents (filterable by status)
GET  /api/v1/admin/stats                    # platform stats
```

---

### Hotspot / AI context

```
GET /api/v1/hotspots/context?lat=49.1427&lng=9.2109
```

Returns a Gemini-generated safety summary for the area.

---

### ElevenLabs voice flow

During an active incident, the incident owner can use ElevenLabs Conversational AI for voice guidance:

1. **Get a signed URL** (incident owner only):
   ```
   GET /api/v1/incidents/{incident_id}/elevenlabs-token
   Authorization: Bearer <jwt>
   → { "signed_url": "wss://...", "incident_id": "..." }
   ```

2. **Start the session** — frontend passes `signed_url` to the ElevenLabs SDK (`Conversation.startSession({ signedUrl })`).

3. **Fetch dynamicVariables context**:
   ```
   GET /api/v1/incidents/{incident_id}/context
   → { "shield_count": "2", "nearest_distance": "340 metres", "nearest_eta": "4 minutes", ... }
   ```

4. **Subscribe to Redis Pub/Sub** — when a Shield moves significantly closer, the broadcast includes `context_update`; call `conversation.setVariables(msg.context_update)` to keep the voice agent current.

---

### Public tracking flow

Every incident includes a `tracking_token` in the trigger response. Share the link with a trusted contact:

```
GET /api/v1/track/{tracking_token}
→ { incident_id, status, person_lat, person_lng, responding_shields: [...], convergence_lat, convergence_lng, ... }
```

Connect via WebSocket for live updates (no auth required):

```
WS /api/v1/track/{tracking_token}/live
```

The WebSocket relays `shield_location`, `person_location`, `convergence_update`, and `incident_resolved` events. Ping with `"ping"` to keep the connection alive; the server responds with `"pong"`.

---

### Running the test suite

**Recommended — inside Docker:**

```bash
docker compose up -d
docker compose exec app alembic upgrade head
docker compose exec app pytest tests/ -v
```

**Locally (outside Docker):**

1. Ensure Postgres 15 and Redis 7 are running, or use Docker for DB/Redis only:
   ```bash
   docker compose up -d db redis
   ```

2. Set `TEST_DATABASE_URL` in `.env`:
   ```env
   TEST_DATABASE_URL=postgresql+asyncpg://shieldher:shieldher@localhost:5433/shieldher_test
   ```

3. Install deps and run:
   ```bash
   pip install -r requirements.txt
   pytest tests/ -v
   ```

**Test environment notes:**

- `pytest.ini` sets `asyncio_default_fixture_loop_scope = session` and the engine uses `NullPool` to avoid "attached to a different loop" errors with asyncpg.
- `shieldher_test` is created automatically if it doesn't exist.
- The test suite uses `fakeredis` in-process — no external Redis required.

---

## Environment Variables

Copy `.env.example` to `.env` and fill in the values below.

### Required (no defaults — app will not start without these)

| Variable | Description |
|---|---|
| `JWT_SECRET` | Secret used to sign JWTs. Use any long random string locally. |
| `FIREBASE_PROJECT_ID` | Your Firebase project ID (e.g. `my-app-12345`) |
| `BREVO_API_KEY` | Brevo API key for Transactional SMS |
| `GOOGLE_MAPS_API_KEY` | Google Maps Directions API key |
| `GEMINI_API_KEY` | Google Gemini API key |
| `GEMINI_MODEL` | Gemini model name (e.g. `gemini-1.5-flash`) |
| `ELEVENLABS_API_KEY` | ElevenLabs API key |
| `ELEVENLABS_AGENT_ID` | ElevenLabs Conversational AI agent ID |
| `ADMIN_API_KEY` | Static secret for the `X-Admin-Key` header |

### Optional (have sensible defaults)

| Variable | Default | Description |
|---|---|---|
| `APP_ENV` | `development` | Set to `production` to disable `/docs` and `/dev/*` endpoints |
| `APP_PORT` | `8000` | Port the app listens on |
| `DATABASE_URL` | `postgresql+asyncpg://shieldher:shieldher@localhost:5432/shieldher` | Postgres connection string |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection string |
| `JWT_EXPIRE_MINUTES` | `10080` (7 days) | JWT lifetime |
| `FIREBASE_API_KEY` | `` | Firebase web API key (only needed for client-side flows) |
| `BREVO_SENDER_NAME` | `ShieldHer` | SMS sender name shown on the recipient's device |

---

## API Reference

Full interactive docs are available at `http://localhost:8000/docs` when running in development mode.

| Domain | Prefix | Key endpoints |
|---|---|---|
| Auth | `/api/v1/auth` | `POST /verify-token` |
| Incidents | `/api/v1/incidents` | `POST /trigger`, `POST /{id}/respond`, `POST /{id}/all-clear`, `GET /{id}`, `GET /{id}/elevenlabs-token`, `GET /{id}/context` |
| Location | `/api/v1/location` | `PATCH /shield`, `PATCH /incident/{id}`, `GET /incident/{id}/all`, `GET /shields/nearby` |
| Shields | `/api/v1/shields` | `POST /apply`, `PATCH /me/status`, `PATCH /me/active-hours`, `PATCH /me/device`, `GET /me` |
| Hotspots | `/api/v1/hotspots` | `GET /context?lat=&lng=` |
| Tracking | `/api/v1/track` | `GET /{token}`, `WS /{token}/live` |
| Admin | `/api/v1/admin` | `GET /shields/pending`, `PATCH /shields/{id}/verify`, `GET /incidents`, `GET /stats` |
| Dev (dev only) | `/api/v1/dev` | `POST /seed`, `POST /trigger-test-sos`, `POST /mock-shield-respond/{incident_id}/{shield_id}`, `POST /test/sms` |
| System | `/` | `GET /health` |

---

## Makefile Shortcuts

```bash
make up       # docker compose up -d
make down     # docker compose down
make migrate  # alembic upgrade head (inside container)
make seed     # POST /dev/seed
make test     # pytest tests/ -v (inside container)
make logs     # follow app container logs
make shell    # bash inside app container
make reset    # full wipe + up + migrate + seed
```
