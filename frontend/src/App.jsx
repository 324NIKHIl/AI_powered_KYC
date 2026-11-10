import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { VerificationProvider } from './context/VerificationContext'
import Navbar from './components/Navbar'
import LandingPage from './pages/LandingPage'
import VerificationPage from './pages/VerificationPage'
import ResultPage from './pages/ResultPage'
import AdminDashboard from './pages/AdminDashboard'
import AdminLogin from './pages/AdminLogin'
import CompletionPage from './pages/CompletionPage'

function AdminOnly({ children }) {
  return sessionStorage.getItem('adminToken') ? children : <Navigate to="/admin/login" replace />
}

export default function App() {
  return (
    <BrowserRouter>
      <VerificationProvider>
        {/* Ambient scanline effect */}
        <div className="scanline" />

        <Navbar />

        <main className="min-h-screen">
          <Routes>
            <Route path="/"          element={<LandingPage />} />
            <Route path="/verify"    element={<VerificationPage />} />
            <Route path="/complete" element={<CompletionPage />} />
            <Route path="/admin/login" element={<AdminLogin />} />
            <Route path="/admin" element={<AdminOnly><AdminDashboard /></AdminOnly>} />
            <Route path="/result/:sessionId" element={<AdminOnly><ResultPage /></AdminOnly>} />
            <Route path="*"          element={<Navigate to="/" replace />} />
          </Routes>
        </main>
      </VerificationProvider>
    </BrowserRouter>
  )
}
