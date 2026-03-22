"use client";

import type { LatLng } from "@/lib/types";
import { bearing as calcBearing, haversine } from "@/lib/types";

interface Props {
  position: LatLng | null;
  target: LatLng | null;
  heading: number | null;
  label: string | null;
}

export function NavigationArrow({ position, target, heading, label }: Props) {
  let rotation = 0;
  let distance = 0;

  if (position && target) {
    const b = calcBearing(position, target);
    rotation = heading != null ? b - heading : b;
    distance = haversine(position, target);
  }

  const distStr =
    distance >= 1_000
      ? `${(distance / 1_000).toFixed(1)}km`
      : `${Math.round(distance)}m`;

  return (
    <div className="flex flex-col items-center gap-5">
      {/* Compass */}
      <div
        className="w-28 h-28 transition-transform duration-500 ease-out"
        style={{ transform: `rotate(${rotation}deg)` }}
      >
        <svg viewBox="0 0 100 100" className="w-full h-full drop-shadow-lg">
          {/* Outer ring */}
          <circle
            cx="50"
            cy="50"
            r="47"
            fill="none"
            stroke="rgba(255,255,255,0.06)"
            strokeWidth="0.8"
          />
          {/* Minor ticks */}
          {Array.from({ length: 36 }, (_, i) => i * 10).map((deg) => (
            <line
              key={deg}
              x1="50"
              y1={deg % 90 === 0 ? "5" : "8"}
              x2="50"
              y2="11"
              stroke={
                deg % 90 === 0
                  ? "rgba(255,255,255,0.18)"
                  : "rgba(255,255,255,0.05)"
              }
              strokeWidth={deg % 90 === 0 ? "1" : "0.5"}
              transform={`rotate(${deg} 50 50)`}
            />
          ))}
          {/* Arrow body */}
          <polygon points="50,6 43,52 50,44 57,52" fill="#FF1744" />
          {/* Arrow tail */}
          <polygon
            points="50,94 43,52 50,58 57,52"
            fill="rgba(255,255,255,0.06)"
          />
          {/* Center dot */}
          <circle cx="50" cy="50" r="2.5" fill="rgba(255,255,255,0.2)" />
        </svg>
      </div>

      {/* Navigation text */}
      <div className="text-center space-y-1.5 max-w-xs px-4">
        {label && (
          <p className="font-mono text-[11px] text-amber tracking-[1.5px] uppercase leading-snug">
            WALK TOWARD {label}
          </p>
        )}
        <p className="font-mono text-lg text-white/50 tracking-wider font-medium">
          {distStr}
        </p>
      </div>
    </div>
  );
}
