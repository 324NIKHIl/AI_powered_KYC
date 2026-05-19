import { Link } from 'react-router-dom'
import { motion } from 'framer-motion'

const FEATURES = [
  { icon: '📄', title: 'OCR Extraction',       desc: 'EasyOCR extracts name, DOB, gender, and ID number from any document in seconds.' },
  { icon: '👁️', title: 'Face Verification',     desc: 'MTCNN + FaceNet generate face embeddings. Cosine similarity decides the match.' },
  { icon: '🎥', title: 'Liveness Detection',    desc: 'Challenge-response system ensures the user is present, not a printed photo.' },
  { icon: '🛡️', title: 'Fraud Prevention',      desc: 'Multi-signal decision engine approves or rejects with a confidence score.' },
  { icon: '🗄️', title: 'Audit Trail',           desc: 'Every verification is stored in MongoDB with full field-level logging.' },
  { icon: '⚡', title: 'Real-time Processing',  desc: 'FastAPI async backend ensures non-blocking, high-throughput verification.' },
]

const STEPS = [
  { n: '01', title: 'Upload Document',    desc: 'Drag & drop your Aadhaar, PAN, Passport, or College ID.' },
  { n: '02', title: 'OCR & Extraction',   desc: 'AI extracts and validates your personal details automatically.' },
  { n: '03', title: 'Live Face Capture',  desc: 'Webcam captures your face. Liveness challenges prevent spoofing.' },
  { n: '04', title: 'AI Decision',        desc: 'FaceNet embedding comparison gives APPROVED or REJECTED verdict.' },
]

const fadeUp = { hidden: { opacity: 0, y: 30 }, visible: (i) => ({ opacity: 1, y: 0, transition: { delay: i * 0.1, duration: 0.5 } }) }

export default function LandingPage() {
  return (
    <div className="overflow-hidden">
      {/* ── Hero ──────────────────────────────────────────────────────────── */}
      <section className="relative min-h-[90vh] flex items-center justify-center px-4 py-20">
        {/* Ambient blobs */}
        <div className="absolute top-20 left-1/4 w-96 h-96 bg-primary/10 rounded-full blur-3xl pointer-events-none" />
        <div className="absolute bottom-20 right-1/4 w-80 h-80 bg-accent/10 rounded-full blur-3xl pointer-events-none" />

        <div className="relative max-w-4xl mx-auto text-center space-y-8">
          {/* Badge */}
          <motion.div
            initial={{ opacity: 0, y: -20 }}
            animate={{ opacity: 1, y: 0 }}
            className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-primary/10 border border-primary/30 text-primary text-sm font-medium"
          >
            <span className="w-2 h-2 rounded-full bg-primary animate-pulse" />
            Phase 1 — Document & Face Verification
          </motion.div>

          {/* Headline */}
          <motion.h1
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1 }}
            className="text-5xl sm:text-6xl lg:text-7xl font-extrabold leading-tight tracking-tight"
          >
            <span className="text-white">AI-Powered</span>{' '}
            <br />
            <span className="gradient-text">KYC Verification</span>
          </motion.h1>

          <motion.p
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.25 }}
            className="text-lg text-white/50 max-w-2xl mx-auto leading-relaxed"
          >
            Verify identity documents with OCR and match live faces against document photos
            using state-of-the-art deep learning — MTCNN · FaceNet · EasyOCR.
          </motion.p>

          {/* CTA buttons */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.35 }}
            className="flex flex-col sm:flex-row gap-4 justify-center"
          >
            <Link to="/verify" className="btn-primary text-lg px-8 py-4">
              🚀 Start Verification
            </Link>
            <Link to="/admin" className="btn-secondary text-lg px-8 py-4">
              📊 View Dashboard
            </Link>
          </motion.div>

          {/* Stats row */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.5 }}
            className="flex flex-wrap justify-center gap-8 pt-8"
          >
            {[
              ['4 Document Types', 'Aadhaar, PAN, Passport, College ID'],
              ['FaceNet Model',    '128-d embeddings, cosine similarity'],
              ['MongoDB Logs',     'Full audit trail for every check'],
            ].map(([title, sub]) => (
              <div key={title} className="text-center">
                <div className="font-bold text-primary text-lg">{title}</div>
                <div className="text-white/40 text-sm">{sub}</div>
              </div>
            ))}
          </motion.div>
        </div>
      </section>

      {/* ── How it works ──────────────────────────────────────────────────── */}
      <section className="py-20 px-4">
        <div className="max-w-6xl mx-auto">
          <motion.div
            initial={{ opacity: 0 }}
            whileInView={{ opacity: 1 }}
            viewport={{ once: true }}
            className="text-center mb-14"
          >
            <h2 className="text-4xl font-bold mb-3">How It Works</h2>
            <p className="text-white/40">Four steps from upload to verdict</p>
          </motion.div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
            {STEPS.map((step, i) => (
              <motion.div
                key={step.n}
                custom={i}
                variants={fadeUp}
                initial="hidden"
                whileInView="visible"
                viewport={{ once: true }}
                className="glass-card p-6 relative overflow-hidden group hover:glow-border transition-all duration-300"
              >
                <div className="font-mono text-5xl font-extrabold text-primary/10 absolute top-4 right-4 group-hover:text-primary/20 transition-colors">
                  {step.n}
                </div>
                <p className="text-white font-semibold mb-2">{step.title}</p>
                <p className="text-white/40 text-sm leading-relaxed">{step.desc}</p>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Features grid ─────────────────────────────────────────────────── */}
      <section className="py-20 px-4 bg-surface-800/40">
        <div className="max-w-6xl mx-auto">
          <motion.div
            initial={{ opacity: 0 }}
            whileInView={{ opacity: 1 }}
            viewport={{ once: true }}
            className="text-center mb-14"
          >
            <h2 className="text-4xl font-bold mb-3">Technical Capabilities</h2>
            <p className="text-white/40">Phase 1 feature set</p>
          </motion.div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {FEATURES.map((f, i) => (
              <motion.div
                key={f.title}
                custom={i}
                variants={fadeUp}
                initial="hidden"
                whileInView="visible"
                viewport={{ once: true }}
                className="glass-card p-6 hover:glow-border transition-all duration-300 group"
              >
                <div className="text-3xl mb-4">{f.icon}</div>
                <h3 className="font-bold text-white mb-2 group-hover:text-primary transition-colors">{f.title}</h3>
                <p className="text-white/40 text-sm leading-relaxed">{f.desc}</p>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Footer CTA ───────────────────────────────────────────────────── */}
      <section className="py-20 px-4 text-center">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          className="max-w-2xl mx-auto"
        >
          <h2 className="text-4xl font-bold mb-4">Ready to verify?</h2>
          <p className="text-white/40 mb-8">Upload your document and complete liveness challenge in under 60 seconds.</p>
          <Link to="/verify" className="btn-primary text-lg px-10 py-4">
            Begin KYC Verification →
          </Link>
        </motion.div>
      </section>
    </div>
  )
}
