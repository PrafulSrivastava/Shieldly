import { useEffect, useState, useRef } from 'react'
import { MapContainer, TileLayer, Circle, Marker, Popup, useMap } from 'react-leaflet'
import MarkerClusterGroup from 'react-leaflet-cluster'
import L from 'leaflet'
import { RefreshCw, AlertTriangle } from 'lucide-react'
import { getMapData, getAdminStats, MapShield, MapHotspot, AdminStats } from '../api/endpoints'
import BottomTabBar from '../components/BottomTabBar'
import Skeleton from '../components/Skeleton'

// Center between Heilbronn and Stuttgart
const MAP_CENTER: [number, number] = [49.14, 9.22]
const MAP_ZOOM = 11

// Risk level visual config
const RISK_CONFIG = {
  low: { fillOpacity: 0.08, radius: 450 },
  medium: { fillOpacity: 0.16, radius: 650 },
  high: { fillOpacity: 0.28, radius: 950 },
}
const HOTSPOT_COLOR = '#C4543A'

// Custom shield marker
function makeShieldIcon(status: string) {
  const active = status === 'active'
  const bg = active ? '#7BB3A6' : '#B0C4BE'
  const border = active ? '#5A9A8D' : '#8EA89F'
  return L.divIcon({
    className: '',
    html: `<div style="
      width:28px;height:28px;
      background:${bg};
      border:2px solid ${border};
      border-radius:50% 50% 50% 0;
      transform:rotate(-45deg);
      box-shadow:0 2px 8px rgba(0,0,0,0.18);
    "></div>`,
    iconSize: [28, 28],
    iconAnchor: [14, 24],
    popupAnchor: [0, -28],
  })
}

// Custom cluster icon
// eslint-disable-next-line @typescript-eslint/no-explicit-any
function makeClusterIcon(cluster: any) {
  const count = cluster.getChildCount()
  const size = count > 50 ? 52 : count > 10 ? 44 : 36
  return L.divIcon({
    html: `<div class="custom-cluster" style="width:${size}px;height:${size}px;font-size:${size > 44 ? 15 : 13}px">${count}</div>`,
    className: '',
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
  })
}

function formatLastSeen(ts: string | null): string {
  if (!ts) return 'Recently active'
  const d = new Date(ts)
  const mins = Math.floor((Date.now() - d.getTime()) / 60000)
  if (mins < 1) return 'Just now'
  if (mins < 60) return `${mins}m ago`
  return `${Math.floor(mins / 60)}h ago`
}

// Selected shield drawer
interface DrawerProps {
  shield: MapShield | null
  onClose: () => void
}
function ShieldDrawer({ shield, onClose }: DrawerProps) {
  if (!shield) return null
  return (
    <div className="absolute bottom-20 left-0 right-0 z-[1000] px-4 pointer-events-none">
      <div className="bg-surface rounded-2xl p-5 shadow-xl border border-ink/6 pointer-events-auto animate-slide-up max-w-md mx-auto">
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="font-display text-lg text-ink">{shield.name}</div>
            <div className="font-sans text-xs text-ink-muted mt-0.5">
              {shield.status === 'active' ? (
                <span className="text-sage">● Active</span>
              ) : (
                <span className="text-ink-muted">● {shield.status}</span>
              )}
              <span className="mx-1.5 opacity-30">|</span>
              {formatLastSeen(shield.last_seen)}
            </div>
          </div>
          <button
            onClick={onClose}
            className="w-7 h-7 rounded-full bg-greige flex items-center justify-center text-ink-muted hover:text-ink"
          >
            <span className="text-sm">✕</span>
          </button>
        </div>
        <div className="mt-3 pt-3 border-t border-ink/6 font-sans text-xs text-ink-muted">
          {shield.lat.toFixed(4)}°N, {shield.lng.toFixed(4)}°E
        </div>
      </div>
    </div>
  )
}

// Stats panel
interface StatsPanelProps {
  stats: AdminStats | null
  hotspotCount: number
  loading: boolean
  onRefresh: () => void
}
function StatsPanel({ stats, hotspotCount, loading, onRefresh }: StatsPanelProps) {
  return (
    <div className="absolute top-4 left-4 z-[1000] bg-surface/92 backdrop-blur-md rounded-2xl p-4 shadow-lg border border-white/30 min-w-[160px]">
      <div className="font-display text-lg text-ink mb-3">
        Shieldly<span className="text-accent">•</span>
      </div>
      {loading ? (
        <div className="flex flex-col gap-2">
          <Skeleton className="h-4 w-28" />
          <Skeleton className="h-4 w-24" />
          <Skeleton className="h-4 w-20" />
        </div>
      ) : (
        <div className="flex flex-col gap-2">
          <StatRow color="bg-sage" label={`${stats?.active_shields ?? 0} shields active`} />
          <StatRow color="bg-accent" label={`${hotspotCount} risk zones`} />
          <StatRow color="bg-lavender" label={`${stats?.total_incidents ?? 0} total SOS`} />
        </div>
      )}
      <button
        onClick={onRefresh}
        className="mt-3 flex items-center gap-1.5 font-sans text-[11px] text-ink-muted hover:text-ink transition-colors"
      >
        <RefreshCw size={11} />
        Refresh
      </button>
    </div>
  )
}

function StatRow({ color, label }: { color: string; label: string }) {
  return (
    <div className="flex items-center gap-2">
      <div className={`w-2 h-2 rounded-full flex-shrink-0 ${color}`} />
      <span className="font-sans text-xs text-ink">{label}</span>
    </div>
  )
}

// Recenter button
function RecenterButton() {
  const map = useMap()
  return (
    <button
      onClick={() => map.flyTo(MAP_CENTER, MAP_ZOOM, { duration: 1 })}
      className="absolute bottom-24 right-4 z-[1000] w-10 h-10 bg-surface/92 backdrop-blur-sm rounded-xl shadow-md border border-white/30 flex items-center justify-center text-ink-muted hover:text-ink transition-colors"
      title="Recenter map"
    >
      <span className="text-lg">⊕</span>
    </button>
  )
}

export default function MapDashboard() {
  const [shields, setShields] = useState<MapShield[]>([])
  const [hotspots, setHotspots] = useState<MapHotspot[]>([])
  const [stats, setStats] = useState<AdminStats | null>(null)
  const [selectedShield, setSelectedShield] = useState<MapShield | null>(null)
  const [loadingMap, setLoadingMap] = useState(true)
  const [errorBanner, setErrorBanner] = useState<string | null>(null)
  const loadedRef = useRef(false)

  async function loadData() {
    setLoadingMap(true)
    setErrorBanner(null)
    try {
      const [mapData, statsData] = await Promise.allSettled([
        getMapData(),
        getAdminStats(),
      ])

      if (mapData.status === 'fulfilled') {
        // Guard: only render shields with valid finite non-zero coords
        const safeShields = (mapData.value.shields ?? []).filter(
          (s) =>
            typeof s.lat === 'number' &&
            typeof s.lng === 'number' &&
            isFinite(s.lat) &&
            isFinite(s.lng) &&
            !(s.lat === 0 && s.lng === 0),
        )
        // Guard: only render hotspots with valid coords and count
        const safeHotspots = (mapData.value.hotspots ?? []).filter(
          (h) =>
            typeof h.lat === 'number' &&
            typeof h.lng === 'number' &&
            isFinite(h.lat) &&
            isFinite(h.lng) &&
            typeof h.incident_count === 'number' &&
            h.incident_count > 0,
        )
        setShields(safeShields)
        setHotspots(safeHotspots)
      } else {
        setErrorBanner('Live shield data unavailable — map may not reflect current positions')
      }

      if (statsData.status === 'fulfilled') {
        setStats(statsData.value)
      }
    } finally {
      setLoadingMap(false)
    }
  }

  useEffect(() => {
    if (loadedRef.current) return
    loadedRef.current = true
    loadData()
  }, [])

  return (
    <div className="h-screen w-full relative">
      {/* Error banner */}
      {errorBanner && (
        <div className="absolute top-4 left-1/2 -translate-x-1/2 z-[2000] bg-surface/95 border border-rose/30 rounded-2xl px-4 py-3 flex items-center gap-2 shadow-md max-w-xs text-center">
          <AlertTriangle size={14} className="text-accent flex-shrink-0" />
          <span className="font-sans text-xs text-ink-muted">{errorBanner}</span>
          <button onClick={() => setErrorBanner(null)} className="text-ink-muted/60 ml-1">✕</button>
        </div>
      )}

        <MapContainer
        center={MAP_CENTER}
        zoom={MAP_ZOOM}
        style={{ height: 'calc(100vh - 64px)', width: '100%' }}
        zoomControl={false}
      >
        {/* Warm CartoDB Voyager tiles */}
        <TileLayer
          attribution='&copy; <a href="https://carto.com/">CARTO</a>'
          url="https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png"
        />

        {/* Hotspot radius circles */}
        {hotspots.map((h) => {
          const cfg = RISK_CONFIG[h.risk_level] ?? RISK_CONFIG.low
          return (
            <Circle
              key={h.geohash}
              center={[h.lat, h.lng]}
              radius={cfg.radius}
              pathOptions={{
                color: HOTSPOT_COLOR,
                fillColor: HOTSPOT_COLOR,
                fillOpacity: cfg.fillOpacity,
                weight: 0,
              }}
            >
              <Popup>
                <div>
                  <div className="font-sans font-semibold text-sm text-ink mb-1">
                    Risk zone · {h.risk_level}
                  </div>
                  <div className="font-sans text-xs text-ink-muted">
                    {h.incident_count} incident{h.incident_count !== 1 ? 's' : ''} recorded
                  </div>
                </div>
              </Popup>
            </Circle>
          )
        })}

        {/* Shield markers with clustering */}
        <MarkerClusterGroup
          chunkedLoading
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          iconCreateFunction={makeClusterIcon as any}
          showCoverageOnHover={false}
          maxClusterRadius={60}
          spiderfyOnMaxZoom={false}
          zoomToBoundsOnClick={true}
          animate={true}
        >
          {shields.map((s) => (
            <Marker
              key={s.id}
              position={[s.lat, s.lng]}
              icon={makeShieldIcon(s.status)}
              eventHandlers={{
                click: () => setSelectedShield(s),
              }}
            />
          ))}
        </MarkerClusterGroup>

        <RecenterButton />
      </MapContainer>

      {/* Floating stats panel */}
      <StatsPanel
        stats={stats}
        hotspotCount={hotspots.length}
        loading={loadingMap}
        onRefresh={loadData}
      />

      {/* Shield info drawer */}
      <ShieldDrawer
        shield={selectedShield}
        onClose={() => setSelectedShield(null)}
      />

      <BottomTabBar />
    </div>
  )
}
