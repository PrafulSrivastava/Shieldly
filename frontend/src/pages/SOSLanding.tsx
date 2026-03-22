import { useState, useEffect, useRef } from 'react'
import { Users } from 'lucide-react'
import { MapContainer, TileLayer, Marker, Popup, useMap } from 'react-leaflet'
import L from 'leaflet'
import {
  triggerSOS,
  getIncident,
  resolveIncident,
  getHotspotContext,
  verifyToken,
  ShieldStatusInfo,
} from '../api/endpoints'
import { useStore } from '../store'
import BottomTabBar from '../components/BottomTabBar'
import ShieldCard from '../components/ShieldCard'
import Skeleton from '../components/Skeleton'

// ── Map helpers for the active SOS state ──────────────────────────────────────

const personMarkerIcon = L.divIcon({
  className: '',
  html: `<div style="
    width:18px;height:18px;
    background:#C4543A;
    border:3px solid white;
    border-radius:50%;
    box-shadow:0 0 0 3px rgba(196,84,58,0.3), 0 2px 8px rgba(0,0,0,0.25);
  "></div>`,
  iconSize: [18, 18],
  iconAnchor: [9, 9],
})

const SHIELD_COLORS: Record<string, [string, string]> = {
  notified:   ['#F5A623', '#D4880A'],
  responding: ['#7BB3A6', '#5A9A8D'],
  arrived:    ['#3D8B6E', '#2A6B52'],
  declined:   ['#B0B0B0', '#888888'],
}

function makeIncidentShieldIcon(status: string) {
  const [bg, border] = SHIELD_COLORS[status] ?? SHIELD_COLORS.notified
  return L.divIcon({
    className: '',
    html: `<div style="
      width:22px;height:22px;
      background:${bg};
      border:2px solid ${border};
      border-radius:50% 50% 50% 0;
      transform:rotate(-45deg);
      box-shadow:0 2px 6px rgba(0,0,0,0.2);
    "></div>`,
    iconSize: [22, 22],
    iconAnchor: [11, 20],
  })
}

function SOSMapFitter({
  person,
  shields,
}: {
  person: { lat: number; lng: number }
  shields: ShieldStatusInfo[]
}) {
  const map = useMap()
  useEffect(() => {
    const pts: [number, number][] = [[person.lat, person.lng]]
    shields.forEach((s) => {
      if (s.lat != null && s.lng != null) pts.push([s.lat, s.lng])
    })
    if (pts.length < 2) {
      map.setView([person.lat, person.lng], 14)
    } else {
      map.fitBounds(L.latLngBounds(pts), { padding: [48, 48] })
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shields.length])
  return null
}

type SOSState = 'idle' | 'countdown' | 'active' | 'resolved'

const COUNTDOWN_SEC = 5
const RING_R = 115
const RING_CIRCUMFERENCE = 2 * Math.PI * RING_R

const HEILBRONN = { lat: 49.1427, lng: 9.2109 }

function CountdownText({ t }: { t: number }) {
  if (t > 3.5) return <>Connecting…</>
  if (t > 1.5) return <>Finding shields…</>
  return <>Almost there…</>
}

export default function SOSLanding() {
  const [state, setState] = useState<SOSState>('idle')
  const [countdown, setCountdown] = useState<number>(COUNTDOWN_SEC)
  const [incidentId, setIncidentId] = useState<string | null>(null)
  const [shields, setShields] = useState<ShieldStatusInfo[]>([])
  const [nearbyCount, setNearbyCount] = useState<number | null>(null)
  const [riskLevel, setRiskLevel] = useState<string | null>(null)
  const [errorMsg, setErrorMsg] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const { token, setAuth, setIncidentId: storeSetIncidentId } = useStore()

  // Silently auto-authenticate on mount so the button always works
  useEffect(() => {
    if (token) return
    verifyToken('+491700000001', 'Demo User', 'person')
      .then((r) => setAuth(r.access_token, r.user_id, r.role, r.phone))
      .catch(() => {})
  }, [])

  // Load ambient safety context once we have a token
  useEffect(() => {
    getHotspotContext(HEILBRONN.lat, HEILBRONN.lng)
      .then((d) => {
        setNearbyCount(d.shield_count_nearby ?? 0)
        setRiskLevel(d.risk_level ?? 'low')
      })
      .catch(() => {})
  }, [token])

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current)
      if (pollRef.current) clearInterval(pollRef.current)
    }
  }, [])

  async function handleSOSTap() {
    setLoading(true)
    setErrorMsg(null)
    try {
      const resp = await triggerSOS(HEILBRONN.lat, HEILBRONN.lng)
      setIncidentId(resp.incident_id)
      storeSetIncidentId(resp.incident_id)

      // Enter countdown
      setState('countdown')
      let remaining = COUNTDOWN_SEC
      setCountdown(remaining)

      intervalRef.current = setInterval(() => {
        remaining -= 0.1
        setCountdown(Math.max(0, remaining))
        if (remaining <= 0) {
          clearInterval(intervalRef.current!)
          setState('active')
          startPolling(resp.incident_id)
        }
      }, 100)
    } catch (e: unknown) {
      setErrorMsg(e instanceof Error ? e.message : 'Failed to send SOS')
      setState('idle')
    } finally {
      setLoading(false)
    }
  }

  async function handleCancel() {
    if (intervalRef.current) clearInterval(intervalRef.current)
    const id = incidentId
    setState('idle')
    setCountdown(COUNTDOWN_SEC)
    setIncidentId(null)
    storeSetIncidentId(null)
    if (id) {
      resolveIncident(id).catch(() => {})
    }
  }

  async function handleAllClear() {
    if (pollRef.current) clearInterval(pollRef.current)
    if (incidentId) {
      try {
        await resolveIncident(incidentId)
      } catch {}
    }
    setState('resolved')
    storeSetIncidentId(null)
  }

  function startPolling(id: string) {
    pollRef.current = setInterval(async () => {
      try {
        const detail = await getIncident(id)
        // Filter to valid shields with real data
        const safeShields = (detail.shields ?? []).filter(
          (s) => s.shield_id && s.name,
        )
        setShields(safeShields)
        if (detail.status === 'resolved') {
          clearInterval(pollRef.current!)
          setState('resolved')
        }
      } catch {}
    }, 3000)
  }

  const progress = countdown / COUNTDOWN_SEC
  const ringOffset = RING_CIRCUMFERENCE * (1 - progress)

  const riskColors: Record<string, string> = {
    low: 'text-sage',
    medium: 'text-ink-muted',
    high: 'text-accent',
  }
  const riskLabels: Record<string, string> = {
    low: 'Area calm',
    medium: 'Moderate activity',
    high: 'Stay aware',
  }

  return (
    <div className="min-h-screen bg-greige flex flex-col pb-20 relative">
      {/* Header */}
      <header className="px-6 pt-10 pb-2">
        <span className="font-display text-2xl text-ink">
          Shieldly<span className="text-accent">•</span>
        </span>
      </header>

      {/* Main */}
      <main className={`flex-1 flex flex-col gap-4 ${state === 'active' ? 'pt-2' : 'items-center justify-center px-6 gap-8'}`}>

        {/* Error */}
        {errorMsg && (
          <div className="w-full max-w-sm bg-surface border border-rose/30 rounded-2xl px-5 py-4 font-sans text-sm text-ink-muted animate-fade-up flex items-start justify-between gap-3">
            <span>{errorMsg}</span>
            <button onClick={() => setErrorMsg(null)} className="text-ink-muted/60 hover:text-ink flex-shrink-0">✕</button>
          </div>
        )}

        {/* ── IDLE ── */}
        {state === 'idle' && (
          <div className="flex flex-col items-center gap-8 animate-fade-up">
            <div className="relative">
              {/* Ambient pulse rings */}
              <div className="absolute inset-0 rounded-full bg-accent/10 animate-pulse-ring" />
              <div className="absolute inset-0 rounded-full bg-accent/6 animate-pulse-ring animation-delay-300" />
              <button
                onClick={handleSOSTap}
                disabled={loading}
                className="relative w-56 h-56 rounded-full bg-accent text-white shadow-[0_8px_48px_rgba(196,84,58,0.4)] animate-breathe flex flex-col items-center justify-center gap-2 transition-all active:scale-95 disabled:opacity-60 select-none"
              >
                <span className="font-display text-[2.6rem] leading-tight">I feel</span>
                <span className="font-display text-[2.6rem] leading-tight">unsafe</span>
              </button>
            </div>

            {/* Safety context */}
            <div className="flex items-center gap-4 font-sans text-sm text-ink-muted">
              <span className="flex items-center gap-1.5">
                <Users size={14} className="text-sage" />
                {nearbyCount !== null
                  ? `${nearbyCount} shield${nearbyCount !== 1 ? 's' : ''} nearby`
                  : 'Finding shields…'}
              </span>
              {riskLevel && (
                <>
                  <span className="w-1 h-1 rounded-full bg-ink-muted/30" />
                  <span className={riskColors[riskLevel] ?? 'text-ink-muted'}>
                    {riskLabels[riskLevel] ?? 'Unknown'}
                  </span>
                </>
              )}
            </div>
          </div>
        )}

        {/* ── COUNTDOWN ── */}
        {state === 'countdown' && (
          <div className="flex flex-col items-center gap-8 animate-fade-up">
            <div className="relative">
              {/* SVG countdown ring */}
              <svg
                width="268"
                height="268"
                className="absolute"
                style={{ top: '-14px', left: '-14px', transform: 'rotate(-90deg)' }}
              >
                {/* Track */}
                <circle
                  cx="134" cy="134" r={RING_R}
                  fill="none"
                  stroke="#C4543A"
                  strokeWidth="3"
                  opacity="0.12"
                />
                {/* Draining arc */}
                <circle
                  cx="134" cy="134" r={RING_R}
                  fill="none"
                  stroke="#C4543A"
                  strokeWidth="3"
                  strokeLinecap="round"
                  strokeDasharray={RING_CIRCUMFERENCE}
                  strokeDashoffset={ringOffset}
                  opacity="0.7"
                  style={{ transition: 'stroke-dashoffset 0.1s linear' }}
                />
              </svg>

              <div className="w-56 h-56 rounded-full bg-accent flex flex-col items-center justify-center gap-2 shadow-[0_8px_48px_rgba(196,84,58,0.4)]">
                <span className="font-display text-xl text-white text-center px-4 leading-snug">
                  <CountdownText t={countdown} />
                </span>
                <span className="font-sans text-4xl font-light text-white/90">
                  {Math.ceil(countdown)}
                </span>
              </div>
            </div>

            <button
              onClick={handleCancel}
              className="font-sans text-base text-ink-muted underline underline-offset-4 py-4 px-10 min-h-[52px] transition-colors hover:text-ink"
            >
              Cancel
            </button>
          </div>
        )}

        {/* ── ACTIVE ── */}
        {state === 'active' && (
          <div className="w-full flex flex-col gap-3 animate-fade-up">
            {/* Status banner */}
            <div className="mx-4 bg-[#F5EDD5] border border-[#E3CE96] rounded-2xl px-5 py-4 text-center">
              <div className="font-display text-2xl text-ink mb-0.5">
                Help is on the way
              </div>
              <div className="font-sans text-sm text-ink-muted">
                {shields.filter((s) => s.status !== 'declined').length > 0
                  ? `${shields.filter((s) => s.status !== 'declined').length} shield${shields.filter((s) => s.status !== 'declined').length !== 1 ? 's' : ''} responding`
                  : 'Locating shields nearby…'}
              </div>
            </div>

            {/* Incident map */}
            <div className="mx-4 rounded-2xl overflow-hidden shadow-md" style={{ height: 300 }}>
              <MapContainer
                center={[HEILBRONN.lat, HEILBRONN.lng]}
                zoom={13}
                style={{ height: '100%', width: '100%' }}
                zoomControl={false}
                attributionControl={false}
              >
                <TileLayer url="https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png" />
                {/* Person */}
                <Marker position={[HEILBRONN.lat, HEILBRONN.lng]} icon={personMarkerIcon}>
                  <Popup>
                    <span className="font-sans text-xs">You are here</span>
                  </Popup>
                </Marker>
                {/* Shields */}
                {shields
                  .filter((s) => s.lat != null && s.lng != null)
                  .map((s) => (
                    <Marker
                      key={s.shield_id}
                      position={[s.lat!, s.lng!]}
                      icon={makeIncidentShieldIcon(s.status)}
                    >
                      <Popup>
                        <div className="font-sans text-xs">
                          <strong>{s.name || 'Shield'}</strong>
                          <br />
                          <span className="capitalize">{s.status}</span>
                          {s.eta_seconds != null && (
                            <> · {Math.round(s.eta_seconds / 60)} min</>
                          )}
                        </div>
                      </Popup>
                    </Marker>
                  ))}
                <SOSMapFitter person={HEILBRONN} shields={shields} />
              </MapContainer>
            </div>

            {/* Map legend */}
            <div className="mx-4 flex items-center gap-4 font-sans text-[11px] text-ink-muted">
              <span className="flex items-center gap-1.5">
                <span className="w-3 h-3 rounded-full bg-accent inline-block" />
                You
              </span>
              <span className="flex items-center gap-1.5">
                <span className="w-3 h-3 rounded-full bg-[#F5A623] inline-block" />
                Notified
              </span>
              <span className="flex items-center gap-1.5">
                <span className="w-3 h-3 rounded-full bg-sage inline-block" />
                En route
              </span>
            </div>

            {/* Shield cards */}
            <div className="mx-4 flex flex-col gap-2">
              {shields.length === 0 ? (
                <>
                  <Skeleton className="h-[64px]" />
                  <Skeleton className="h-[64px] animation-delay-100" />
                </>
              ) : (
                shields.map((s, i) => (
                  <ShieldCard key={s.shield_id} shield={s} index={i} />
                ))
              )}
            </div>

            <div className="mx-4 mb-2">
              <button
                onClick={handleAllClear}
                className="w-full py-4 rounded-2xl bg-sage text-white font-sans font-semibold text-base transition-all hover:bg-sage/90 active:scale-95 shadow-sm"
              >
                I'm safe now
              </button>
            </div>
          </div>
        )}

        {/* ── RESOLVED ── */}
        {state === 'resolved' && (
          <div className="w-full max-w-sm flex flex-col gap-6 items-center animate-fade-up">
            <div className="w-full bg-sage-light border border-sage/20 rounded-3xl p-10 text-center">
              <div className="font-display text-5xl text-sage mb-5">✦</div>
              <div className="font-display text-3xl text-ink mb-2">
                You're safe
              </div>
              <div className="font-sans text-sm text-ink-muted">
                The incident has been resolved
              </div>
            </div>
            <button
              onClick={() => {
                setState('idle')
                setIncidentId(null)
                setShields([])
              }}
              className="font-sans text-sm text-ink-muted underline underline-offset-4 hover:text-ink transition-colors"
            >
              Return to home
            </button>
          </div>
        )}
      </main>

      <BottomTabBar />
    </div>
  )
}
