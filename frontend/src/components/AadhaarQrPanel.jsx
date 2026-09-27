import { useState } from 'react'
import DocumentUpload from './DocumentUpload'

const SIGNATURE_STYLES = {
  verified:   { label: 'UIDAI signature verified',   icon: '🔏', className: 'bg-success/10 border-success/30 text-success' },
  invalid:    { label: 'Signature INVALID — forged', icon: '⛔', className: 'bg-danger/10 border-danger/30 text-danger' },
  unverified: { label: 'Signature not checked',      icon: '⚠️', className: 'bg-warning/10 border-warning/30 text-warning' },
  unsigned:   { label: 'Old QR — no signature',      icon: '⚠️', className: 'bg-warning/10 border-warning/30 text-warning' },
}

const CHECK_ICON = { match: '✓', mismatch: '✗', unavailable: '–' }
const CHECK_COLOR = { match: 'text-success', mismatch: 'text-danger', unavailable: 'text-white/30' }

const FIELD_ROWS = [
  { key: 'name',          label: 'Name' },
  { key: 'dob',           label: 'DOB' },
  { key: 'gender',        label: 'Gender' },
  { key: 'aadhaar_last4', label: 'Aadhaar', format: (v) => `XXXX XXXX ${v}` },
]

/**
 * Aadhaar Secure QR verification status.
 * - `onUpload` (optional): shows an upload box when no QR has been decoded yet.
 * - `qrFaceSimilarity` / `documentQrFaceSimilarity` / `tamperFlags`: results from face verification.
 */
export default function AadhaarQrPanel({
  qr,
  onUpload,
  qrFaceSimilarity,
  documentQrFaceSimilarity,
  tamperFlags,
}) {
  const [file, setFile] = useState(null)
  const [uploading, setUploading] = useState(false)
  const [uploadError, setUploadError] = useState(null)

  const found = qr?.found
  const signature = SIGNATURE_STYLES[qr?.signature_status]
  const flags = tamperFlags ?? qr?.tamper_flags ?? []
  const photoSrc = qr?.photo_path ? `/${qr.photo_path.replace(/\\/g, '/')}` : null

  async function handleUpload() {
    if (!file || !onUpload) return
    setUploading(true)
    setUploadError(null)
    try {
      await onUpload(file)
    } catch (err) {
      setUploadError(err.message)
    } finally {
      setUploading(false)
    }
  }

  return (
    <div className="glass-card p-6 space-y-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="font-bold text-lg flex items-center gap-2"><span>🔐</span> Aadhaar Secure QR</h3>
          <p className="text-white/40 text-xs mt-1">
            Checks UIDAI's digital signature and compares the signed details and photo with the printed card
          </p>
        </div>
        {signature && (
          <span className={`text-xs px-3 py-1 rounded-full border whitespace-nowrap ${signature.className}`}>
            {signature.icon} {signature.label}
          </span>
        )}
      </div>

      {qr?.message && <p className="text-sm text-white/60">{qr.message}</p>}

      {found && (
        <div className="grid grid-cols-1 sm:grid-cols-[auto,1fr] gap-4 items-start">
          {photoSrc && (
            <div className="text-center">
              <img src={photoSrc} alt="Photo from Aadhaar QR" className="w-24 h-28 object-cover rounded-xl border border-white/10 mx-auto" />
              <p className="text-[10px] text-white/30 mt-1 uppercase tracking-wider">QR photo</p>
            </div>
          )}
          <div className="space-y-2">
            {FIELD_ROWS.map(({ key, label, format }) => {
              const value = qr.fields?.[key]
              const check = qr.field_checks?.[key] ?? 'unavailable'
              return (
                <div key={key} className="flex items-center gap-3 bg-surface-700/40 rounded-xl px-4 py-2 text-sm">
                  <span className={`w-4 text-center ${CHECK_COLOR[check]}`} title={`Printed card: ${check}`}>{CHECK_ICON[check]}</span>
                  <span className="text-white/40 w-16 flex-shrink-0">{label}</span>
                  <span className="font-mono text-white/80 truncate">{value ? (format ? format(value) : value) : '—'}</span>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {(qrFaceSimilarity != null || documentQrFaceSimilarity != null) && (
        <div className="grid grid-cols-2 gap-3 text-sm">
          <Similarity label="Selfie ↔ QR photo" value={qrFaceSimilarity} />
          <Similarity label="Printed ↔ QR photo" value={documentQrFaceSimilarity} />
        </div>
      )}

      {flags.length > 0 && (
        <div className="bg-danger/10 border border-danger/30 rounded-xl p-3 space-y-1">
          <p className="text-danger text-sm font-semibold">Tampering indicators</p>
          {flags.map((flag) => (
            <p key={flag} className="text-danger/80 text-xs">• {flag}</p>
          ))}
        </div>
      )}

      {!found && onUpload && (
        <div className="space-y-3 pt-2 border-t border-white/5">
          <p className="text-sm text-white/60">
            <span className="text-white font-medium">Aadhaar card? Upload the side with the QR code</span> —
            on PVC cards it's the back. It's verified with UIDAI's digital signature: optional, but it
            catches edited cards and swapped photos.
          </p>
          <DocumentUpload onFileSelected={setFile} uploading={uploading} uploadProgress={0} />
          <button onClick={handleUpload} disabled={!file || uploading} className="btn-secondary w-full">
            {uploading ? 'Reading QR code…' : '🔍 Verify Aadhaar QR'}
          </button>
          {uploadError && <p className="text-danger text-sm">⚠ {uploadError}</p>}
        </div>
      )}
    </div>
  )
}

function Similarity({ label, value }) {
  return (
    <div className="bg-surface-700/40 rounded-xl px-4 py-2">
      <p className="text-white/40 text-xs">{label}</p>
      <p className="font-mono text-white/80">{value != null ? `${Math.round(value * 100)}%` : '—'}</p>
    </div>
  )
}
