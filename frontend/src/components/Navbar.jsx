import { Link, useLocation } from 'react-router-dom'
import { motion } from 'framer-motion'

const links = [
  { to: '/',       label: 'Home'      },
  { to: '/verify', label: 'Verify'    },
  { to: '/admin',  label: 'Dashboard' },
]

export default function Navbar() {
  const { pathname } = useLocation()

  return (
    <nav className="sticky top-0 z-50 border-b border-white/5 bg-surface-900/80 backdrop-blur-xl">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
        {/* Logo */}
        <Link to="/" className="flex items-center gap-3 group">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-primary to-accent flex items-center justify-center shadow-glow group-hover:shadow-glow-lg transition-shadow">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" className="text-surface-900">
              <path d="M12 2L2 7l10 5 10-5-10-5z" />
              <path d="M2 17l10 5 10-5" />
              <path d="M2 12l10 5 10-5" />
            </svg>
          </div>
          <span className="font-bold text-lg tracking-tight">
            <span className="gradient-text">AI</span>
            <span className="text-white"> KYC</span>
          </span>
        </Link>

        {/* Nav links */}
        <div className="flex items-center gap-1">
          {links.map(({ to, label }) => {
            const active = pathname === to
            return (
              <Link key={to} to={to} className="relative px-4 py-2 rounded-lg text-sm font-medium transition-colors hover:text-primary">
                <span className={active ? 'text-primary' : 'text-white/60'}>{label}</span>
                {active && (
                  <motion.div
                    layoutId="nav-indicator"
                    className="absolute inset-0 rounded-lg bg-primary/10 border border-primary/30"
                    transition={{ type: 'spring', stiffness: 400, damping: 30 }}
                  />
                )}
              </Link>
            )
          })}
        </div>

        {/* CTA */}
        <Link to="/verify" className="btn-primary text-sm px-4 py-2 hidden sm:flex">
          Start Verification
        </Link>
      </div>
    </nav>
  )
}
