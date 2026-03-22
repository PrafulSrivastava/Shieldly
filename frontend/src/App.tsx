import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import SOSLanding from './pages/SOSLanding'
import MapDashboard from './pages/MapDashboard'
import ShieldDashboard from './pages/ShieldDashboard'
import AdminDashboard from './pages/AdminDashboard'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<SOSLanding />} />
        <Route path="/dashboard" element={<MapDashboard />} />
        <Route path="/shield" element={<ShieldDashboard />} />
        <Route path="/admin" element={<AdminDashboard />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
