import { create } from 'zustand'
import { persist } from 'zustand/middleware'

interface AppState {
  token: string | null
  userId: string | null
  role: 'person' | 'shield' | null
  phone: string | null
  adminKey: string
  incidentId: string | null
  setAuth: (token: string, userId: string, role: 'person' | 'shield', phone: string) => void
  clearAuth: () => void
  setAdminKey: (key: string) => void
  setIncidentId: (id: string | null) => void
}

export const useStore = create<AppState>()(
  persist(
    (set) => ({
      token: null,
      userId: null,
      role: null,
      phone: null,
      adminKey: 'dev-admin-key-change-in-prod',
      incidentId: null,
      setAuth: (token, userId, role, phone) =>
        set({ token, userId, role, phone }),
      clearAuth: () =>
        set({ token: null, userId: null, role: null, phone: null }),
      setAdminKey: (key) => set({ adminKey: key }),
      setIncidentId: (id) => set({ incidentId: id }),
    }),
    { name: 'shieldly-store' }
  )
)
