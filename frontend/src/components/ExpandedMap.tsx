"use client";

import { useEffect } from "react";
import {
  MapContainer,
  TileLayer,
  Marker,
  Circle,
  Popup,
  useMap,
} from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { X } from "lucide-react";
import type { LatLng, ShieldStatusInfo } from "@/lib/types";

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

function makeShieldIcon(name: string) {
  return L.divIcon({
    className: "",
    html: `<div style="
      width:28px;height:28px;border-radius:50%;background:rgba(184,207,192,0.2);
      border:1.5px solid #B8CFC0;display:flex;align-items:center;justify-content:center;
      font-family:'Outfit',sans-serif;font-size:10px;font-weight:600;color:#6B2E4F;
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
  onClose: () => void;
}

export default function ExpandedMap({
  position,
  shields,
  convergence,
  respondingCount,
  onClose,
}: Props) {
  const responding = shields.filter(
    (s) => s.status === "responding" || s.status === "arrived",
  );

  return (
    <div className="fixed inset-0 z-50 bg-bg/95 backdrop-blur-sm animate-fade-in">
      {/* Header bar */}
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
        {responding.map((sh) => (
          <Marker
            key={sh.shield_id}
            position={[sh.lat, sh.lng]}
            icon={makeShieldIcon(sh.name)}
          >
            <Popup>
              <span>
                {sh.name} ·{" "}
                {sh.eta_seconds
                  ? `${Math.ceil(sh.eta_seconds / 60)} min`
                  : "en route"}
              </span>
            </Popup>
          </Marker>
        ))}

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
    </div>
  );
}
