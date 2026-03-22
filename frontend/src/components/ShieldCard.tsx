import { ShieldStatusInfo } from '../api/endpoints'
import { Clock, Navigation } from 'lucide-react'

interface Props {
  shield: ShieldStatusInfo
  index?: number
}

const statusLabel: Record<string, { text: string; color: string }> = {
  notified: { text: 'Notified', color: 'text-ink-muted' },
  responding: { text: 'En route', color: 'text-sage' },
  arrived: { text: 'Arrived', color: 'text-sage' },
  declined: { text: 'Unavailable', color: 'text-ink-muted' },
}

function formatEta(seconds: number | null): string {
  if (seconds === null) return 'En route'
  if (seconds < 60) return `<1 min`
  return `${Math.round(seconds / 60)} min`
}

export default function ShieldCard({ shield, index = 0 }: Props) {
  const s = statusLabel[shield.status] ?? { text: shield.status, color: 'text-ink-muted' }
  const isDeclined = shield.status === 'declined'

  return (
    <div
      className={`animate-fade-up bg-surface rounded-2xl px-5 py-4 flex items-center gap-4 border transition-all ${
        isDeclined ? 'opacity-40 border-ink/5' : 'border-sage/20 shadow-sm'
      }`}
      style={{ animationDelay: `${index * 80}ms` }}
    >
      {/* Shield avatar */}
      <div
        className={`w-10 h-10 rounded-full flex items-center justify-center text-white font-sans font-semibold text-sm flex-shrink-0 ${
          isDeclined ? 'bg-ink-muted/30' : 'bg-sage'
        }`}
      >
        {(shield.name ?? 'S')[0].toUpperCase()}
      </div>

      {/* Info */}
      <div className="flex-1 min-w-0">
        <div className="font-sans font-medium text-ink text-sm truncate">
          {shield.name || 'Shield volunteer'}
        </div>
        <div className={`font-sans text-xs mt-0.5 ${s.color}`}>{s.text}</div>
      </div>

      {/* ETA */}
      {!isDeclined && (
        <div className="flex items-center gap-1 text-ink-muted flex-shrink-0">
          {shield.status === 'arrived' ? (
            <Navigation size={14} className="text-sage" />
          ) : (
            <Clock size={14} />
          )}
          <span className="font-sans text-xs">
            {shield.status === 'arrived' ? 'Here' : formatEta(shield.eta_seconds)}
          </span>
        </div>
      )}
    </div>
  )
}
