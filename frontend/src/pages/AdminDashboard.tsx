import { useState } from 'react'
import { Terminal, Sprout, KeyRound, RefreshCw, ShieldCheck } from 'lucide-react'
import { verifyToken, seedQuick, seedLarge, seedHotspots, simulateShieldAccept } from '../api/endpoints'
import { useStore } from '../store'
import BottomTabBar from '../components/BottomTabBar'

type LogEntry = { ts: string; label: string; ok: boolean; body: string }

function ts() {
  return new Date().toLocaleTimeString('en-GB', { hour12: false })
}

export default function AdminDashboard() {
  const { token, adminKey, setAdminKey, setAuth, clearAuth, phone, role, incidentId } = useStore()
  const [log, setLog] = useState<LogEntry[]>([])
  const [loading, setLoading] = useState<string | null>(null)

  // Auth form
  const [authPhone, setAuthPhone] = useState('+491700000001')
  const [authName, setAuthName] = useState('Demo User')
  const [authRole, setAuthRole] = useState<'person' | 'shield'>('person')

  function addLog(label: string, ok: boolean, body: unknown) {
    setLog((prev) => [
      { ts: ts(), label, ok, body: JSON.stringify(body, null, 2) },
      ...prev.slice(0, 49),
    ])
  }

  async function run(label: string, fn: () => Promise<unknown>) {
    setLoading(label)
    try {
      const res = await fn()
      addLog(label, true, res)
    } catch (e: unknown) {
      addLog(label, false, { error: e instanceof Error ? e.message : String(e) })
    } finally {
      setLoading(null)
    }
  }

  async function handleLogin() {
    await run('Auth: verify-token', async () => {
      const resp = await verifyToken(authPhone, authName, authRole)
      setAuth(resp.access_token, resp.user_id, resp.role, resp.phone)
      return resp
    })
  }

  const seeds = [
    { label: 'Quick Seed', fn: seedQuick, desc: 'Small test dataset' },
    { label: 'Large Seed (1 000 users)', fn: seedLarge, desc: '600 persons + 400 shields in Heilbronn & Stuttgart' },
    { label: 'Seed Hotspots', fn: seedHotspots, desc: 'Populate hotspot zone data' },
  ]

  return (
    <div className="min-h-screen bg-greige flex flex-col pb-24">
      <header className="px-6 pt-10 pb-4">
        <span className="font-display text-2xl text-ink">
          Shieldly<span className="text-accent">•</span>
        </span>
        <div className="font-sans text-xs text-ink-muted mt-1">Admin tools</div>
      </header>

      <main className="flex-1 flex flex-col gap-5 px-4 pt-2">

        {/* Auth */}
        <section className="bg-surface rounded-2xl p-5 border border-ink/6 shadow-sm">
          <div className="flex items-center gap-2 mb-4">
            <KeyRound size={16} className="text-accent" />
            <div className="font-display text-base text-ink">Authentication</div>
          </div>

          {token ? (
            <div className="flex flex-col gap-3">
              <div className="bg-sage-light rounded-xl p-4">
                <div className="font-sans text-xs text-ink-muted mb-1">Signed in as</div>
                <div className="font-sans text-sm font-medium text-ink">{phone}</div>
                <div className="font-sans text-xs text-sage capitalize mt-0.5">{role}</div>
              </div>
              <button
                onClick={clearAuth}
                className="w-full py-3 rounded-xl bg-greige border border-ink/10 text-ink-muted font-sans text-sm hover:border-ink/20 transition-all"
              >
                Sign out
              </button>
            </div>
          ) : (
            <div className="flex flex-col gap-3">
              <input
                value={authPhone}
                onChange={(e) => setAuthPhone(e.target.value)}
                placeholder="+491700000001"
                className="w-full bg-greige border border-ink/10 rounded-xl px-4 py-3 font-sans text-sm text-ink focus:outline-none focus:border-accent transition-colors"
              />
              <input
                value={authName}
                onChange={(e) => setAuthName(e.target.value)}
                placeholder="Name"
                className="w-full bg-greige border border-ink/10 rounded-xl px-4 py-3 font-sans text-sm text-ink focus:outline-none focus:border-accent transition-colors"
              />
              <div className="flex gap-2">
                {(['person', 'shield'] as const).map((r) => (
                  <button
                    key={r}
                    onClick={() => setAuthRole(r)}
                    className={`flex-1 py-2.5 rounded-xl font-sans text-sm border transition-all ${
                      authRole === r
                        ? 'bg-accent text-white border-accent'
                        : 'bg-greige text-ink-muted border-ink/10'
                    }`}
                  >
                    {r.charAt(0).toUpperCase() + r.slice(1)}
                  </button>
                ))}
              </div>
              <button
                onClick={handleLogin}
                disabled={loading === 'Auth: verify-token'}
                className="w-full py-3 rounded-xl bg-accent text-white font-sans font-semibold text-sm transition-all hover:bg-accent-dark active:scale-95 disabled:opacity-50"
              >
                {loading === 'Auth: verify-token' ? 'Connecting…' : 'Sign in'}
              </button>
            </div>
          )}
        </section>

        {/* Admin key */}
        <section className="bg-surface rounded-2xl p-5 border border-ink/6 shadow-sm">
          <div className="font-sans text-xs font-medium text-ink-muted mb-2 uppercase tracking-wide">
            Admin API key
          </div>
          <input
            value={adminKey}
            onChange={(e) => setAdminKey(e.target.value)}
            className="w-full bg-greige border border-ink/10 rounded-xl px-4 py-3 font-mono text-xs text-ink-muted focus:outline-none focus:border-accent transition-colors"
          />
        </section>

        {/* Seed controls */}
        <section className="bg-surface rounded-2xl p-5 border border-ink/6 shadow-sm">
          <div className="flex items-center gap-2 mb-4">
            <Sprout size={16} className="text-sage" />
            <div className="font-display text-base text-ink">Database seed</div>
          </div>
          <div className="flex flex-col gap-3">
            {seeds.map(({ label, fn, desc }) => (
              <button
                key={label}
                onClick={() => run(label, fn)}
                disabled={loading !== null}
                className="w-full text-left px-4 py-3.5 rounded-xl bg-greige border border-ink/8 hover:border-sage/40 transition-all disabled:opacity-50 group"
              >
                <div className="font-sans text-sm font-medium text-ink group-hover:text-sage transition-colors flex items-center justify-between">
                  {label}
                  {loading === label && (
                    <RefreshCw size={14} className="text-sage animate-spin" />
                  )}
                </div>
                <div className="font-sans text-xs text-ink-muted mt-0.5">{desc}</div>
              </button>
            ))}
          </div>
        </section>

        {/* Demo: simulate shield response */}
        <section className="bg-surface rounded-2xl p-5 border border-ink/6 shadow-sm">
          <div className="flex items-center gap-2 mb-4">
            <ShieldCheck size={16} className="text-sage" />
            <div className="font-display text-base text-ink">Demo controls</div>
          </div>
          <div className="flex flex-col gap-3">
            <div className="bg-greige rounded-xl px-4 py-3">
              <div className="font-sans text-xs text-ink-muted mb-1">Active incident</div>
              <div className="font-mono text-xs text-ink truncate">
                {incidentId ?? 'None — trigger an SOS first'}
              </div>
            </div>
            <button
              onClick={() =>
                incidentId &&
                run('Simulate: shields accept', () => simulateShieldAccept(incidentId))
              }
              disabled={!incidentId || loading !== null}
              className="w-full text-left px-4 py-3.5 rounded-xl bg-greige border border-ink/8 hover:border-sage/40 transition-all disabled:opacity-40 group"
            >
              <div className="font-sans text-sm font-medium text-ink group-hover:text-sage transition-colors flex items-center justify-between">
                Simulate shields accepting SOS
                {loading === 'Simulate: shields accept' && (
                  <RefreshCw size={14} className="text-sage animate-spin" />
                )}
              </div>
              <div className="font-sans text-xs text-ink-muted mt-0.5">
                Makes all notified shields respond to the active incident
              </div>
            </button>
          </div>
        </section>

        {/* Console */}
        <section className="bg-ink rounded-2xl p-4 border border-ink shadow-sm">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <Terminal size={14} className="text-sage" />
              <div className="font-mono text-xs text-sage">API console</div>
            </div>
            {log.length > 0 && (
              <button
                onClick={() => setLog([])}
                className="font-mono text-[10px] text-ink-muted hover:text-sage transition-colors"
              >
                clear
              </button>
            )}
          </div>

          <div className="flex flex-col gap-2 max-h-72 overflow-y-auto">
            {log.length === 0 ? (
              <div className="font-mono text-xs text-ink-muted/50 text-center py-4">
                No requests yet
              </div>
            ) : (
              log.map((entry, i) => (
                <div key={i} className="flex flex-col gap-1">
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-[10px] text-ink-muted/50">{entry.ts}</span>
                    <span className={`font-mono text-[10px] font-semibold ${entry.ok ? 'text-sage' : 'text-accent'}`}>
                      {entry.ok ? '✓' : '✗'} {entry.label}
                    </span>
                  </div>
                  <pre className="font-mono text-[10px] text-sage/70 bg-white/4 rounded px-3 py-2 overflow-x-auto whitespace-pre-wrap break-all">
                    {entry.body}
                  </pre>
                </div>
              ))
            )}
          </div>
        </section>
      </main>

      <BottomTabBar />
    </div>
  )
}
