import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { motion } from 'framer-motion'
import { useVerification } from '../context/VerificationContext'
import { getVerificationDetail } from '../services/api'
import ConfidenceMeter from '../components/ConfidenceMeter'
import StatusBadge from '../components/StatusBadge'

const FACE_SIMILARITY_THRESHOLD = 0.32

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
        console.log('[ResultPage] loaded result', data)
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

  const isApproved  = record.verified === true || record.status === 'approved' || record.final_decision === 'APPROVED'
  const simScore    = record.similarity_score ?? 0
  const docScore    = record.document_confidence_score ?? 0
  const reason      = record.reason || record.rejection_reason
  const fields      = record.extracted_fields ?? {}
  const validation  = record.field_validation ?? {}
  console.log('[ResultPage] render decision', {
    verified: record.verified,
    status: record.status,
    finalDecision: record.final_decision,
    isApproved,
    similarity: simScore,
    reason,
  })

  return (
    <div className="min-h-screen py-12 px-4">
      <div className="max-w-4xl mx-auto space-y-8">

        {/* ── Result hero ─────────────────────────────────────────────────── */}
        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          className={`glass-card p-10 text-center border-2 ${isApproved ? 'border-success/40' : 'border-danger/40'}`}
        >
          {/* Animated icon */}
          <motion.div
            initial={{ scale: 0 }}
            animate={{ scale: 1 }}
            transition={{ type: 'spring', stiffness: 300, delay: 0.2 }}
            className={`w-24 h-24 rounded-full mx-auto mb-6 flex items-center justify-center text-5xl ${isApproved ? 'bg-success/20' : 'bg-danger/20'}`}
            style={{ boxShadow: isApproved ? '0 0 40px rgba(16,185,129,0.3)' : '0 0 40px rgba(239,68,68,0.3)' }}
          >
            {isApproved ? '✅' : '❌'}
          </motion.div>

          <h1 className={`text-4xl font-extrabold mb-3 ${isApproved ? 'text-success' : 'text-danger'}`}>
            Verification {record.final_decision}
          </h1>

          {reason && (
            <p className="text-white/50 text-sm mb-4">Reason: {reason}</p>
          )}

          <StatusBadge status={record.final_decision} large />

          <p className="text-white/30 text-xs mt-4 font-mono">Session: {sessionId}</p>
        </motion.div>

        {/* ── Scores row ──────────────────────────────────────────────────── */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <ScoreCard label="Document Score"  value={docScore}  color="primary" />
          <ScoreCard label="Face Similarity" value={simScore}  color={simScore >= FACE_SIMILARITY_THRESHOLD ? 'success' : 'danger'} />
          <BoolCard  label="Face Match"     value={record.face_match} />
          <BoolCard  label="Liveness"       value={record.liveness_verified} />
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
                <ConfidenceMeter score={docScore} label="Doc Confidence" size={140} />
              </div>
              <div className="text-center">
                <ConfidenceMeter score={simScore} label="Face Similarity" size={140} />
              </div>
            </div>
            <div className="text-center space-y-1">
              <p className="text-xs text-white/30">Threshold for approval: Face ≥ 32%</p>
              <p className="text-xs text-white/20 font-mono">
                {new Date(record.created_at).toLocaleString()}
              </p>
            </div>
          </motion.div>
        </div>

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

function BoolCard({ label, value }) {
  return (
    <div className="glass-card p-4 text-center">
      <p className={`text-2xl font-bold ${value ? 'text-success' : 'text-danger'}`}>{value ? 'PASS' : 'FAIL'}</p>
      <p className="text-white/40 text-xs mt-1">{label}</p>
    </div>
  )
}
