import { motion } from 'framer-motion'

const STEPS = [
  { id: 1, label: 'Your Details', icon: 'user' },
  { id: 2, label: 'Upload Document', icon: 'document' },
  { id: 3, label: 'OCR Preview', icon: 'scan' },
  { id: 4, label: 'Face Capture', icon: 'camera' },
  { id: 5, label: 'Processing', icon: 'settings' },
  { id: 6, label: 'Result', icon: 'result' },
]

function StepIcon({ name, className = 'h-[18px] w-[18px]' }) {
  const common = {
    className,
    viewBox: '0 0 24 24',
    fill: 'none',
    stroke: 'currentColor',
    strokeWidth: 1.7,
    strokeLinecap: 'round',
    strokeLinejoin: 'round',
    'aria-hidden': true,
  }

  const paths = {
    user: <><circle cx="12" cy="8" r="3.25" /><path d="M5.5 19a6.5 6.5 0 0 1 13 0" /></>,
    document: <><path d="M7 3.75h7l4 4V20a.75.75 0 0 1-.75.75h-10.5A.75.75 0 0 1 6 20V4.75A1 1 0 0 1 7 3.75Z" /><path d="M14 4v4h4M9 13h6M9 16.5h6" /></>,
    scan: <><path d="M8 4.5H5.5v3M16 4.5h2.5v3M8 19.5H5.5v-3M16 19.5h2.5v-3" /><circle cx="11" cy="11" r="4.25" /><path d="m14.25 14.25 3.25 3.25" /></>,
    camera: <><path d="M4.75 8A1.75 1.75 0 0 1 6.5 6.25h2l1.1-1.5h4.8l1.1 1.5h2A1.75 1.75 0 0 1 19.25 8v9.25A1.75 1.75 0 0 1 17.5 19h-11a1.75 1.75 0 0 1-1.75-1.75Z" /><circle cx="12" cy="12.5" r="3.25" /></>,
    settings: <><path d="M12 3.75v2M12 18.25v2M20.25 12h-2M5.75 12h-2M17.83 6.17l-1.42 1.42M7.59 16.41l-1.42 1.42M17.83 17.83l-1.42-1.42M7.59 7.59 6.17 6.17" /><circle cx="12" cy="12" r="5.25" /><circle cx="12" cy="12" r="1.5" /></>,
    result: <><path d="M7 3.75h7l4 4V20a.75.75 0 0 1-.75.75h-10.5A.75.75 0 0 1 6 20V4.75A1 1 0 0 1 7 3.75Z" /><path d="M14 4v4h4m-9 5 2 2 4-4" /></>,
    check: <path d="m5 12.5 4.25 4.25L19 7" />,
  }

  return <svg {...common}>{paths[name]}</svg>
}

export default function ProgressSteps({ currentStep }) {
  return (
    <div className="w-full" aria-label="Verification progress">
      <div className="relative flex items-center justify-between">
        <div className="absolute left-0 right-0 top-5 z-0 h-px bg-slate-200" />
        <motion.div
          className="absolute left-0 top-5 z-0 h-px bg-primary"
          initial={{ width: '0%' }}
          animate={{ width: `${((currentStep - 1) / (STEPS.length - 1)) * 100}%` }}
          transition={{ duration: 0.45, ease: 'easeInOut' }}
        />

        {STEPS.map((step) => {
          const done = step.id < currentStep
          const active = step.id === currentStep
          const pending = step.id > currentStep

          return (
            <div key={step.id} className="z-10 flex flex-col items-center gap-2">
              <motion.div
                aria-current={active ? 'step' : undefined}
                className={`flex h-10 w-10 items-center justify-center rounded-full border transition-colors duration-200 ${
                  done ? 'border-teal-200 bg-teal-50 text-primary' :
                  active ? '!border-primary !bg-primary !text-white shadow-glow' :
                  'border-slate-200 bg-white text-slate-400'
                }`}
                animate={active ? { scale: [1, 1.04, 1] } : { scale: 1 }}
                transition={active ? { repeat: Infinity, duration: 2 } : { duration: 0.2 }}
              >
                <StepIcon name={done ? 'check' : step.icon} />
              </motion.div>
              <span className={`hidden text-xs font-medium sm:block ${active ? 'text-primary' : pending ? 'text-slate-400' : 'text-slate-600'}`}>
                {step.label}
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}
