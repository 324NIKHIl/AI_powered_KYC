import { motion } from 'framer-motion'

const OK   = { cls: 'badge-approved', icon: '✓', pulse: '#10B981' }
const BAD  = { cls: 'badge-rejected', icon: '✗', pulse: '#EF4444' }
const WARN = { cls: 'badge-pending',  icon: '⚠', pulse: '#F59E0B' }

export const STATUS_CONFIG = {
  VERIFIED: OK, VALID: OK, APPROVED: OK,
  REJECTED: BAD, INVALID: BAD, SUSPICIOUS: BAD,
  VERIFICATION_UNAVAILABLE: WARN, MANUAL_REVIEW_REQUIRED: WARN,
  PENDING: { ...WARN, icon: '⏳' },
}

export default function StatusBadge({ status, large = false }) {
  const key = status?.toUpperCase()
  const cfg = STATUS_CONFIG[key] || STATUS_CONFIG.PENDING
  const label = (status || 'PENDING').replace(/_/g, ' ')

  return (
    <motion.div
      className={`inline-flex items-center gap-2 ${cfg.cls} ${large ? 'text-base px-5 py-2' : ''}`}
      initial={{ opacity: 0, scale: 0.8 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ type: 'spring', stiffness: 400 }}
    >
      <span className="relative flex h-2 w-2">
        <span
          className="animate-ping absolute inline-flex h-full w-full rounded-full opacity-75"
          style={{ backgroundColor: cfg.pulse }}
        />
        <span className="relative inline-flex rounded-full h-2 w-2" style={{ backgroundColor: cfg.pulse }} />
      </span>
      <span>{cfg.icon}</span>
      <span>{label}</span>
    </motion.div>
  )
}
