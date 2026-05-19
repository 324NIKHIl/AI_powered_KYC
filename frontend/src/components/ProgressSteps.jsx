import { motion } from 'framer-motion'

const STEPS = [
  { id: 1, label: 'Upload Document', icon: '📄' },
  { id: 2, label: 'OCR Preview',     icon: '🔍' },
  { id: 3, label: 'Face Capture',    icon: '📸' },
  { id: 4, label: 'Processing',      icon: '⚙️'  },
  { id: 5, label: 'Result',          icon: '✅' },
]

export default function ProgressSteps({ currentStep }) {
  return (
    <div className="w-full">
      <div className="flex items-center justify-between relative">
        {/* Connector line */}
        <div className="absolute top-5 left-0 right-0 h-px bg-white/10 z-0" />
        <motion.div
          className="absolute top-5 left-0 h-px bg-gradient-to-r from-primary to-accent z-0"
          initial={{ width: '0%' }}
          animate={{ width: `${((currentStep - 1) / (STEPS.length - 1)) * 100}%` }}
          transition={{ duration: 0.5, ease: 'easeInOut' }}
        />

        {STEPS.map((step) => {
          const done    = step.id < currentStep
          const active  = step.id === currentStep
          const pending = step.id > currentStep

          return (
            <div key={step.id} className="flex flex-col items-center gap-2 z-10">
              <motion.div
                className={`
                  w-10 h-10 rounded-full flex items-center justify-center text-sm font-bold
                  border-2 transition-all duration-300
                  ${done    ? 'bg-primary/20 border-primary text-primary'       : ''}
                  ${active  ? 'bg-primary border-primary text-surface-900 shadow-glow' : ''}
                  ${pending ? 'bg-surface-700 border-white/10 text-white/30'    : ''}
                `}
                animate={active ? { scale: [1, 1.05, 1] } : {}}
                transition={{ repeat: Infinity, duration: 2 }}
              >
                {done ? (
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth="2.5" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                  </svg>
                ) : (
                  <span>{step.icon}</span>
                )}
              </motion.div>
              <span className={`text-xs font-medium hidden sm:block ${active ? 'text-primary' : pending ? 'text-white/30' : 'text-white/60'}`}>
                {step.label}
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}
