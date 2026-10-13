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
    <div className="glass-card p-6 space-y-4">
      <h2 className="font-bold text-lg">{DOC_LABELS[type] || type.replace(/_/g, ' ')}</h2>

      {verification.external?.mock && (
        <div className="p-3 rounded-xl bg-warning/10 border border-warning/20 text-xs text-warning">
          MOCK_VERIFICATION — a development provider was used. This is not a genuine verification.
        </div>
      )}

      <ul className="space-y-2">
        {checks.map((c, i) => {
          const o = ICONS[c.outcome] || ICONS.info
          const muted = c.outcome === 'skip' || c.outcome === 'info'
          return (
            <li key={`${c.id}-${i}`} className="flex items-start gap-3 text-sm">
              <span className={`${o.cls} w-4 text-center flex-shrink-0`}>{o.icon}</span>
              <div className="min-w-0">
                <p className={muted ? 'text-white/40' : 'text-white/80'}>{c.label}</p>
                {c.detail && <p className="text-xs text-white/40 break-words">{c.detail}</p>}
              </div>
            </li>
          )
        })}
      </ul>

      <p className="text-xs text-white/40">{EVIDENCE[verification.evidence_level] || EVIDENCE.none}</p>
      {verification.summary && <p className="text-sm text-white/60">{verification.summary}</p>}

      <div className="flex items-center justify-between pt-3 border-t border-white/10">
        <span className="text-xs font-semibold tracking-wider text-white/40">FINAL RESULT</span>
        <StatusBadge status={verification.status} />
      </div>
    </div>
  )
}
