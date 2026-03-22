"use client";

import { useRef, useEffect } from "react";
import type { LatLng, ShieldStatusInfo } from "@/lib/types";

interface Props {
  position: LatLng | null;
  shields: ShieldStatusInfo[];
  convergence: LatLng | null;
  size?: number;
  onExpand: () => void;
}

function shieldColor(status: string): string {
  switch (status) {
    case "responding":
    case "arrived":
      return "#4ADE80";
    case "declined":
      return "#F87171";
    case "notified":
      return "#FBBF24";
    default:
      return "#B8CFC0";
  }
}

function toRadar(
  person: LatLng,
  target: LatLng,
  r: number,
): { x: number; y: number } | null {
  const mPerDegLng = 111_320 * Math.cos((person.lat * Math.PI) / 180);
  const dx = (target.lng - person.lng) * mPerDegLng;
  const dy = (target.lat - person.lat) * 111_320;
  const scale = r / 2_000;
  const px = r + dx * scale;
  const py = r - dy * scale;
  const dist = Math.hypot(px - r, py - r);
  if (dist > r - 4) return null;
  return { x: px, y: py };
}

export function MiniMap({
  position,
  shields,
  convergence,
  size = 80,
  onExpand,
}: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const rafRef = useRef<number>(0);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const dpr = window.devicePixelRatio || 1;
    canvas.width = size * dpr;
    canvas.height = size * dpr;

    const r = size / 2;

    const draw = () => {
      ctx.save();
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, size, size);

      ctx.beginPath();
      ctx.arc(r, r, r, 0, Math.PI * 2);
      ctx.fillStyle = "#FFFFFF";
      ctx.fill();
      ctx.clip();

      ctx.strokeStyle = "rgba(232,223,245,0.5)";
      ctx.lineWidth = 0.5;
      for (const frac of [0.33, 0.66, 1]) {
        ctx.beginPath();
        ctx.arc(r, r, r * frac, 0, Math.PI * 2);
        ctx.stroke();
      }

      ctx.strokeStyle = "rgba(232,223,245,0.3)";
      ctx.beginPath();
      ctx.moveTo(r, 0);
      ctx.lineTo(r, size);
      ctx.moveTo(0, r);
      ctx.lineTo(size, r);
      ctx.stroke();

      if (position) {
        if (convergence) {
          const cp = toRadar(position, convergence, r);
          if (cp) {
            ctx.strokeStyle = "#E8634A";
            ctx.lineWidth = 1.2;
            const a = 5;
            ctx.beginPath();
            ctx.moveTo(cp.x - a, cp.y);
            ctx.lineTo(cp.x + a, cp.y);
            ctx.moveTo(cp.x, cp.y - a);
            ctx.lineTo(cp.x, cp.y + a);
            ctx.stroke();
          }
        }

        shields.forEach((sh) => {
          const sp = toRadar(position, { lat: sh.lat, lng: sh.lng }, r);
          if (sp) {
            ctx.beginPath();
            ctx.arc(sp.x, sp.y, 2.5, 0, Math.PI * 2);
            ctx.fillStyle = shieldColor(sh.status);
            ctx.fill();
          }
        });

        const pulse = 0.55 + 0.45 * Math.sin(Date.now() / 500);
        ctx.beginPath();
        ctx.arc(r, r, 3.5, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(107,46,79,${pulse})`;
        ctx.fill();
        ctx.beginPath();
        ctx.arc(r, r, 6, 0, Math.PI * 2);
        ctx.strokeStyle = `rgba(107,46,79,${pulse * 0.25})`;
        ctx.lineWidth = 0.8;
        ctx.stroke();
      }

      ctx.restore();
      rafRef.current = requestAnimationFrame(draw);
    };

    draw();
    return () => cancelAnimationFrame(rafRef.current);
  }, [position, shields, convergence, size]);

  return (
    <button
      onClick={onExpand}
      className="relative rounded-card overflow-hidden border border-lavender-muted shadow-soft group cursor-pointer"
      style={{ width: size, height: size }}
    >
      <canvas
        ref={canvasRef}
        className="w-full h-full"
        style={{ width: size, height: size }}
      />
      <div className="absolute inset-0 scanline-overlay pointer-events-none opacity-20" />
      <div className="absolute inset-0 bg-coral/0 group-hover:bg-coral/[0.04] transition-colors pointer-events-none" />
    </button>
  );
}
