import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import './i18n'
import App from './App'
import './styles/globals.css'
import './styles/auth.css'
import './styles/chat.css'
import './styles/documents.css'
import './styles/admin.css'
import 'driver.js/dist/driver.css'
import './styles/tour.css'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </StrictMode>,
)
