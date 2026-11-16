import StatusBadge from './StatusBadge'

const DOC_LABELS = {
  AADHAAR: 'AADHAAR CARD', PAN: 'PAN CARD', PASSPORT: 'PASSPORT', DRIVING_LICENCE: 'DRIVING LICENCE',
  CITIZENSHIP: 'CITIZENSHIP CERTIFICATE', EDUCATION: 'EDUCATION CERTIFICATE', COLLEGE_ID: 'COLLEGE ID', UNKNOWN: 'DOCUMENT',
}

const EVIDENCE = {
  none: 'Evidence: none — nothing usable could be established',
  format_only: 'Evidence: format check only — this does not show the document is genuine',
  document_analysis: 'Evidence: document analysis only — not verified against an authoritative source',
  cryptographic: 'Evidence: issuer digital signature verified',
  issuer_verified: 'Evidence: confirmed by an authoritative external source',
}

const ICONS = {
  pass: { icon: '✓', cls: 'text-success' },
  fail: { icon: '✗', cls: 'text-danger' },
  warn: { icon: '⚠', cls: 'text-warning' },
  skip: { icon: '–', cls: 'text-white/30' },
  info: { icon: 'ℹ', cls: 'text-white/40' },
}

export default function VerificationBreakdown({ verification }) {
  if (!verification) return null
  const type = String(verification.document_type || 'UNKNOWN').toUpperCase()
  const checks = verification.checks || []

  return (
    <div className="glass-card space-y-5 p-5 sm:p-6">
      <div><p className="text-xs font-semibold uppercase tracking-[.14em] text-slate-500">Document verification</p><h2 className="mt-1 text-lg font-semibold text-slate-900">{DOC_LABELS[type] || type.replace(/_/g, ' ')}</h2></div>

      {verification.external?.mock && (
        <div className="rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
          MOCK_VERIFICATION — a development provider was used. This is not a genuine verification.
        </div>
      )}

      <ul className="space-y-3">
        {checks.map((c, i) => {
          const o = ICONS[c.outcome] || ICONS.info
          const muted = c.outcome === 'skip' || c.outcome === 'info'
          return (
            <li key={`${c.id}-${i}`} className="flex items-start gap-3 text-sm leading-5">
              <span className={`${o.cls} w-4 text-center flex-shrink-0`}>{o.icon}</span>
              <div className="min-w-0">
                <p className={`font-medium ${muted ? 'text-slate-600' : 'text-slate-800'}`}>{c.label}</p>
                {c.detail && <p className="mt-0.5 text-sm leading-5 text-slate-600 break-words">{c.detail}</p>}
              </div>
            </li>
          )
        })}
      </ul>

      <p className="text-sm leading-5 text-slate-600">{EVIDENCE[verification.evidence_level] || EVIDENCE.none}</p>
      {verification.summary && <p className="text-sm leading-5 text-slate-700">{verification.summary}</p>}

      <div className="flex items-center justify-between border-t border-slate-200 pt-4">
        <span className="text-xs font-semibold tracking-wider text-slate-600">FINAL RESULT</span>
        <StatusBadge status={verification.status} />
      </div>
    </div>
  )
}
