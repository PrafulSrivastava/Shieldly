import { useState } from 'react'
import { X } from 'lucide-react'
import { verifyToken } from '../api/endpoints'
import { useStore } from '../store'

interface Props {
  onClose: () => void
  defaultRole?: 'person' | 'shield'
}

export default function LoginModal({ onClose, defaultRole = 'person' }: Props) {
  const [phone, setPhone] = useState('+491700000001')
  const [name, setName] = useState('Demo User')
  const [role, setRole] = useState<'person' | 'shield'>(defaultRole)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const { setAuth } = useStore()

  async function handleLogin() {
    setLoading(true)
    setError(null)
    try {
      const resp = await verifyToken(phone, name, role)
      setAuth(resp.access_token, resp.user_id, resp.role, resp.phone)
      onClose()
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Login failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="fixed inset-0 z-[200] flex items-end justify-center bg-ink/30 backdrop-blur-sm">
      <div className="w-full max-w-md bg-surface rounded-t-3xl p-6 pb-10 animate-slide-up shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <div className="font-display text-xl text-ink">Sign in</div>
            <div className="font-sans text-xs text-ink-muted mt-0.5">
              Use your phone number (dev mock mode)
            </div>
          </div>
          <button
            onClick={onClose}
            className="w-8 h-8 rounded-full bg-greige flex items-center justify-center text-ink-muted hover:text-ink transition-colors"
          >
            <X size={16} />
          </button>
        </div>

        {/* Phone */}
        <div className="mb-4">
          <label className="font-sans text-xs font-medium text-ink-muted mb-1.5 block uppercase tracking-wide">
            Phone number
          </label>
          <input
            type="text"
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
            className="w-full bg-greige border border-ink/10 rounded-xl px-4 py-3 font-sans text-ink text-sm focus:outline-none focus:border-accent transition-colors"
            placeholder="+491700000001"
          />
        </div>

        {/* Name */}
        <div className="mb-4">
          <label className="font-sans text-xs font-medium text-ink-muted mb-1.5 block uppercase tracking-wide">
            Name
          </label>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="w-full bg-greige border border-ink/10 rounded-xl px-4 py-3 font-sans text-ink text-sm focus:outline-none focus:border-accent transition-colors"
            placeholder="Your name"
          />
        </div>

        {/* Role */}
        <div className="mb-6">
          <label className="font-sans text-xs font-medium text-ink-muted mb-1.5 block uppercase tracking-wide">
            Role
          </label>
          <div className="flex gap-2">
            {(['person', 'shield'] as const).map((r) => (
              <button
                key={r}
                onClick={() => setRole(r)}
                className={`flex-1 py-2.5 rounded-xl font-sans text-sm font-medium border transition-all ${
                  role === r
                    ? 'bg-accent text-white border-accent'
                    : 'bg-greige text-ink-muted border-ink/10 hover:border-accent/40'
                }`}
              >
                {r.charAt(0).toUpperCase() + r.slice(1)}
              </button>
            ))}
          </div>
        </div>

        {error && (
          <div className="mb-4 text-sm text-accent font-sans bg-rose/20 rounded-xl px-4 py-3">
            {error}
          </div>
        )}

        <button
          onClick={handleLogin}
          disabled={loading || !phone || !name}
          className="w-full py-4 bg-accent text-white rounded-2xl font-sans font-semibold text-base transition-all hover:bg-accent-dark active:scale-95 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {loading ? 'Signing in…' : 'Continue'}
        </button>
      </div>
    </div>
  )
}
