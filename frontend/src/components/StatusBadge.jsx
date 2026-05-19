import { motion } from 'framer-motion'

const CONFIGS = {
  APPROVED: { cls: 'badge-approved', icon: '✓', pulse: '#10B981' },
  REJECTED: { cls: 'badge-rejected', icon: '✗', pulse: '#EF4444' },
  PENDING:  { cls: 'badge-pending',  icon: '⏳', pulse: '#F59E0B' },
}

export default function StatusBadge({ status, large = false }) {
  const cfg = CONFIGS[status?.toUpperCase()] || CONFIGS.PENDING

  return (
    <motion.div
      className={`inline-flex items-center gap-2 ${cfg.cls} ${large ? 'text-base px-5 py-2' : ''}`}
      initial={{ opacity: 0, scale: 0.8 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ type: 'spring', stiffness: 400 }}
    >
      {/* Pulsing dot */}
      <span className="relative flex h-2 w-2">
        <span
          className="animate-ping absolute inline-flex h-full w-full rounded-full opacity-75"
          style={{ backgroundColor: cfg.pulse }}
        />
        <span className="relative inline-flex rounded-full h-2 w-2" style={{ backgroundColor: cfg.pulse }} />
      </span>
      <span>{cfg.icon}</span>
      <span>{status}</span>
    </motion.div>
  )
}
