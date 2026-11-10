function formatDate(value) {
  if (!value) return 'Not extracted'
  const iso = String(value).match(/^(\d{4})-(\d{2})-(\d{2})$/)
  if (!iso) return value
  return new Date(Number(iso[1]), Number(iso[2]) - 1, Number(iso[3])).toLocaleDateString(undefined, {
    day: '2-digit', month: 'short', year: 'numeric',
  })
}

function titleCaseName(value) {
  return value ? value.toLowerCase().replace(/\b[a-z]/g, letter => letter.toUpperCase()) : ''
}

export default function PassportDetailsPanel({ fields = {}, verification = {} }) {
  const fullName = [verification.given_names, verification.surname].filter(Boolean).join(' ')
    || fields.name
  const details = [
    { label: 'Full name', value: titleCaseName(fullName) },
    { label: 'Date of birth', value: formatDate(verification.dob || fields.dob) },
    { label: 'Passport number', value: fields.id_number || verification.passport_number || 'Not extracted' },
    { label: 'Date of expiry', value: formatDate(verification.expiry || verification.expiry_date) },
  ]

  return (
    <section className="glass-card p-6 space-y-4">
      <div>
        <h2 className="font-bold text-lg flex items-center gap-2"><span>🛂</span> Passport Details</h2>
        <p className="text-xs text-white/40 mt-1">Extracted from the passport fields and machine-readable zone.</p>
      </div>
      <dl className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {details.map(({ label, value }) => (
          <div key={label} className="rounded-xl bg-surface-700/40 px-4 py-3">
            <dt className="text-xs text-white/40">{label}</dt>
            <dd className="mt-1 font-mono text-sm text-white/85 break-words">{value || 'Not extracted'}</dd>
          </div>
        ))}
      </dl>
    </section>
  )
}
