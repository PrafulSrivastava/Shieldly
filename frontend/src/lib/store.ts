import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { ConvergencePoint, ShieldStatusInfo, LatLng } from "./types";

export type AppPhase = "idle" | "active" | "resolved";

interface IncidentState {
  id: string;
  trackingToken: string;
  convergencePoint: ConvergencePoint | null;
  shieldsNotified: number;
  trackingUrl: string;
}

interface AppState {
  token: string | null;
  userId: string | null;
  role: "person" | "shield" | null;
  phone: string | null;
  adminKey: string;

  phase: AppPhase;
  incident: IncidentState | null;
  mapExpanded: boolean;

  liveShields: ShieldStatusInfo[];
  liveConvergence: ConvergencePoint | null;
  livePersonPos: LatLng | null;

  setAuth: (
    token: string,
    userId: string,
    role: "person" | "shield",
    phone: string,
  ) => void;
  clearAuth: () => void;
  setAdminKey: (key: string) => void;
  setPhase: (phase: AppPhase) => void;
  setIncident: (incident: IncidentState | null) => void;
  setMapExpanded: (expanded: boolean) => void;
  setLiveShields: (shields: ShieldStatusInfo[]) => void;
  setLiveConvergence: (point: ConvergencePoint | null) => void;
  setLivePersonPos: (pos: LatLng | null) => void;
  patchLiveShield: (
    shieldId: string,
    lat: number,
    lng: number,
  ) => void;
}

export const useStore = create<AppState>()(
  persist(
    (set) => ({
      token: null,
      userId: null,
      role: null,
      phone: null,
      adminKey: "",

      phase: "idle",
      incident: null,
      mapExpanded: false,

      liveShields: [],
      liveConvergence: null,
      livePersonPos: null,

      setAuth: (token, userId, role, phone) =>
        set({ token, userId, role, phone }),
      clearAuth: () =>
        set({ token: null, userId: null, role: null, phone: null }),
      setAdminKey: (key) => set({ adminKey: key }),
      setPhase: (phase) => set({ phase }),
      setIncident: (incident) => set({ incident }),
      setMapExpanded: (expanded) => set({ mapExpanded: expanded }),
      setLiveShields: (shields) => set({ liveShields: shields }),
      setLiveConvergence: (point) => set({ liveConvergence: point }),
      setLivePersonPos: (pos) => set({ livePersonPos: pos }),
      patchLiveShield: (shieldId, lat, lng) =>
        set((s) => ({
          liveShields: s.liveShields.map((sh) =>
            sh.shield_id === shieldId ? { ...sh, lat, lng } : sh,
          ),
        })),
    }),
    {
      name: "shieldher-store",
      partialize: (state) => ({
        token: state.token,
        userId: state.userId,
        role: state.role,
        phone: state.phone,
        adminKey: state.adminKey,
      }),
    },
  ),
);
