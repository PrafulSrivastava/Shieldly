"use client";

import { useEffect, useRef } from "react";
import { useStore } from "@/lib/store";
import type { WSIncoming } from "@/lib/types";

const WS_BASE =
  typeof window !== "undefined"
    ? (process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:8000")
    : "";

export function useWebSocket(trackingToken: string | null) {
  const wsRef = useRef<WebSocket | null>(null);
  const { patchLiveShield, setLiveConvergence, setLivePersonPos, setPhase } =
    useStore();

  useEffect(() => {
    if (!trackingToken) return;

    const url = `${WS_BASE}/api/v1/track/${trackingToken}/live`;
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onmessage = (event) => {
      try {
        const msg: WSIncoming = JSON.parse(event.data);

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

    const ping = setInterval(() => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: "ping" }));
      }
    }, 25_000);

    return () => {
      clearInterval(ping);
      ws.close();
      wsRef.current = null;
    };
  }, [
    trackingToken,
    patchLiveShield,
    setLiveConvergence,
    setLivePersonPos,
    setPhase,
  ]);
}
