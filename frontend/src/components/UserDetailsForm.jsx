import { useState } from 'react'

const todayIso = () => new Date().toISOString().slice(0, 10)

/** yyyy-mm-dd (date input) → dd/mm/yyyy (the format Indian IDs and the backend parser use) */
export function isoToDisplayDob(iso) {
  const [y, m, d] = (iso || '').split('-')
  return y && m && d ? `${d}/${m}/${y}` : ''
}

/** Optional leading +, then 7–15 digits (spaces, dashes and brackets allowed) — covers India (+91) and Nepal (+977). */
export function normalisePhone(raw) {
  const trimmed = (raw || '').trim()
  const digits = trimmed.replace(/\D/g, '')
  return (trimmed.startsWith('+') ? '+' : '') + digits
}

function validate({ fullName, dobIso, phone }) {
  const errors = {}
  const name = fullName.trim()
  if (!name) errors.fullName = 'Enter your full name as it appears on the document'
  else if (name.length < 2 || !/[A-Za-z]/.test(name)) errors.fullName = 'Enter a valid name'

  if (!dobIso) errors.dobIso = 'Select your date of birth'
  else if (dobIso > todayIso() || dobIso < '1900-01-01') errors.dobIso = 'Enter a valid date of birth'

  const raw = phone.trim()
  const digits = raw.replace(/\D/g, '')
  if (!raw) errors.phone = 'Enter your phone number'
  else if (!/^\+?[\d\s\-()]+$/.test(raw) || digits.length < 7 || digits.length > 15) errors.phone = 'Enter a valid phone number (7–15 digits, optional + country code)'
  return errors
}

export default function UserDetailsForm({ initial, onSubmit }) {
  const [values, setValues] = useState({
    fullName: initial?.fullName ?? '',
    dobIso:   initial?.dobIso   ?? '',
    phone:    initial?.phone    ?? '',
  })
  const [touched, setTouched] = useState(false)
  const errors = validate(values)
  const show = touched ? errors : {}

  const set = (key) => (e) => setValues((v) => ({ ...v, [key]: e.target.value }))

  function handleSubmit(e) {
    e.preventDefault()
    setTouched(true)
    if (Object.keys(errors).length) return
    onSubmit({
      fullName: values.fullName.trim(),
      dobIso:   values.dobIso,
      dob:      isoToDisplayDob(values.dobIso),
      phone:    normalisePhone(values.phone),
    })
  }

  const field = 'w-full rounded-xl bg-surface-700/60 border px-4 py-3 text-sm text-white placeholder-white/25 focus:outline-none focus:border-primary'
  const border = (k) => (show[k] ? 'border-danger/60' : 'border-white/10')

  return (
    <form onSubmit={handleSubmit} noValidate className="space-y-5">
      <div className="space-y-1.5">
        <label htmlFor="fullName" className="text-sm text-white/60">Full name</label>
        <input id="fullName" type="text" autoComplete="name" placeholder="As printed on your document"
          value={values.fullName} onChange={set('fullName')} className={`${field} ${border('fullName')}`} />
        {show.fullName && <p className="text-danger text-xs">{show.fullName}</p>}
      </div>

      <div className="space-y-1.5">
        <label htmlFor="dob" className="text-sm text-white/60">Date of birth</label>
        <input id="dob" type="date" min="1900-01-01" max={todayIso()}
          value={values.dobIso} onChange={set('dobIso')} className={`${field} ${border('dobIso')}`} />
        {show.dobIso && <p className="text-danger text-xs">{show.dobIso}</p>}
      </div>

      <div className="space-y-1.5">
        <label htmlFor="phone" className="text-sm text-white/60">Phone number</label>
        <input id="phone" type="tel" autoComplete="tel" inputMode="tel" placeholder="e.g. +91 98765 43210"
          value={values.phone} onChange={set('phone')} className={`${field} ${border('phone')}`} />
        {show.phone && <p className="text-danger text-xs">{show.phone}</p>}
      </div>

      <button type="submit" className="btn-primary w-full">Next: Choose Document →</button>
    </form>
  )
}
