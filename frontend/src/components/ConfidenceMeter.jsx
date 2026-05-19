import { motion } from 'framer-motion'

/**
 * Animated arc-gauge confidence meter.
 * score: 0.0 – 1.0
 */
export default function ConfidenceMeter({ score = 0, label = 'Confidence', size = 160 }) {
  const pct   = Math.max(0, Math.min(1, score))
  const deg   = pct * 270  // arc spans 270 degrees (-135 to +135)
  const color = pct >= 0.75 ? '#10B981' : pct >= 0.50 ? '#F59E0B' : '#EF4444'
  const r     = (size / 2) - 12
  const cx    = size / 2
  const cy    = size / 2
  const circumference = 2 * Math.PI * r
  const arcLength     = circumference * (270 / 360)
  const dashOffset    = arcLength * (1 - pct)

  return (
    <div className="flex flex-col items-center gap-2">
      <div className="relative" style={{ width: size, height: size }}>
        <svg width={size} height={size} style={{ transform: 'rotate(135deg)' }}>
          {/* Background track */}
          <circle
            cx={cx} cy={cy} r={r}
            fill="none"
            stroke="rgba(255,255,255,0.05)"
            strokeWidth={10}
            strokeDasharray={`${arcLength} ${circumference - arcLength}`}
            strokeLinecap="round"
          />
          {/* Animated foreground arc */}
          <motion.circle
            cx={cx} cy={cy} r={r}
            fill="none"
            stroke={color}
            strokeWidth={10}
            strokeDasharray={`${arcLength} ${circumference - arcLength}`}
            strokeLinecap="round"
            initial={{ strokeDashoffset: arcLength }}
            animate={{ strokeDashoffset: dashOffset }}
            transition={{ duration: 1.2, ease: 'easeOut' }}
            style={{ filter: `drop-shadow(0 0 6px ${color})` }}
          />
        </svg>

        {/* Center text */}
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <motion.span
            className="text-2xl font-bold"
            style={{ color }}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.5 }}
          >
            {Math.round(pct * 100)}%
          </motion.span>
          <span className="text-xs text-white/40 mt-0.5">{label}</span>
        </div>
      </div>
    </div>
  )
}
