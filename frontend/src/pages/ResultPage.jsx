import { useEffect, useState } from 'react'
import { useParams, Link, useLocation } from 'react-router-dom'
import { motion } from 'framer-motion'
import { useVerification } from '../context/VerificationContext'
import { getVerificationDetail, getVerificationFaceImage } from '../services/api'
import AadhaarQrPanel from '../components/AadhaarQrPanel'
import ConfidenceMeter from '../components/ConfidenceMeter'
import StatusBadge from '../components/StatusBadge'
import VerificationBreakdown from '../components/VerificationBreakdown'
import PassportDetailsPanel from '../components/PassportDetailsPanel'

const LEGACY = { APPROVED: 'VERIFIED', REJECTED: 'REJECTED', PENDING: 'MANUAL_REVIEW_REQUIRED' }
const TITLES = {
  VERIFIED: 'Identity Verified',
  REJECTED: 'Verification Rejected',
  SUSPICIOUS: 'Suspicious — flagged',
  VERIFICATION_UNAVAILABLE: 'Verification Unavailable',
  MANUAL_REVIEW_REQUIRED: 'Manual Review Required',
}
const TONES = {
  green: { border: 'border-l-emerald-600', bg: 'bg-emerald-50', text: 'text-emerald-800' },
  red:   { border: 'border-l-red-600', bg: 'bg-red-50', text: 'text-red-800' },
  amber: { border: 'border-l-amber-500', bg: 'bg-amber-50', text: 'text-amber-800' },
}
const toneFor = (st) => (st === 'VERIFIED' ? TONES.green : st === 'REJECTED' || st === 'SUSPICIOUS' ? TONES.red : TONES.amber)
const STATUS_SUMMARY = {
  VERIFIED: 'The configured verification checks met their pass criteria.',
  REJECTED: 'One or more required checks did not meet the configured criteria.',
  SUSPICIOUS: 'Review the flagged signals and supporting evidence for this case.',
  VERIFICATION_UNAVAILABLE: 'An authoritative verification source was unavailable for this case.',
  MANUAL_REVIEW_REQUIRED: 'This case needs a reviewer to assess the available evidence.',
}

export default function ResultPage() {
  const { sessionId }        = useParams()
  const location = useLocation()
  const returnTo = location.state?.returnTo || '/admin'
  const { state, dispatch }  = useVerification()
  const [record, setRecord]  = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError]    = useState(null)
  const [faceImages, setFaceImages] = useState({})

  // Prefer in-memory state; fall back to API fetch (e.g. direct link)
  useEffect(() => {
    async function load() {
      try {
        setLoading(true)
        const data = await getVerificationDetail(sessionId)
        setRecord(data)
      } catch (err) {
        setError(err.message)
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [sessionId])

  useEffect(() => {
    let active = true
    const objectUrls = []
    const images = [
      ['document', record?.document_face_path],
      ['live', record?.live_face_path],
    ].filter(([, path]) => Boolean(path))

    if (!images.length) {
      setFaceImages({})
      return undefined
    }

    Promise.all(images.map(async ([type]) => {
      try {
        const blob = await getVerificationFaceImage(sessionId, type)
        const url = URL.createObjectURL(blob)
        objectUrls.push(url)
        return [type, url]
      } catch {
        return [type, null]
      }
    })).then((entries) => {
      if (active) setFaceImages(Object.fromEntries(entries))
      else objectUrls.forEach(URL.revokeObjectURL)
    }).catch(() => {
      if (active) setFaceImages({})
    })

    return () => {
      active = false
      objectUrls.forEach(URL.revokeObjectURL)
    }
  }, [sessionId, record?.document_face_path, record?.live_face_path])

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="w-12 h-12 border-4 border-primary/20 border-t-primary rounded-full animate-spin" />
      </div>
    )
  }

  if (error || !record) {
    return (
      <div className="min-h-screen flex items-center justify-center px-4">
        <div className="glass-card p-10 text-center max-w-md">
          <p className="text-5xl mb-4">😕</p>
          <p className="text-lg font-semibold mb-2">Result Not Found</p>
          <p className="text-white/40 text-sm mb-6">{error || 'Session ID not recognised'}</p>
          <Link to="/verify" className="btn-primary">Try Again</Link>
        </div>
      </div>
    )
  }

  const kycStatus  = record.kyc_status || LEGACY[record.final_decision] || 'MANUAL_REVIEW_REQUIRED'
  const tone        = toneFor(kycStatus)
  const simScore    = record.similarity_score ?? 0
  const docScore    = record.document_confidence_score ?? 0
  const reasons     = record.reasons?.length ? record.reasons : (record.reason || record.rejection_reason ? [record.reason || record.rejection_reason] : [])
  const fields      = record.extracted_fields ?? {}
  const validation  = record.field_validation ?? {}
  const thresholds  = record.face_thresholds
  const faceStatus  = record.face_match_status || (record.face_match ? 'MATCH' : record.face_match === false ? 'NO_MATCH' : null)
  const liveness    = record.liveness
  const deepfake    = record.deepfake

  return (
    <div className="min-h-screen bg-slate-50/70 px-4 py-8 sm:py-10">
      <div className="mx-auto max-w-5xl space-y-6">

        <Link to={returnTo} className="inline-flex items-center gap-2 rounded-lg py-2 text-sm font-semibold text-primary hover:text-primary-dark">
          <span aria-hidden="true">←</span> Back to verification history
        </Link>

        {/* ── Result hero ─────────────────────────────────────────────────── */}
        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          className={`glass-card border-l-4 p-6 sm:p-8 ${tone.border}`}
        >
          <div className="flex flex-col gap-5 sm:flex-row sm:items-start">
            <div className={`flex h-12 w-12 shrink-0 items-center justify-center rounded-xl ${tone.bg} ${tone.text}`}>
              <ResultStatusIcon status={kycStatus} />
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[.14em] text-slate-500">Verification result</p>
                  <h1 className={`mt-1 text-2xl font-bold tracking-tight sm:text-3xl ${tone.text}`}>{TITLES[kycStatus] || kycStatus}</h1>
                </div>
                <StatusBadge status={kycStatus} large />
              </div>
              <p className="mt-2 text-sm leading-6 text-slate-700">{STATUS_SUMMARY[kycStatus] || 'Review the checks below for details.'}</p>
              {reasons.length > 0 && (
                <ul className="mt-4 space-y-2 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm leading-6 text-slate-700">
                  {reasons.map((r, i) => <li key={i}>{r}</li>)}
                </ul>
              )}
              <p className="mt-4 border-t border-slate-100 pt-3 font-mono text-xs text-slate-500">Session ID: {sessionId}</p>
            </div>
          </div>
        </motion.div>

        {/* ── Scores row ──────────────────────────────────────────────────── */}
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <ScoreCard label="OCR Read Confidence" value={docScore} color="primary" />
          <ScoreCard label="Face Similarity" value={simScore} color={faceStatus === 'MATCH' ? 'success' : faceStatus === 'UNCERTAIN' ? 'primary' : 'danger'} />
          <TriCard label="Face Match" value={faceStatus} />
          <TriCard label="Liveness" value={liveness?.status ?? (record.liveness_verified ? 'PASS' : null)} />
        </div>

        {String(record.document_type).toLowerCase() === 'passport' && (
          <PassportDetailsPanel
            fields={record.extracted_fields}
            verification={record.document_verification?.extracted}
          />
        )}

        {(record.document_face_path || record.live_face_path) && (
          <section className="glass-card p-5 space-y-4 sm:p-6">
            <div>
              <h2 className="font-semibold text-lg text-slate-900">Face capture review</h2>
              <p className="mt-1 text-sm text-slate-600">Compare the document portrait with the face captured during the liveness check.</p>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
              <FaceImageCard label="Document face" image={faceImages.document} loading={Boolean(record.document_face_path) && !Object.hasOwn(faceImages, 'document')} available={Boolean(record.document_face_path)} />
              <FaceImageCard label="Live liveness capture" image={faceImages.live} loading={Boolean(record.live_face_path) && !Object.hasOwn(faceImages, 'live')} available={Boolean(record.live_face_path)} />
            </div>
          </section>
        )}

        {/* ── Detailed breakdown ──────────────────────────────────────────── */}
        <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
          {/* Document fields */}
          <motion.div initial={{ opacity: 0, x: -20 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.3 }} className="glass-card p-5 space-y-4 sm:p-6">
            <h2 className="flex items-center gap-2 text-lg font-semibold text-slate-900">
              <DocumentIcon /> Document details
              <span className="ml-auto rounded-full bg-slate-100 px-2.5 py-1 text-[11px] font-semibold tracking-wide text-slate-600">{record.document_type?.replace(/_/g, ' ')}</span>
            </h2>
            {[
              { label: 'Name',      value: fields.name,      valid: validation.name      },
              { label: 'DOB',       value: fields.dob,       valid: validation.dob        },
              { label: 'Gender',    value: fields.gender,    valid: true                  },
              { label: 'ID Number', value: fields.id_number, valid: validation.id_number  },
              { label: 'Address',   value: fields.address,   valid: null                  },
            ].map(({ label, value, valid }) => (
              <div key={label} className="flex items-center gap-3 rounded-xl border border-slate-100 bg-slate-50 px-4 py-3 text-sm">
                {valid !== null && <span className={valid ? 'text-success' : 'text-danger'}>{valid ? '✓' : '✗'}</span>}
                <span className="w-20 flex-shrink-0 font-medium text-slate-600">{label}</span>
                <span className="truncate font-mono text-slate-900">{value || '—'}</span>
              </div>
            ))}
          </motion.div>

          {/* Confidence meters */}
          <motion.div initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.4 }} className="glass-card flex flex-col items-center justify-center gap-6 p-5 sm:p-6">
            <div className="flex gap-8 justify-center">
              <div className="text-center">
                <ConfidenceMeter score={docScore} label="OCR Read Confidence" size={140} />
              </div>
              <div className="text-center">
                <ConfidenceMeter score={simScore} label="Face Similarity" size={140} />
              </div>
            </div>
            <div className="text-center space-y-1">
              {thresholds && (
                <p className="text-xs text-slate-600">
                  Face match ≥ {Math.round(thresholds.face_match * 100)}% · no match &lt; {Math.round(thresholds.face_no_match * 100)}%
                </p>
              )}
              <p className="font-mono text-xs text-slate-500">
                {new Date(record.created_at).toLocaleString()}
              </p>
            </div>
          </motion.div>
        </div>

        {/* ── Document verification ───────────────────────────────────────── */}
        <VerificationBreakdown verification={record.document_verification} />

        {/* ── Identity checks ─────────────────────────────────────────────── */}
        <div className="glass-card space-y-5 p-5 sm:p-6">
          <div><h2 className="text-lg font-semibold text-slate-900">Identity checks</h2><p className="mt-1 text-sm text-slate-600">Individual signals used to reach this result.</p></div>
          <CheckRow
            label="Face match"
            value={faceStatus}
            detail={`Similarity ${Math.round(simScore * 100)}%` + (thresholds ? ` (match ≥ ${Math.round(thresholds.face_match * 100)}%, no match < ${Math.round(thresholds.face_no_match * 100)}%)` : '')}
          />
          <CheckRow label="Liveness" value={liveness?.status} detail={liveness?.reasons?.join('; ')} />
          <CheckRow
            label="Face alteration / deepfake analysis"
            value={deepfake?.requires_manual_review ? 'REVIEW' : deepfake?.level}
            detail={[
              deepfake?.method ? `Method: ${deepfake.method}` : null,
              deepfake?.level === 'HIGH' ? 'High alteration signal routed to manual review; it is not an automatic rejection.' : null,
              ...(deepfake?.reasons || []),
              deepfake?.model_score_calibrated === false
                ? 'Classifier score is uncalibrated and informational; it cannot label a face as generated by itself.'
                : 'A low score does not prove the face is genuine; review this signal with the other checks.',
            ].filter(Boolean).join(' · ')}
          />
          <div className="flex justify-between border-t border-slate-200 pt-4 text-sm">
            <span className="font-medium text-slate-600">Overall risk score</span>
            <span className="font-mono font-semibold text-slate-900">{record.risk_score != null ? `${Math.round(record.risk_score * 100)}%` : '—'}</span>
          </div>
        </div>

        {/* ── Aadhaar Secure QR ───────────────────────────────────────────── */}
        {record.aadhaar_qr && (
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.5 }}>
            <AadhaarQrPanel
              qr={record.aadhaar_qr}
              qrFaceSimilarity={record.qr_face_similarity}
              documentQrFaceSimilarity={record.document_qr_face_similarity}
              tamperFlags={record.tamper_flags}
            />
          </motion.div>
        )}

        {/* ── Actions ──────────────────────────────────────────────────────── */}
        <div className="flex flex-col justify-center gap-3 border-t border-slate-200 pt-6 sm:flex-row">
          <button onClick={() => { dispatch({ type: 'RESET' }); window.location.href = '/verify' }} className="btn-primary">
            New verification <span aria-hidden="true">→</span>
          </button>
          <Link to={returnTo} className="btn-secondary">
            ← Back to verification history
          </Link>
        </div>
      </div>
    </div>
  )
}

// ── Small sub-components ──────────────────────────────────────────────────────

function ScoreCard({ label, value, color }) {
  const colorMap = { primary: 'text-primary', success: 'text-success', danger: 'text-danger' }
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-4 text-center shadow-sm">
      <p className={`text-2xl font-bold tracking-tight ${colorMap[color] || 'text-slate-900'}`}>{Math.round(value * 100)}%</p>
      <p className="mt-1 text-xs font-medium text-slate-600">{label}</p>
    </div>
  )
}

const TRI_TONE = {
  MATCH: 'text-success', PASS: 'text-success', LOW: 'text-success',
  UNCERTAIN: 'text-warning', REVIEW: 'text-warning',
  NO_MATCH: 'text-danger', FAIL: 'text-danger', HIGH: 'text-danger',
}

function TriCard({ label, value }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-4 text-center shadow-sm">
      <p className={`text-lg font-bold ${TRI_TONE[value] || 'text-slate-500'}`}>{value ? value.replace(/_/g, ' ') : 'N/A'}</p>
      <p className="mt-1 text-xs font-medium text-slate-600">{label}</p>
    </div>
  )
}

function CheckRow({ label, value, detail }) {
  return (
    <div className="grid grid-cols-[7.5rem_minmax(0,1fr)] items-start gap-x-4 text-sm">
      <span className={`font-semibold ${TRI_TONE[value] || 'text-slate-500'}`}>{value ? value.replace(/_/g, ' ') : 'N/A'}</span>
      <div className="min-w-0">
        <p className="font-medium leading-5 text-slate-800">{label}</p>
        {detail && <p className="mt-1 text-sm leading-5 text-slate-600 break-words">{detail}</p>}
      </div>
    </div>
  )
}

function FaceImageCard({ label, image, loading, available }) {
  return (
    <div className="space-y-3 rounded-xl border border-slate-200 bg-slate-50 p-3.5 sm:p-4">
      <h3 className="text-sm font-semibold text-slate-700">{label}</h3>
      {image ? (
        <img src={image} alt={label} className="h-64 w-full rounded-lg bg-slate-200 object-contain" />
      ) : (
        <div className="flex h-64 w-full items-center justify-center rounded-lg bg-slate-100 px-4 text-center text-sm text-slate-600">
          {loading ? 'Loading face image…' : available ? 'Image unavailable. Restart the backend, then refresh this page.' : 'Face image not available'}
        </div>
      )}
    </div>
  )
}

function ResultStatusIcon({ status }) {
  const glyph = status === 'VERIFIED'
    ? <path d="m7 12.5 3.2 3.2L17.5 8" />
    : status === 'REJECTED'
      ? <path d="m8.5 8.5 7 7m0-7-7 7" />
      : <><path d="M12 7.5v5" /><path d="M12 16.5h.01" /></>

  return <svg aria-hidden="true" viewBox="0 0 24 24" className="h-6 w-6" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="9" />{glyph}</svg>
}

function DocumentIcon() {
  return <svg aria-hidden="true" viewBox="0 0 24 24" className="h-5 w-5 text-primary" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M7 3.75h7l4 4V20a.75.75 0 0 1-.75.75h-10.5A.75.75 0 0 1 6 20V4.75A1 1 0 0 1 7 3.75Z" /><path d="M14 4v4h4M9 13h6M9 16.5h6" /></svg>
}
