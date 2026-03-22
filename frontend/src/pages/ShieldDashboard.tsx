import { useState, useEffect, useRef } from 'react'
import { ShieldCheck, ToggleLeft, ToggleRight, X, Navigation } from 'lucide-react'
import {
  respondToIncident,
  getIncident,
  updateShieldLocation,
  IncidentDetail,
} from '../api/endpoints'
import { useStore } from '../store'
import BottomTabBar from '../components/BottomTabBar'
import LoginModal from '../components/LoginModal'

type ShieldState = 'offline' | 'active' | 'incoming' | 'responding' | 'arrived'

const HEILBRONN: [number, number] = [49.1427, 9.2109]

function formatEta(s: number | null) {
  if (s === null) return 'En route'
  if (s < 60) return '<1 min'
  return `${Math.round(s / 60)} min`
}

export default function ShieldDashboard() {
  const [shieldState, setShieldState] = useState<ShieldState>('offline')
  const [incomingIncident, setIncomingIncident] = useState<IncidentDetail | null>(null)
  const [activeIncident, setActiveIncident] = useState<IncidentDetail | null>(null)
  const [showLogin, setShowLogin] = useState(false)
  const [errorMsg, setErrorMsg] = useState<string | null>(null)
  const [locationSent, setLocationSent] = useState(false)

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const { token, incidentId, role } = useStore()

  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current)
    }
  }, [])

  // If there's an active incident in store (from SOS landing), load it
  useEffect(() => {
    if (incidentId && role === 'shield') {
      getIncident(incidentId)
        .then((d) => {
          setIncomingIncident(d)
          setShieldState('incoming')
        })
        .catch(() => {})
    }
  }, [incidentId, role])

  async function goActive() {
    if (!token) {
      setShowLogin(true)
      return
    }
    // Update shield location
    try {
      await updateShieldLocation(HEILBRONN[0], HEILBRONN[1])
      setLocationSent(true)
    } catch {}
    setShieldState('active')
  }

  async function handleAccept() {
    if (!incomingIncident) return
    setErrorMsg(null)
    try {
      await respondToIncident(incomingIncident.incident_id, 'responding')
      setActiveIncident(incomingIncident)
      setShieldState('responding')
      startPolling(incomingIncident.incident_id)
    } catch (e: unknown) {
      setErrorMsg(e instanceof Error ? e.message : 'Failed to respond')
    }
  }

  async function handleDecline() {
    if (!incomingIncident) return
    try {
      await respondToIncident(incomingIncident.incident_id, 'declined')
    } catch {}
    setIncomingIncident(null)
    setShieldState('active')
  }

  function handleArrived() {
    if (pollRef.current) clearInterval(pollRef.current)
    setShieldState('arrived')
  }

  function startPolling(id: string) {
    pollRef.current = setInterval(async () => {
      try {
        const detail = await getIncident(id)
        setActiveIncident(detail)
        if (detail.status === 'resolved') {
          clearInterval(pollRef.current!)
          setShieldState('arrived')
        }
      } catch {}
    }, 5000)
  }

  const myInfo = activeIncident?.shields?.find(
    (s) => s.status === 'responding' || s.status === 'arrived',
  )

  return (
    <div className="min-h-screen bg-greige flex flex-col pb-20">
      {/* Header */}
      <header className="px-6 pt-10 pb-4">
        <span className="font-display text-2xl text-ink">
          Shieldly<span className="text-accent">•</span>
        </span>
        <div className="font-sans text-xs text-ink-muted mt-1">Shield volunteer</div>
      </header>

      <main className="flex-1 flex flex-col items-center px-6 gap-6 pt-4">
        {/* Error */}
        {errorMsg && (
          <div className="w-full max-w-sm bg-surface border border-rose/30 rounded-2xl px-5 py-4 font-sans text-sm text-ink-muted animate-fade-up flex items-start justify-between gap-3">
            <span>{errorMsg}</span>
            <button onClick={() => setErrorMsg(null)} className="flex-shrink-0">✕</button>
          </div>
        )}

        {/* ── OFFLINE ── */}
        {shieldState === 'offline' && (
          <div className="w-full max-w-sm flex flex-col gap-5 animate-fade-up">
            <div className="bg-surface rounded-2xl p-6 border border-ink/6 shadow-sm">
              <div className="flex items-center justify-between mb-4">
                <div>
                  <div className="font-display text-xl text-ink">Patrol status</div>
                  <div className="font-sans text-xs text-ink-muted mt-0.5">You're currently offline</div>
                </div>
                <div className="w-10 h-10 rounded-full bg-greige flex items-center justify-center">
                  <ShieldCheck size={20} className="text-ink-muted" />
                </div>
              </div>
              <button
                onClick={goActive}
                className="w-full flex items-center justify-center gap-2 py-4 rounded-2xl bg-greige border border-ink/10 text-ink-muted font-sans text-sm hover:border-sage/50 hover:text-sage transition-all"
              >
                <ToggleLeft size={20} />
                Go on patrol
              </button>
            </div>

            <div className="bg-surface rounded-2xl p-5 border border-ink/6 shadow-sm">
              <div className="font-display text-base text-ink mb-3">How it works</div>
              <div className="flex flex-col gap-3 font-sans text-sm text-ink-muted">
                <div className="flex items-start gap-3">
                  <div className="w-6 h-6 rounded-full bg-sage-light flex items-center justify-center text-sage text-xs font-semibold flex-shrink-0">1</div>
                  <span>Go active to let people know you're nearby</span>
                </div>
                <div className="flex items-start gap-3">
                  <div className="w-6 h-6 rounded-full bg-sage-light flex items-center justify-center text-sage text-xs font-semibold flex-shrink-0">2</div>
                  <span>Receive alerts when someone nearby needs help</span>
                </div>
                <div className="flex items-start gap-3">
                  <div className="w-6 h-6 rounded-full bg-sage-light flex items-center justify-center text-sage text-xs font-semibold flex-shrink-0">3</div>
                  <span>Choose to respond or pass — always your choice</span>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* ── ACTIVE / PATROLLING ── */}
        {shieldState === 'active' && (
          <div className="w-full max-w-sm flex flex-col gap-5 animate-fade-up">
            <div className="bg-sage-light border border-sage/20 rounded-2xl p-6 text-center shadow-sm">
              <div className="inline-flex items-center justify-center w-14 h-14 rounded-full bg-sage/20 mb-4">
                <ShieldCheck size={28} className="text-sage" />
              </div>
              <div className="font-display text-2xl text-ink mb-1">You're on patrol</div>
              <div className="font-sans text-sm text-ink-muted">
                You'll be notified when someone nearby needs help
              </div>
              {locationSent && (
                <div className="mt-3 font-sans text-xs text-sage">
                  Location shared with network
                </div>
              )}
            </div>

            <button
              onClick={() => setShieldState('offline')}
              className="w-full flex items-center justify-center gap-2 py-4 rounded-2xl bg-surface border border-ink/8 text-ink-muted font-sans text-sm hover:border-ink/20 transition-all"
            >
              <ToggleRight size={20} className="text-sage" />
              End patrol
            </button>
          </div>
        )}

        {/* ── INCOMING SOS ── */}
        {shieldState === 'incoming' && incomingIncident && (
          <div className="w-full max-w-sm animate-slide-up">
            <div className="bg-surface rounded-2xl p-6 border-2 border-accent/30 shadow-lg">
              {/* Header */}
              <div className="flex items-start justify-between mb-5">
                <div>
                  <div className="font-display text-xl text-ink">Someone needs help</div>
                  <div className="font-sans text-xs text-ink-muted mt-0.5">
                    SOS triggered nearby
                  </div>
                </div>
                <button
                  onClick={handleDecline}
                  className="w-7 h-7 rounded-full bg-greige flex items-center justify-center"
                >
                  <X size={14} className="text-ink-muted" />
                </button>
              </div>

              {/* Details */}
              <div className="bg-greige rounded-xl p-4 mb-5">
                <div className="flex items-center justify-between font-sans text-sm">
                  <span className="text-ink-muted">Location</span>
                  <span className="text-ink font-medium">
                    {incomingIncident.trigger_lat.toFixed(3)}°N
                  </span>
                </div>
                <div className="flex items-center justify-between font-sans text-sm mt-2">
                  <span className="text-ink-muted">Shields notified</span>
                  <span className="text-ink font-medium">
                    {incomingIncident.shields_notified}
                  </span>
                </div>
              </div>

              {/* Actions */}
              <div className="flex flex-col gap-3">
                <button
                  onClick={handleAccept}
                  className="w-full py-4 rounded-2xl bg-sage text-white font-sans font-semibold text-base transition-all hover:bg-sage/90 active:scale-95 shadow-sm"
                >
                  I'll help
                </button>
                <button
                  onClick={handleDecline}
                  className="w-full py-3 rounded-2xl bg-greige text-ink-muted font-sans text-sm transition-all hover:bg-greige/80"
                >
                  Can't right now
                </button>
              </div>
            </div>
          </div>
        )}

        {/* ── RESPONDING ── */}
        {shieldState === 'responding' && activeIncident && (
          <div className="w-full max-w-sm flex flex-col gap-5 animate-fade-up">
            <div className="bg-surface rounded-2xl p-6 border border-sage/20 shadow-sm">
              <div className="flex items-center gap-3 mb-4">
                <div className="w-10 h-10 rounded-full bg-sage/20 flex items-center justify-center">
                  <Navigation size={20} className="text-sage" />
                </div>
                <div>
                  <div className="font-display text-xl text-ink">En route</div>
                  <div className="font-sans text-xs text-ink-muted">
                    Head to the person's location
                  </div>
                </div>
              </div>

              <div className="bg-greige rounded-xl p-4 mb-5">
                <div className="font-sans text-sm text-ink-muted mb-1">Destination</div>
                <div className="font-sans text-sm font-medium text-ink">
                  {activeIncident.trigger_lat.toFixed(4)}°N, {activeIncident.trigger_lng.toFixed(4)}°E
                </div>
                {myInfo?.eta_seconds !== undefined && (
                  <div className="font-sans text-xs text-sage mt-2">
                    ETA: {formatEta(myInfo.eta_seconds ?? null)}
                  </div>
                )}
              </div>

              <button
                onClick={handleArrived}
                className="w-full py-4 rounded-2xl bg-accent text-white font-sans font-semibold text-base transition-all hover:bg-accent-dark active:scale-95 shadow-sm"
              >
                I've arrived
              </button>
            </div>
          </div>
        )}

        {/* ── ARRIVED ── */}
        {shieldState === 'arrived' && (
          <div className="w-full max-w-sm flex flex-col gap-5 items-center animate-fade-up">
            <div className="w-full bg-sage-light border border-sage/20 rounded-3xl p-10 text-center shadow-sm">
              <div className="font-display text-4xl text-sage mb-4">✦</div>
              <div className="font-display text-2xl text-ink mb-2">Thank you</div>
              <div className="font-sans text-sm text-ink-muted">
                You made someone feel safer today
              </div>
            </div>
            <button
              onClick={() => {
                setShieldState('active')
                setActiveIncident(null)
                setIncomingIncident(null)
              }}
              className="font-sans text-sm text-ink-muted underline underline-offset-4 hover:text-ink transition-colors"
            >
              Continue patrol
            </button>
          </div>
        )}
      </main>

      <BottomTabBar />
      {showLogin && (
        <LoginModal onClose={() => setShowLogin(false)} defaultRole="shield" />
      )}
    </div>
  )
}
