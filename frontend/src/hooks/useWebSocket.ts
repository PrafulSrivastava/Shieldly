"use client";

import { useEffect, useRef, useCallback } from "react";
import { useStore } from "@/lib/store";
import type { WSIncoming } from "@/lib/types";

const WS_BASE =
  typeof window !== "undefined"
    ? (process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:8000")
    : "";

const MAX_RETRY_MS = 30_000;
const BASE_RETRY_MS = 1_000;

export function useWebSocket(trackingToken: string | null) {
  const wsRef = useRef<WebSocket | null>(null);
  const retryCount = useRef(0);
  const retryTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pingTimer = useRef<ReturnType<typeof setInterval> | null>(null);
  const cancelled = useRef(false);

  const { patchLiveShield, setLiveConvergence, setLivePersonPos, setPhase } =
    useStore();

  const connect = useCallback(() => {
    if (cancelled.current || !trackingToken) return;

    const url = `${WS_BASE}/api/v1/track/${trackingToken}/live`;
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      if (cancelled.current) {
        ws.close();
        return;
      }
      retryCount.current = 0;

      pingTimer.current = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send("ping");
        }
      }, 25_000);
    };

    ws.onmessage = (event) => {
      const raw: string = event.data;
      if (raw === "pong") return;

      try {
        const msg: WSIncoming = JSON.parse(raw);

        switch (msg.type) {
          case "shield_location":
            patchLiveShield(msg.shield_id, msg.lat, msg.lng);
            break;
          case "person_location":
            setLivePersonPos({ lat: msg.lat, lng: msg.lng });
            break;
          case "convergence_update":
            setLiveConvergence({ lat: msg.lat, lng: msg.lng });
            break;
          case "incident_resolved":
            setPhase("resolved");
            break;
          case "pong":
            break;
        }
      } catch {
        /* ignore malformed frames */
      }
    };

    ws.onclose = () => {
      if (pingTimer.current) clearInterval(pingTimer.current);
      if (cancelled.current) return;

      const delay = Math.min(
        BASE_RETRY_MS * 2 ** retryCount.current,
        MAX_RETRY_MS,
      );
      retryCount.current += 1;
      retryTimer.current = setTimeout(connect, delay);
    };

    ws.onerror = () => {
      // onclose always fires after onerror — reconnect handled there
    };
  }, [
    trackingToken,
    patchLiveShield,
    setLiveConvergence,
    setLivePersonPos,
    setPhase,
  ]);

  useEffect(() => {
    if (!trackingToken) return;

    cancelled.current = false;
    retryCount.current = 0;
    connect();

    return () => {
      cancelled.current = true;
      if (retryTimer.current) clearTimeout(retryTimer.current);
      if (pingTimer.current) clearInterval(pingTimer.current);
      if (
        wsRef.current &&
        wsRef.current.readyState !== WebSocket.CLOSED
      ) {
        wsRef.current.close();
      }
      wsRef.current = null;
    };
  }, [trackingToken, connect]);
}
