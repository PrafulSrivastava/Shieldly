"use client";

import { useEffect, useState, useRef } from "react";
import {
  MapContainer,
  TileLayer,
  Marker,
  Circle,
  Popup,
  Polyline,
  useMap,
} from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { X } from "lucide-react";
import type { LatLng, ShieldStatusInfo, RouteToNearestShield } from "@/lib/types";
import { haversine } from "@/lib/types";

/* ── Custom Leaflet icons — warm editorial ───────────────────────────── */

const personIcon = L.divIcon({
  className: "",
  html: `<div style="
    width:14px;height:14px;border-radius:50%;background:#6B2E4F;
    box-shadow:0 0 10px rgba(107,46,79,0.4),0 0 24px rgba(107,46,79,0.15);
  "></div>`,
  iconSize: [14, 14],
  iconAnchor: [7, 7],
});

function shieldIconColors(status: string): {
  bg: string;
  border: string;
  text: string;
} {
  switch (status) {
    case "responding":
    case "arrived":
      return {
        bg: "rgba(74,222,128,0.2)",
        border: "#4ADE80",
        text: "#166534",
      };
    case "declined":
      return {
        bg: "rgba(248,113,113,0.2)",
        border: "#F87171",
        text: "#991B1B",
      };
    case "notified":
      return {
        bg: "rgba(74,222,128,0.2)",
        border: "#4ADE80",
        text: "#166534",
      };
    default:
      return {
        bg: "rgba(184,207,192,0.2)",
        border: "#B8CFC0",
        text: "#6B2E4F",
      };
  }
}

function makeShieldIcon(name: string, status: string) {
  const c = shieldIconColors(status);
  return L.divIcon({
    className: "",
    html: `<div style="
      width:28px;height:28px;border-radius:50%;background:${c.bg};
      border:1.5px solid ${c.border};display:flex;align-items:center;justify-content:center;
      font-family:'Outfit',sans-serif;font-size:10px;font-weight:600;color:${c.text};
    ">${name.charAt(0).toUpperCase()}</div>`,
    iconSize: [28, 28],
    iconAnchor: [14, 14],
  });
}

const convergenceIcon = L.divIcon({
  className: "",
  html: `<div style="
    width:20px;height:20px;position:relative;
  ">
    <div style="position:absolute;inset:0;border:2px solid #E8634A;border-radius:3px;"></div>
    <div style="position:absolute;inset:5px;background:#E8634A;border-radius:1px;"></div>
  </div>`,
  iconSize: [20, 20],
  iconAnchor: [10, 10],
});

/* ── Helper: keep map centred on position ─────────────────────────────── */

function FlyTo({ center }: { center: LatLng }) {
  const map = useMap();
  useEffect(() => {
    map.flyTo([center.lat, center.lng], map.getZoom(), { duration: 0.8 });
  }, [center.lat, center.lng, map]);
  return null;
}

/* ── Component ────────────────────────────────────────────────────────── */

interface Props {
  position: LatLng;
  shields: ShieldStatusInfo[];
  convergence: LatLng | null;
  respondingCount: number;
  routeToShield?: RouteToNearestShield | null;
  onClose?: () => void;
  embedded?: boolean;
}

async function fetchWalkingRoute(
  from: LatLng,
  to: { lat: number; lng: number },
): Promise<{
  route_points: [number, number][];
  distance_meters: number;
  duration_seconds: number;
} | null> {
  try {
    const url = `https://router.project-osrm.org/route/v1/foot/${from.lng},${from.lat};${to.lng},${to.lat}?overview=full&geometries=geojson`;
    const res = await fetch(url);
    if (!res.ok) return null;
    const data = await res.json();
    if (data.code !== "Ok" || !data.routes?.length) return null;
    const route = data.routes[0];
    const coords: [number, number][] = route.geometry.coordinates.map(
      ([lng, lat]: [number, number]) => [lat, lng] as [number, number],
    );
    return {
      route_points: coords,
      distance_meters: Math.round(route.distance),
      duration_seconds: Math.round(route.duration),
    };
  } catch {
    return null;
  }
}

export default function ExpandedMap({
  position,
  shields,
  convergence,
  respondingCount,
  routeToShield,
  onClose,
  embedded,
}: Props) {
  const [fallbackRoute, setFallbackRoute] = useState<RouteToNearestShield | null>(null);
  const fetchIdRef = useRef(0);

  useEffect(() => {
    if (routeToShield || shields.length === 0) {
      setFallbackRoute(null);
      return;
    }
    const closest = shields.reduce((best, sh) => {
      const d = haversine(position, { lat: sh.lat, lng: sh.lng });
      const bd = haversine(position, { lat: best.lat, lng: best.lng });
      return d < bd ? sh : best;
    }, shields[0]);

    const id = ++fetchIdRef.current;

    fetchWalkingRoute(position, closest).then((result) => {
      if (id !== fetchIdRef.current) return;
      if (!result) return;
      setFallbackRoute({
        shield_id: closest.shield_id,
        shield_name: closest.name,
        distance_meters: result.distance_meters,
        duration_seconds: result.duration_seconds,
        route_points: result.route_points,
      });
    });
  }, [routeToShield, shields, position]);

  const effectiveRoute = routeToShield ?? fallbackRoute;

  const routeLatLngs: L.LatLngTuple[] | null =
    effectiveRoute?.route_points?.length
      ? effectiveRoute.route_points.map(([lat, lng]) => [lat, lng] as L.LatLngTuple)
      : null;
  return (
    <div
      className={
        embedded
          ? "absolute inset-0"
          : "fixed inset-0 z-50 bg-bg/95 backdrop-blur-sm animate-fade-in"
      }
    >
      {/* Header bar — overlay mode only */}
      {!embedded && onClose && (
        <div className="absolute top-0 left-0 right-0 z-[1000] flex items-center justify-between px-5 py-4 bg-gradient-to-b from-bg/90 to-transparent">
          <div className="flex items-center gap-2.5">
            <span className="w-2 h-2 rounded-full bg-sage animate-dot-pulse" />
            <span className="font-body text-[11px] text-plum tracking-[0.1em] font-semibold">
              {respondingCount} Shield{respondingCount !== 1 ? "s" : ""}{" "}
              Responding
            </span>
          </div>
          <button
            onClick={onClose}
            className="w-9 h-9 rounded-full bg-white border border-lavender-muted shadow-soft flex items-center justify-center hover:bg-blush transition-colors"
          >
            <X className="w-4 h-4 text-plum/50" />
          </button>
        </div>
      )}

      {/* Map */}
      <MapContainer
        center={[position.lat, position.lng]}
        zoom={16}
        className="h-full w-full"
        zoomControl={false}
        attributionControl={false}
        style={{ background: "#FFF8F3" }}
      >
        <TileLayer
          url="https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png"
          attribution=""
        />
        <FlyTo center={position} />

        {/* Incident radius */}
        <Circle
          center={[position.lat, position.lng]}
          radius={1000}
          pathOptions={{
            color: "rgba(232,99,74,0.15)",
            fillColor: "rgba(232,99,74,0.05)",
            fillOpacity: 1,
            weight: 1,
          }}
        />

        {/* Person */}
        <Marker position={[position.lat, position.lng]} icon={personIcon} />

        {/* Shields */}
        {shields.map((sh) => (
          <Marker
            key={sh.shield_id}
            position={[sh.lat, sh.lng]}
            icon={makeShieldIcon(sh.name, sh.status)}
          >
            <Popup>
              <span>
                {sh.name} · {sh.status}
                {sh.eta_seconds
                  ? ` · ${Math.ceil(sh.eta_seconds / 60)} min`
                  : ""}
              </span>
            </Popup>
          </Marker>
        ))}

        {/* Route to nearest shield */}
        {routeLatLngs && (
          <Polyline
            positions={routeLatLngs}
            pathOptions={{
              color: "#6B2E4F",
              weight: 4,
              opacity: 0.7,
              dashArray: "8 6",
              lineCap: "round",
              lineJoin: "round",
            }}
          />
        )}

        {/* Convergence */}
        {convergence && (
          <Marker
            position={[convergence.lat, convergence.lng]}
            icon={convergenceIcon}
          >
            <Popup>
              <span className="font-semibold text-coral">Meet Here</span>
            </Popup>
          </Marker>
        )}
      </MapContainer>

      {/* Route info card */}
      {effectiveRoute && (
        <div className="absolute bottom-4 left-1/2 -translate-x-1/2 z-[1000]">
          <div className="bg-white/90 backdrop-blur-md rounded-2xl border border-lavender-muted shadow-soft px-4 py-2.5 flex items-center gap-3">
            <div className="w-8 h-8 rounded-full bg-plum/10 border border-plum/20 flex items-center justify-center">
              <svg className="w-4 h-4 text-plum" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M5 12h14M12 5l7 7-7 7"/>
              </svg>
            </div>
            <div className="flex flex-col">
              <span className="font-body text-[11px] text-plum font-semibold tracking-[0.04em]">
                Walking to {effectiveRoute.shield_name}
              </span>
              <span className="font-body text-[10px] text-warm-muted/60 tracking-[0.06em]">
                {Math.ceil(effectiveRoute.duration_seconds / 60)} min · {effectiveRoute.distance_meters} m
              </span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
