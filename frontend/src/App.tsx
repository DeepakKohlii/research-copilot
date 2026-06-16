import { BrowserRouter, Link, Route, Routes } from 'react-router-dom'
import { HomePage } from './pages/HomePage'
import { SessionPage } from './pages/SessionPage'

function BrandMark() {
  return (
    <span className="brand-mark" aria-hidden="true">
      <svg viewBox="0 0 24 24" width="18" height="18" fill="none">
        <rect x="4" y="3" width="16" height="18" rx="3" fill="currentColor" opacity="0.18" />
        <rect x="7" y="7" width="7" height="1.6" rx="0.8" fill="currentColor" />
        <rect x="7" y="11" width="10" height="1.6" rx="0.8" fill="currentColor" />
        <rect x="7" y="15" width="6" height="1.6" rx="0.8" fill="currentColor" />
      </svg>
    </span>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <div className="shell">
        <header className="topbar">
          <div className="topbar-inner">
            <Link to="/" className="brand">
              <BrandMark />
              <span className="wordmark">
                Briefing Desk<span className="dot">.</span>
              </span>
            </Link>
            <nav className="topnav">
              <span className="tagline">Meeting prep, automated</span>
              <Link to="/" className="btn btn-sm btn-primary">
                New briefing
              </Link>
            </nav>
          </div>
        </header>
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/sessions/:id" element={<SessionPage />} />
        </Routes>
      </div>
    </BrowserRouter>
  )
}
