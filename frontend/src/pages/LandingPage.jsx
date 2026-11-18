import { Link } from 'react-router-dom'
import { motion } from 'framer-motion'

const FEATURES = [
  { number: '01', title: 'Document understanding', desc: 'Extract and review identity fields across supported document formats with OCR and document-specific checks.' },
  { number: '02', title: 'Face comparison', desc: 'Compare the portrait on the document with the face captured during the verification flow.' },
  { number: '03', title: 'Liveness assessment', desc: 'Use a guided camera challenge and capture signals to assess whether a person is present.' },
  { number: '04', title: 'Risk screening', desc: 'Combine image-analysis signals to identify cases that may need a closer human review.' },
  { number: '05', title: 'Aadhaar QR checks', desc: 'Validate supported Secure QR signatures locally and compare signed data with extracted fields.' },
  { number: '06', title: 'Review workflow', desc: 'Keep verification history and give administrators a place to inspect and resolve cases.' },
]

const STEPS = [
  { n: '01', title: 'Share your details', desc: 'Enter the information needed for the selected identity document.' },
  { n: '02', title: 'Upload a document', desc: 'Choose the document type and upload a clear image for text extraction.' },
  { n: '03', title: 'Complete a face check', desc: 'Follow the live camera prompt and complete the liveness challenge.' },
  { n: '04', title: 'Review the outcome', desc: 'See the verification result or route the case to an administrator.' },
]

const reveal = { hidden: { opacity: 0, y: 18 }, visible: (i = 0) => ({ opacity: 1, y: 0, transition: { delay: i * 0.08, duration: 0.45 } }) }

function ShieldIcon() {
  return <svg viewBox="0 0 24 24" fill="none" className="w-5 h-5" stroke="currentColor" strokeWidth="1.8"><path d="M12 3 19 6v5c0 4.5-2.8 8-7 10-4.2-2-7-5.5-7-10V6l7-3Z"/><path d="m9 12 2 2 4-4"/></svg>
}

export default function LandingPage() {
  return (
    <div className="overflow-hidden">
      <section className="relative px-4 pt-16 pb-20 sm:pt-24 sm:pb-28">
        <div className="pointer-events-none absolute -top-40 right-[-8rem] h-[34rem] w-[34rem] rounded-full bg-teal-100/70 blur-3xl" />
        <div className="relative mx-auto grid max-w-7xl items-center gap-14 lg:grid-cols-[1.05fr_.95fr] lg:gap-16">
          <div className="max-w-2xl">
            <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="mb-6 inline-flex items-center gap-2 rounded-full border border-primary/15 bg-white px-3.5 py-2 text-xs font-semibold tracking-wide text-primary shadow-sm">
              <span className="h-2 w-2 rounded-full bg-emerald-500" /> DIGITAL IDENTITY REVIEW
            </motion.div>
            <motion.h1 initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: .06 }} className="max-w-[20ch] text-4xl font-bold leading-[1.1] tracking-tight text-slate-950 sm:text-5xl lg:text-[3.25rem]">
              A Multimodal Framework for <span className="text-primary">Risk-Aware Digital Identity Verification</span>
            </motion.h1>
            <motion.p initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: .16 }} className="mt-6 max-w-xl text-base leading-7 text-slate-600 sm:text-lg">
              A guided verification experience that brings document review, face comparison, and liveness checks into one workflow—with human review for uncertain cases.
            </motion.p>
            <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: .24 }} className="mt-8 flex flex-col gap-3 sm:flex-row">
              <Link to="/verify" className="btn-primary px-6 py-3.5">Start verification <span aria-hidden="true">→</span></Link>
              <a href="#how-it-works" className="btn-secondary px-6 py-3.5">Explore the process</a>
            </motion.div>
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: .35 }} className="mt-10 flex flex-wrap gap-x-7 gap-y-3 border-t border-slate-200 pt-6 text-sm text-slate-500">
              <span className="inline-flex items-center gap-2"><span className="text-primary"><ShieldIcon /></span> Multiple evidence checks</span>
              <span className="inline-flex items-center gap-2"><span className="h-1.5 w-1.5 rounded-full bg-emerald-500" /> Review when uncertain</span>
            </motion.div>
          </div>

          <motion.div initial={{ opacity: 0, y: 18, scale: .98 }} animate={{ opacity: 1, y: 0, scale: 1 }} transition={{ delay: .12, duration: .5 }} className="relative mx-auto w-full max-w-xl">
            <div className="absolute -inset-5 rounded-[2rem] bg-gradient-to-br from-teal-100/80 via-white to-indigo-100/70 blur-xl" />
            <div className="glass-card relative overflow-hidden p-5 sm:p-7">
              <div className="flex items-center justify-between border-b border-slate-100 pb-5">
                <div><p className="text-xs font-semibold uppercase tracking-[.16em] text-slate-400">Verification overview</p><h2 className="mt-1 text-lg font-bold text-slate-900">Evidence review</h2></div>
                <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-teal-50 text-primary"><ShieldIcon /></div>
              </div>
              <div className="mt-5 space-y-3">
                {[
                  ['Document details', 'Text extraction and field checks', 'Reviewed'],
                  ['Face comparison', 'Document portrait and live capture', 'Compared'],
                  ['Liveness check', 'Guided camera challenge', 'Completed'],
                ].map(([title, desc, status], i) => (
                  <div key={title} className="flex items-center gap-3 rounded-xl border border-slate-100 bg-slate-50/70 p-3.5">
                    <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-white text-sm font-bold text-primary shadow-sm">0{i + 1}</span>
                    <div className="min-w-0 flex-1"><p className="truncate text-sm font-semibold text-slate-800">{title}</p><p className="mt-0.5 truncate text-xs text-slate-500">{desc}</p></div>
                    <span className="hidden rounded-full bg-emerald-50 px-2.5 py-1 text-[11px] font-semibold text-emerald-700 sm:inline-flex">{status}</span>
                  </div>
                ))}
              </div>
              <div className="mt-5 rounded-xl border border-amber-200/80 bg-amber-50/70 p-4">
                <div className="flex gap-3"><span className="mt-0.5 text-amber-700">ⓘ</span><div><p className="text-sm font-semibold text-slate-800">A careful, reviewable result</p><p className="mt-1 text-xs leading-5 text-slate-600">Automated signals support the decision. Cases that need judgment can be sent for manual review.</p></div></div>
              </div>
              <p className="mt-4 text-center text-[11px] text-slate-400">Illustrative workflow preview</p>
            </div>
          </motion.div>
        </div>
      </section>

      <section id="how-it-works" className="border-y border-slate-200 bg-white px-4 py-20 sm:py-24">
        <div className="mx-auto max-w-7xl">
          <div className="mb-11 max-w-xl"><p className="text-xs font-bold uppercase tracking-[.18em] text-primary">A straightforward process</p><h2 className="mt-3 text-3xl font-bold tracking-tight text-slate-900 sm:text-4xl">From document to review</h2><p className="mt-3 text-slate-600">Each step adds a separate piece of evidence to the verification.</p></div>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {STEPS.map((step, i) => <motion.article key={step.n} custom={i} variants={reveal} initial="hidden" whileInView="visible" viewport={{ once: true }} className="rounded-2xl border border-slate-200 bg-slate-50/60 p-5 transition duration-200 hover:-translate-y-1 hover:bg-white hover:shadow-card">
              <span className="text-xs font-bold tracking-[.16em] text-primary">STEP {step.n}</span><h3 className="mt-5 font-semibold text-slate-900">{step.title}</h3><p className="mt-2 text-sm leading-6 text-slate-600">{step.desc}</p>
            </motion.article>)}
          </div>
        </div>
      </section>

      <section className="px-4 py-20 sm:py-24">
        <div className="mx-auto max-w-7xl">
          <div className="mb-11 max-w-xl"><p className="text-xs font-bold uppercase tracking-[.18em] text-primary">Built around evidence</p><h2 className="mt-3 text-3xl font-bold tracking-tight text-slate-900 sm:text-4xl">Verification tools in one place</h2><p className="mt-3 text-slate-600">Separate checks help make outcomes easier to understand and review.</p></div>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {FEATURES.map((feature, i) => <motion.article key={feature.number} custom={i} variants={reveal} initial="hidden" whileInView="visible" viewport={{ once: true }} className="group rounded-2xl border border-slate-200 bg-white p-6 shadow-sm transition duration-200 hover:-translate-y-1 hover:border-teal-200 hover:shadow-card">
              <div className="flex items-center justify-between"><span className="flex h-10 w-10 items-center justify-center rounded-xl bg-teal-50 text-primary"><ShieldIcon /></span><span className="font-mono text-xs text-slate-400">{feature.number}</span></div>
              <h3 className="mt-5 font-semibold text-slate-900 group-hover:text-primary">{feature.title}</h3><p className="mt-2 text-sm leading-6 text-slate-600">{feature.desc}</p>
            </motion.article>)}
          </div>
        </div>
      </section>

      <section className="px-4 pb-20 sm:pb-24">
        <div className="mx-auto flex max-w-7xl flex-col items-start justify-between gap-6 rounded-3xl bg-slate-900 px-7 py-9 !text-white sm:flex-row sm:items-center sm:px-10 sm:py-11">
          <div><p className="text-xs font-semibold uppercase tracking-[.18em] text-teal-300">Ready when you are</p><h2 className="mt-2 text-2xl font-bold sm:text-3xl">Begin your verification</h2><p className="mt-2 max-w-xl text-sm leading-6 text-slate-300">Have your identity document ready and follow each on-screen step.</p></div>
          <Link to="/verify" className="inline-flex shrink-0 items-center gap-2 rounded-xl bg-white px-5 py-3 font-semibold text-slate-900 transition hover:bg-teal-50">Start verification <span aria-hidden="true">→</span></Link>
        </div>
      </section>
    </div>
  )
}
