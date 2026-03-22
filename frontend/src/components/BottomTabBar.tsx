import { useNavigate, useLocation } from 'react-router-dom'
import { ShieldAlert, Map, Shield, Settings } from 'lucide-react'

const tabs = [
  { path: '/', label: 'Unsafe', icon: ShieldAlert },
  { path: '/dashboard', label: 'Map', icon: Map },
  { path: '/shield', label: 'Shield', icon: Shield },
  { path: '/admin', label: 'Admin', icon: Settings },
]

export default function BottomTabBar() {
  const navigate = useNavigate()
  const { pathname } = useLocation()

  return (
    <nav className="fixed bottom-0 left-0 right-0 z-[9999] bg-surface/95 backdrop-blur-sm border-t border-ink/8 flex">
      {tabs.map(({ path, label, icon: Icon }) => {
        const active = pathname === path
        return (
          <button
            key={path}
            onClick={() => navigate(path)}
            className={`flex-1 flex flex-col items-center justify-center gap-1 py-3 transition-colors ${
              active ? 'text-accent' : 'text-ink-muted'
            }`}
          >
            <Icon
              size={22}
              strokeWidth={active ? 2.2 : 1.6}
              className="transition-all"
            />
            <span className="font-sans text-[11px] font-medium leading-none">
              {label}
            </span>
            {active && (
              <span className="absolute bottom-0 w-8 h-0.5 bg-accent rounded-t-full" />
            )}
          </button>
        )
      })}
    </nav>
  )
}
