import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { motion } from 'framer-motion'
import { useVerification } from '../context/VerificationContext'
import { getVerificationDetail } from '../services/api'
import AadhaarQrPanel from '../components/AadhaarQrPanel'
import ConfidenceMeter from '../components/ConfidenceMeter'
import StatusBadge from '../components/StatusBadge'
import VerificationBreakdown from '../components/VerificationBreakdown'

const LEGACY = { APPROVED: 'VERIFIED', REJECTED: 'REJECTED', PENDING: 'MANUAL_REVIEW_REQUIRED' }
const TITLES = {
  VERIFIED: 'Identity Verified',
  REJECTED: 'Verification Rejected',
  SUSPICIOUS: 'Suspicious — flagged',
  VERIFICATION_UNAVAILABLE: 'Verification Unavailable',
  MANUAL_REVIEW_REQUIRED: 'Manual Review Required',
}
const TONES = {
  green: { border: 'border-success/40', bg: 'bg-success/20', text: 'text-success', glow: 'rgba(16,185,129,0.3)' },
  red:   { border: 'border-danger/40',  bg: 'bg-danger/20',  text: 'text-danger',  glow: 'rgba(239,68,68,0.3)' },
  amber: { border: 'border-warning/40', bg: 'bg-warning/20', text: 'text-warning', glow: 'rgba(245,158,11,0.3)' },
}
const toneFor = (st) => (st === 'VERIFIED' ? TONES.green : st === 'REJECTED' || st === 'SUSPICIOUS' ? TONES.red : TONES.amber)
const ICON = { VERIFIED: '✅', REJECTED: '❌', SUSPICIOUS: '🚩', VERIFICATION_UNAVAILABLE: '⚠️', MANUAL_REVIEW_REQUIRED: '🕵️' }

export default function ResultPage() {
  const { sessionId }        = useParams()
  const { state, dispatch }  = useVerification()
  const [record, setRecord]  = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError]    = useState(null)

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
    <div className="min-h-screen py-12 px-4">
      <div className="max-w-4xl mx-auto space-y-8">

        {/* ── Result hero ─────────────────────────────────────────────────── */}
        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          className={`glass-card p-10 text-center border-2 ${tone.border}`}
        >
          <motion.div
            initial={{ scale: 0 }}
            animate={{ scale: 1 }}
            transition={{ type: 'spring', stiffness: 300, delay: 0.2 }}
            className={`w-24 h-24 rounded-full mx-auto mb-6 flex items-center justify-center text-5xl ${tone.bg}`}
            style={{ boxShadow: `0 0 40px ${tone.glow}` }}
          >
            {ICON[kycStatus]}
          </motion.div>

          <h1 className={`text-4xl font-extrabold mb-3 ${tone.text}`}>{TITLES[kycStatus] || kycStatus}</h1>

          {reasons.length > 0 && (
            <ul className="text-white/50 text-sm mb-4 space-y-1">
              {reasons.map((r, i) => <li key={i}>{r}</li>)}
            </ul>
          )}

          <StatusBadge status={kycStatus} large />

          <p className="text-white/30 text-xs mt-4 font-mono">Session: {sessionId}</p>
        </motion.div>

        {/* ── Scores row ──────────────────────────────────────────────────── */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <ScoreCard label="OCR Read Confidence" value={docScore} color="primary" />
          <ScoreCard label="Face Similarity" value={simScore} color={faceStatus === 'MATCH' ? 'success' : faceStatus === 'UNCERTAIN' ? 'primary' : 'danger'} />
          <TriCard label="Face Match" value={faceStatus} />
          <TriCard label="Liveness" value={liveness?.status ?? (record.liveness_verified ? 'PASS' : null)} />
        </div>

        {/* ── Detailed breakdown ──────────────────────────────────────────── */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Document fields */}
          <motion.div initial={{ opacity: 0, x: -20 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.3 }} className="glass-card p-6 space-y-4">
            <h2 className="font-bold text-lg flex items-center gap-2">
              <span>📄</span> Document Details
              <span className="ml-auto text-xs px-2 py-0.5 rounded bg-surface-600 font-mono uppercase">{record.document_type}</span>
            </h2>
            {[
              { label: 'Name',      value: fields.name,      valid: validation.name      },
              { label: 'DOB',       value: fields.dob,       valid: validation.dob        },
              { label: 'Gender',    value: fields.gender,    valid: true                  },
              { label: 'ID Number', value: fields.id_number, valid: validation.id_number  },
              { label: 'Address',   value: fields.address,   valid: null                  },
            ].map(({ label, value, valid }) => (
              <div key={label} className="flex items-center gap-3 bg-surface-700/40 rounded-xl px-4 py-3 text-sm">
                {valid !== null && <span className={valid ? 'text-success' : 'text-danger'}>{valid ? '✓' : '✗'}</span>}
                <span className="text-white/40 w-20 flex-shrink-0">{label}</span>
                <span className="font-mono text-white/80 truncate">{value || '—'}</span>
              </div>
            ))}
          </motion.div>

          {/* Confidence meters */}
          <motion.div initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.4 }} className="glass-card p-6 flex flex-col items-center justify-center gap-8">
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
                <p className="text-xs text-white/30">
                  Face match ≥ {Math.round(thresholds.face_match * 100)}% · no match &lt; {Math.round(thresholds.face_no_match * 100)}%
                </p>
              )}
              <p className="text-xs text-white/20 font-mono">
                {new Date(record.created_at).toLocaleString()}
              </p>
            </div>
          </motion.div>
        </div>

        {/* ── Document verification ───────────────────────────────────────── */}
        <VerificationBreakdown verification={record.document_verification} />

        {/* ── Identity checks ─────────────────────────────────────────────── */}
        <div className="glass-card p-6 space-y-4">
          <h2 className="font-bold text-lg">Identity checks</h2>
          <CheckRow
            label="Face match"
            value={faceStatus}
            detail={`Similarity ${Math.round(simScore * 100)}%` + (thresholds ? ` (match ≥ ${Math.round(thresholds.face_match * 100)}%, no match < ${Math.round(thresholds.face_no_match * 100)}%)` : '')}
          />
          <CheckRow label="Liveness" value={liveness?.status} detail={liveness?.reasons?.join('; ')} />
          <CheckRow
            label="Face alteration / deepfake analysis (heuristic)"
            value={deepfake?.level}
            detail={deepfake?.reasons?.join('; ') || 'Heuristic signals only — a low score does not prove the face is genuine'}
          />
          <div className="flex justify-between pt-3 border-t border-white/10 text-sm">
            <span className="text-white/40">Overall risk score</span>
            <span className="font-mono">{record.risk_score != null ? `${Math.round(record.risk_score * 100)}%` : '—'}</span>
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
        <div className="flex flex-col sm:flex-row gap-4 justify-center">
          <button onClick={() => { dispatch({ type: 'RESET' }); window.location.href = '/verify' }} className="btn-primary">
            🔄 New Verification
          </button>
          <Link to="/admin" className="btn-secondary">
            📊 View Dashboard
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
    <div className="glass-card p-4 text-center">
      <p className={`text-2xl font-bold ${colorMap[color] || 'text-white'}`}>{Math.round(value * 100)}%</p>
      <p className="text-white/40 text-xs mt-1">{label}</p>
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
    <div className="glass-card p-4 text-center">
      <p className={`text-xl font-bold ${TRI_TONE[value] || 'text-white/40'}`}>{value ? value.replace(/_/g, ' ') : 'N/A'}</p>
      <p className="text-white/40 text-xs mt-1">{label}</p>
    </div>
  )
}

function CheckRow({ label, value, detail }) {
  return (
    <div className="flex items-start gap-3 text-sm">
      <span className={`w-28 flex-shrink-0 font-semibold ${TRI_TONE[value] || 'text-white/40'}`}>{value ? value.replace(/_/g, ' ') : 'N/A'}</span>
      <div className="min-w-0">
        <p className="text-white/80">{label}</p>
        {detail && <p className="text-xs text-white/40 break-words">{detail}</p>}
      </div>
    </div>
  )
}
