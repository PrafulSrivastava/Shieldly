"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { TrackingResponse } from "@/lib/types";

export default function TrackingPage({
  params,
}: {
  params: { token: string };
}) {
  const [data, setData] = useState<TrackingResponse | null>(null);
  const [error, setError] = useState(false);

  /* ── Poll REST endpoint ────────────────────────────────────────────── */

  useEffect(() => {
    const poll = () => {
      api
        .getTracking(params.token)
        .then(setData)
        .catch(() => setError(true));
    };
    poll();
    const id = setInterval(poll, 5_000);
    return () => clearInterval(id);
  }, [params.token]);

  /* ── WebSocket for live pushes ─────────────────────────────────────── */

  useEffect(() => {
    const base =
      process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:8000";
    const ws = new WebSocket(
      `${base}/api/v1/track/${params.token}/live`,
    );

    ws.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data);
        if (msg.type === "incident_resolved") {
          setData((prev) =>
            prev
              ? { ...prev, status: "resolved", resolved_at: msg.resolved_at }
              : prev,
          );
        }
        if (msg.type === "shield_location" && data) {
          setData((prev) => {
            if (!prev) return prev;
            return {
              ...prev,
              responding_shields: prev.responding_shields.map((s) =>
                s.shield_index === msg.shield_index
                  ? { ...s, lat: msg.lat, lng: msg.lng }
                  : s,
              ),
            };
          });
        }
      } catch {
        /* ignore */
      }
    };

    const ping = setInterval(() => {
      if (ws.readyState === WebSocket.OPEN)
        ws.send(JSON.stringify({ type: "ping" }));
    }, 25_000);

    return () => {
      clearInterval(ping);
      ws.close();
    };
  }, [params.token, data]);

  /* ── Error state ───────────────────────────────────────────────────── */

  if (error) {
    return (
      <main className="h-dvh w-screen bg-void flex items-center justify-center px-6">
        <div className="text-center space-y-3">
          <p className="font-display text-3xl text-danger tracking-[4px]">
            LINK EXPIRED
          </p>
          <p className="font-mono text-[11px] text-white/25 tracking-wider max-w-xs mx-auto">
            This tracking link is no longer active or the incident has been
            resolved.
          </p>
        </div>
      </main>
    );
  }

  /* ── Loading state ─────────────────────────────────────────────────── */

  if (!data) {
    return (
      <main className="h-dvh w-screen bg-void flex items-center justify-center">
        <div className="flex items-center gap-3">
          <span className="w-2 h-2 rounded-full bg-danger animate-dot-pulse" />
          <span className="font-mono text-[11px] text-white/25 tracking-wider">
            LOADING TRACKING DATA...
          </span>
        </div>
      </main>
    );
  }

  /* ── Resolved state ────────────────────────────────────────────────── */

  if (data.status === "resolved") {
    return (
      <main className="h-dvh w-screen bg-void flex items-center justify-center px-6">
        <div className="text-center space-y-4">
          <div className="w-16 h-16 rounded-full bg-shield/10 border border-shield/30 flex items-center justify-center mx-auto">
            <svg
              className="w-7 h-7 text-shield"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <polyline points="20 6 9 17 4 12" />
            </svg>
          </div>
          <p className="font-display text-2xl text-shield/80 tracking-[4px]">
            INCIDENT RESOLVED
          </p>
          <p className="font-mono text-[10px] text-white/25 tracking-wider">
            The person has confirmed they are safe.
          </p>
        </div>
      </main>
    );
  }

  /* ── Live tracking ─────────────────────────────────────────────────── */

  const shieldCount = data.responding_shields.length;
  const nearestEta = data.responding_shields.reduce(
    (min, s) =>
      s.eta_seconds != null ? Math.min(min, s.eta_seconds) : min,
    Infinity,
  );
  const mapsUrl = `https://www.google.com/maps?q=${data.person_lat},${data.person_lng}`;

  return (
    <main className="h-dvh w-screen bg-void flex flex-col">
      {/* Header */}
      <div className="flex-none px-6 pt-[env(safe-area-inset-top,20px)] pb-4 border-b border-void-border">
        <div className="flex items-center justify-between">
          <span className="font-mono text-[10px] tracking-[3px] text-white/20 uppercase">
            ShieldHer
          </span>
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-danger animate-dot-pulse" />
            <span className="font-mono text-[10px] text-danger/70 tracking-wider">
              LIVE
            </span>
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 flex flex-col items-center justify-center gap-8 px-6">
        {/* Status */}
        <div className="text-center space-y-2">
          <p className="font-display text-4xl text-danger tracking-[5px]">
            ACTIVE SOS
          </p>
          <p className="font-mono text-[11px] text-white/30 tracking-wider">
            Someone needs help nearby
          </p>
        </div>

        {/* Shield info */}
        <div className="w-full max-w-xs space-y-4">
          <div className="flex items-center justify-between py-3 border-b border-void-border">
            <span className="font-mono text-[10px] text-white/30 tracking-wider uppercase">
              Shields responding
            </span>
            <span className="font-mono text-sm text-shield font-semibold">
              {shieldCount}
            </span>
          </div>

          {nearestEta < Infinity && (
            <div className="flex items-center justify-between py-3 border-b border-void-border">
              <span className="font-mono text-[10px] text-white/30 tracking-wider uppercase">
                Nearest ETA
              </span>
              <span className="font-mono text-sm text-amber font-semibold">
                {Math.ceil(nearestEta / 60)} min
              </span>
            </div>
          )}

          {data.convergence_lat && data.convergence_lng && (
            <div className="flex items-center justify-between py-3 border-b border-void-border">
              <span className="font-mono text-[10px] text-white/30 tracking-wider uppercase">
                Meet point
              </span>
              <span className="font-mono text-[11px] text-white/50">
                {data.convergence_lat.toFixed(4)},{" "}
                {data.convergence_lng.toFixed(4)}
              </span>
            </div>
          )}
        </div>

        {/* Open in maps */}
        <a
          href={mapsUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center gap-2 px-5 py-3 rounded-full border border-danger/30 text-danger font-mono text-[11px] tracking-wider hover:bg-danger/10 transition-colors"
        >
          <svg
            className="w-4 h-4"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z" />
            <circle cx="12" cy="10" r="3" />
          </svg>
          OPEN IN MAPS
        </a>

        {/* Triggered time */}
        <p className="font-mono text-[9px] text-white/15 tracking-wider">
          TRIGGERED{" "}
          {new Date(data.triggered_at).toLocaleTimeString([], {
            hour: "2-digit",
            minute: "2-digit",
          })}
        </p>
      </div>
    </main>
  );
}
