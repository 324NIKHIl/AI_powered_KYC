import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { VerificationProvider } from './context/VerificationContext'
import Navbar from './components/Navbar'
import LandingPage from './pages/LandingPage'
import VerificationPage from './pages/VerificationPage'
import ResultPage from './pages/ResultPage'
import AdminDashboard from './pages/AdminDashboard'

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
            <Route path="/result/:sessionId" element={<ResultPage />} />
            <Route path="/admin"     element={<AdminDashboard />} />
            <Route path="*"          element={<Navigate to="/" replace />} />
          </Routes>
        </main>
      </VerificationProvider>
    </BrowserRouter>
  )
}
