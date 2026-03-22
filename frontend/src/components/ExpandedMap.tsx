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

/* ── Custom Leaflet icons ─────────────────────────────────────────────── */

const personIcon = L.divIcon({
  className: "",
  html: `<div style="
    width:14px;height:14px;border-radius:50%;background:#fff;
    box-shadow:0 0 10px rgba(255,255,255,0.5),0 0 24px rgba(255,255,255,0.2);
  "></div>`,
  iconSize: [14, 14],
  iconAnchor: [7, 7],
});

function makeShieldIcon(name: string) {
  return L.divIcon({
    className: "",
    html: `<div style="
      width:28px;height:28px;border-radius:50%;background:rgba(0,230,118,0.15);
      border:1.5px solid #00E676;display:flex;align-items:center;justify-content:center;
      font-family:'IBM Plex Mono',monospace;font-size:10px;font-weight:600;color:#00E676;
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
    <div style="position:absolute;inset:0;border:2px solid #FF9800;border-radius:3px;"></div>
    <div style="position:absolute;inset:5px;background:#FF9800;border-radius:1px;"></div>
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
    <div className="fixed inset-0 z-50 bg-void/95 backdrop-blur-sm animate-fade-in">
      {/* Header bar */}
      <div className="absolute top-0 left-0 right-0 z-[1000] flex items-center justify-between px-5 py-4 bg-gradient-to-b from-void/90 to-transparent">
        <div className="flex items-center gap-2.5">
          <span className="w-2 h-2 rounded-full bg-shield animate-dot-pulse" />
          <span className="font-mono text-[11px] text-shield tracking-[1.5px]">
            {respondingCount} SHIELD{respondingCount !== 1 ? "S" : ""}{" "}
            RESPONDING
          </span>
        </div>
        <button
          onClick={onClose}
          className="w-9 h-9 rounded-full bg-void-light border border-void-border flex items-center justify-center hover:bg-void-lighter transition-colors"
        >
          <X className="w-4 h-4 text-white/50" />
        </button>
      </div>

      {/* Map */}
      <MapContainer
        center={[position.lat, position.lng]}
        zoom={16}
        className="h-full w-full"
        zoomControl={false}
        attributionControl={false}
        style={{ background: "#0A0A0F" }}
      >
        <TileLayer
          url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
          attribution=""
        />
        <FlyTo center={position} />

        {/* Incident radius — 1 km soft circle */}
        <Circle
          center={[position.lat, position.lng]}
          radius={1000}
          pathOptions={{
            color: "rgba(255,23,68,0.12)",
            fillColor: "rgba(255,23,68,0.04)",
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
            <Popup className="!bg-void-light !text-white !border-void-border !rounded-lg !shadow-xl !font-mono !text-xs">
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
            <Popup className="!bg-void-light !text-amber !border-void-border !rounded-lg !shadow-xl !font-mono !text-xs">
              <span>MEET HERE</span>
            </Popup>
          </Marker>
        )}
      </MapContainer>
    </div>
  );
}
