"use client";

import { useState, useEffect, useCallback } from "react";

interface OrientationState {
  heading: number | null;
  permissionGranted: boolean;
}

export function useDeviceOrientation() {
  const [state, setState] = useState<OrientationState>({
    heading: null,
    permissionGranted: false,
  });

  const requestPermission = useCallback(async () => {
    const DOE = DeviceOrientationEvent as unknown as {
      requestPermission?: () => Promise<"granted" | "denied">;
    };

    if (typeof DOE.requestPermission === "function") {
      try {
        const perm = await DOE.requestPermission();
        setState((s) => ({ ...s, permissionGranted: perm === "granted" }));
        return perm === "granted";
      } catch {
        return false;
      }
    }

    setState((s) => ({ ...s, permissionGranted: true }));
    return true;
  }, []);

  useEffect(() => {
    const handler = (e: DeviceOrientationEvent) => {
      const h =
        (e as DeviceOrientationEvent & { webkitCompassHeading?: number })
          .webkitCompassHeading ?? (e.alpha != null ? 360 - e.alpha : null);

      if (h != null) {
        setState((s) => ({ ...s, heading: h }));
      }
    };

    window.addEventListener("deviceorientation", handler, true);
    return () => window.removeEventListener("deviceorientation", handler, true);
  }, []);

  return { ...state, requestPermission };
}
