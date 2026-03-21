import { Routes, Route, Navigate } from 'react-router-dom'
import { LandingPage } from './pages/LandingPage'
import { ChatApp } from './pages/ChatApp'

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<LandingPage />} />
      <Route path="/app/*" element={<ChatApp />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
