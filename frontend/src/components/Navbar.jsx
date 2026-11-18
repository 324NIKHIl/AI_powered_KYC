import { Link, useLocation } from 'react-router-dom'
import { motion } from 'framer-motion'

const links = [
  { to: '/',       label: 'Home'      },
  { to: '/verify', label: 'Verify'    },
  { to: '/admin/login', label: 'Admin' },
]

export default function Navbar() {
  const { pathname } = useLocation()

  return (
    <nav className="sticky top-0 z-50 border-b border-slate-200/80 bg-white/90 backdrop-blur-xl">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-[72px] flex items-center justify-between">
        {/* Logo */}
        <Link to="/" className="flex items-center gap-3 group">
          <svg aria-hidden="true" viewBox="0 0 48 48" className="h-10 w-10 shrink-0 transition-transform duration-200 group-hover:scale-[1.04]">
            <defs>
              <linearGradient id="veriqo-mark" x1="5" y1="8" x2="42" y2="39" gradientUnits="userSpaceOnUse">
                <stop stopColor="#14B8A6" />
                <stop offset=".52" stopColor="#0EA5E9" />
                <stop offset="1" stopColor="#6D4AFF" />
              </linearGradient>
            </defs>
            <path d="M5 7h9.3l9.4 22L33 7h9.4L27 41h-7.1L5 7Z" fill="url(#veriqo-mark)" />
            <path d="M11 34C16 19 28 8.5 37 10.5c7.6 1.7 5.5 9.2-1.2 15.8-6.2 6.1-17.5 12.4-23.2 10.2-2.7-1-3.2-3.5-1.6-7" fill="none" stroke="url(#veriqo-mark)" strokeWidth="2.2" strokeLinecap="round" />
          </svg>
          <span className="text-[1.25rem] font-extrabold tracking-[-.055em] text-slate-900">
            VER<span className="text-sky-500">I</span><span className="bg-gradient-to-r from-sky-500 to-violet-600 bg-clip-text text-transparent">QO</span>
          </span>
        </Link>

        {/* Nav links */}
        <div className="flex items-center gap-1">
          {links.map(({ to, label }) => {
            const active = to === '/admin/login' ? pathname.startsWith('/admin') : pathname === to
            return (
              <Link key={to} to={to} className={`relative px-4 py-2 rounded-lg text-sm font-medium transition-colors hover:text-primary ${active ? 'text-primary' : 'text-slate-500'}`}>
                <span className="relative z-10">{label}</span>
                {active && (
                  <motion.div
                    layoutId="nav-indicator"
                    className="absolute inset-0 rounded-lg bg-primary/5 border border-primary/15"
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
