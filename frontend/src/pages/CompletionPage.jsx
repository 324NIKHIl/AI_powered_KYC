import { Link } from 'react-router-dom'
import { motion } from 'framer-motion'

export default function CompletionPage() {
  return (
    <div className="min-h-[80vh] flex items-center justify-center px-4 py-12">
      <motion.div
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        className="glass-card max-w-xl p-10 text-center space-y-5"
      >
        <div className="mx-auto w-20 h-20 rounded-full bg-success/15 text-success flex items-center justify-center text-4xl">✓</div>
        <div>
          <h1 className="text-3xl font-bold">Verification submitted</h1>
          <p className="text-white/60 mt-3">
            Liveness check is complete and your verification has been sent for review. You may close this page.
          </p>
        </div>
        <Link to="/" className="btn-secondary">Return to home</Link>
      </motion.div>
    </div>
  )
}
