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
    let cancelled = false;
    const base =
      process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:8000";
    const ws = new WebSocket(
      `${base}/api/v1/track/${params.token}/live`,
    );

    ws.onopen = () => {
      if (cancelled) ws.close();
    };

    ws.onmessage = (e) => {
      if (e.data === "pong") return;
      try {
        const msg = JSON.parse(e.data);
        if (msg.type === "incident_resolved") {
          setData((prev) =>
            prev
              ? { ...prev, status: "resolved", resolved_at: msg.resolved_at }
              : prev,
          );
        }
        if (msg.type === "shield_location") {
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
        ws.send("ping");
    }, 25_000);

    return () => {
      cancelled = true;
      clearInterval(ping);
      if (ws.readyState === WebSocket.OPEN) ws.close();
    };
  }, [params.token]);

  /* ── Error state ───────────────────────────────────────────────────── */

  if (error) {
    return (
      <main className="h-dvh w-screen bg-bg flex items-center justify-center px-6">
        <div className="text-left space-y-3">
          <h2 className="font-display text-3xl text-plum tracking-[-0.02em]">
            Link Expired
          </h2>
          <p className="font-body text-[13px] text-warm-muted tracking-wide max-w-xs">
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
      <main className="h-dvh w-screen bg-bg flex items-center justify-center">
        <div className="flex items-center gap-3">
          <span className="w-2 h-2 rounded-full bg-coral animate-dot-pulse" />
          <span className="font-body text-[12px] text-warm-muted tracking-wide">
            Loading tracking data...
          </span>
        </div>
      </main>
    );
  }

  /* ── Resolved state ────────────────────────────────────────────────── */

  if (data.status === "resolved") {
    return (
      <main className="h-dvh w-screen bg-bg flex items-center justify-center px-6">
        <div className="text-left space-y-4">
          <div className="w-16 h-16 rounded-full bg-sage-light border border-sage flex items-center justify-center">
            <svg
              className="w-7 h-7 text-plum"
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
          <h2 className="font-display text-2xl text-plum tracking-[-0.02em]">
            Incident Resolved
          </h2>
          <p className="font-body text-[12px] text-warm-muted tracking-wide">
            The person has confirmed they are{" "}
            <span className="font-display italic font-light text-coral">safe</span>.
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
    <main className="h-dvh w-screen bg-bg flex flex-col">
      {/* Blob backgrounds */}
      <div className="fixed inset-0 z-0 pointer-events-none overflow-hidden">
        <div className="absolute w-[600px] h-[600px] -top-[200px] -left-[200px] bg-[radial-gradient(circle,rgba(232,99,74,0.08)_0%,transparent_70%)] rounded-full blur-[40px] animate-drift-slow" />
        <div className="absolute w-[400px] h-[400px] top-[40%] left-[35%] bg-[radial-gradient(circle,rgba(232,223,245,0.35)_0%,transparent_70%)] rounded-full blur-[60px] animate-drift-slower" />
      </div>

      {/* Header */}
      <div className="relative z-10 flex-none px-6 pt-[env(safe-area-inset-top,20px)] pb-4 border-b border-lavender-muted">
        <div className="flex items-center justify-between">
          <span className="font-display text-[14px] tracking-[-0.01em] text-plum font-semibold">
            ShieldHer
          </span>
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-coral animate-dot-pulse" />
            <span className="font-body text-[10px] text-coral tracking-[0.12em] font-semibold uppercase">
              Live
            </span>
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="relative z-10 flex-1 flex flex-col items-start justify-center gap-8 px-6">
        {/* Status */}
        <div className="text-left space-y-2">
          <h1 className="font-display text-4xl text-plum tracking-[-0.02em]">
            Active SOS
          </h1>
          <p className="font-body text-[13px] text-warm-muted tracking-wide">
            Someone needs help nearby
          </p>
        </div>

        {/* Shield info */}
        <div className="w-full max-w-xs space-y-4">
          <div className="flex items-center justify-between py-3 border-b border-lavender-muted">
            <span className="font-body text-[11px] text-warm-muted tracking-[0.08em] font-medium uppercase">
              Shields responding
            </span>
            <span className="font-display text-sm text-plum font-semibold">
              {shieldCount}
            </span>
          </div>

          {nearestEta < Infinity && (
            <div className="flex items-center justify-between py-3 border-b border-lavender-muted">
              <span className="font-body text-[11px] text-warm-muted tracking-[0.08em] font-medium uppercase">
                Nearest ETA
              </span>
              <span className="font-display text-sm text-coral font-semibold">
                {Math.ceil(nearestEta / 60)} min
              </span>
            </div>
          )}

          {data.convergence_lat && data.convergence_lng && (
            <div className="flex items-center justify-between py-3 border-b border-lavender-muted">
              <span className="font-body text-[11px] text-warm-muted tracking-[0.08em] font-medium uppercase">
                Meet point
              </span>
              <span className="font-body text-[12px] text-warm-black/60">
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
          className="btn-secondary flex items-center gap-2 !px-5 !py-3 !text-[12px] !tracking-[0.06em]"
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
          Open in Maps
        </a>

        {/* Triggered time */}
        <p className="font-body text-[10px] text-warm-muted/40 tracking-[0.08em] uppercase">
          Triggered{" "}
          {new Date(data.triggered_at).toLocaleTimeString([], {
            hour: "2-digit",
            minute: "2-digit",
          })}
        </p>
      </div>
    </main>
  );
}
