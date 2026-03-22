"use client";

import { useState, useEffect, useCallback } from "react";
import type { LatLng } from "@/lib/types";

interface GeolocationState {
  position: LatLng | null;
  error: string | null;
  requesting: boolean;
}

export function useGeolocation(enableHighAccuracy = true) {
  const [state, setState] = useState<GeolocationState>({
    position: null,
    error: null,
    requesting: false,
  });

  const request = useCallback(() => {
    if (!navigator.geolocation) {
      setState((s) => ({ ...s, error: "Geolocation not supported" }));
      return;
    }

    setState((s) => ({ ...s, requesting: true }));

    navigator.geolocation.getCurrentPosition(
      (pos) =>
        setState({
          position: { lat: pos.coords.latitude, lng: pos.coords.longitude },
          error: null,
          requesting: false,
        }),
      (err) =>
        setState((s) => ({
          ...s,
          error: err.message,
          requesting: false,
        })),
      { enableHighAccuracy, timeout: 10_000, maximumAge: 5_000 },
    );
  }, [enableHighAccuracy]);

  useEffect(() => {
    request();

    if (!navigator.geolocation) return;

    const watchId = navigator.geolocation.watchPosition(
      (pos) =>
        setState({
          position: { lat: pos.coords.latitude, lng: pos.coords.longitude },
          error: null,
          requesting: false,
        }),
      (err) =>
        setState((s) => ({ ...s, error: err.message, requesting: false })),
      { enableHighAccuracy, timeout: 15_000, maximumAge: 3_000 },
    );

    return () => navigator.geolocation.clearWatch(watchId);
  }, [enableHighAccuracy, request]);

  return state;
}
