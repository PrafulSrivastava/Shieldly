"use client";

import { useEffect, useRef, useCallback } from "react";
import { useStore } from "@/lib/store";
import { api } from "@/lib/api";

const POLL_MS = 5_000;
const LOCATION_PUSH_MS = 8_000;

export function useIncidentPolling(incidentId: string | null) {
  const { setLiveShields, setLiveConvergence, setPhase, setIncident } =
    useStore();
  const intervalRef = useRef<ReturnType<typeof setInterval>>();

  const poll = useCallback(async () => {
    if (!incidentId) return;
    try {
      const detail = await api.getIncident(incidentId);

      setLiveShields(detail.shields);

      if (detail.convergence_point) {
        setLiveConvergence(detail.convergence_point);
      }

      if (detail.status === "resolved") {
        setPhase("resolved");
        setTimeout(() => {
          setPhase("idle");
          setIncident(null);
        }, 3_000);
      }
    } catch {
      /* network hiccup — retry on next tick */
    }
  }, [incidentId, setLiveShields, setLiveConvergence, setPhase, setIncident]);

  useEffect(() => {
    if (!incidentId) return;

    poll();
    intervalRef.current = setInterval(poll, POLL_MS);
    return () => clearInterval(intervalRef.current);
  }, [incidentId, poll]);
}

export function useLocationPush(
  incidentId: string | null,
  position: { lat: number; lng: number } | null,
) {
  useEffect(() => {
    if (!incidentId || !position) return;

    const push = () => {
      api
        .updatePersonLocation(incidentId, position.lat, position.lng)
        .catch(() => {});
    };

    push();
    const id = setInterval(push, LOCATION_PUSH_MS);
    return () => clearInterval(id);
  }, [incidentId, position]);
}
