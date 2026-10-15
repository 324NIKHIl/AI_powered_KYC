import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { useVerification } from '../context/VerificationContext'
import { uploadAadhaarQr, uploadDocument, verifyFace } from '../services/api'
import AadhaarQrPanel from '../components/AadhaarQrPanel'
import ProgressSteps from '../components/ProgressSteps'
import DocumentUpload from '../components/DocumentUpload'
import UserDetailsForm from '../components/UserDetailsForm'
import WebcamCapture from '../components/WebcamCapture'
import ConfidenceMeter from '../components/ConfidenceMeter'
import VerificationBreakdown from '../components/VerificationBreakdown'

// Document types offered on step 2 — choosing one is mandatory
const DOCUMENT_TYPES = [
  { value: 'aadhaar',         label: 'Aadhaar Card' },
  { value: 'passport',        label: 'Passport' },
  { value: 'citizenship',     label: 'Citizenship Certificate' },
  { value: 'pan',             label: 'PAN Card' },
  { value: 'driving_licence', label: 'Driving Licence' },
]
const MISMATCH_LABELS = { document_type: 'document type', name: 'name', dob: 'date of birth' }

export default function VerificationPage() {
  const { state, dispatch } = useVerification()
  const navigate = useNavigate()

  const [selectedFile,   setSelectedFile]   = useState(null)
  const [uploading,      setUploading]      = useState(false)
  const [uploadProgress, setUploadProgress] = useState(0)
  const [processingFace, setProcessingFace] = useState(false)
  const [typeTouched,    setTypeTouched]    = useState(false)

  const currentStep = state.step
  const documentType = state.documentResult?.document_type
  const showQrPanel = ['aadhaar', 'unknown'].includes(documentType) || Boolean(state.documentResult?.aadhaar_qr)
  const qrPending = showQrPanel && !state.documentResult?.aadhaar_qr?.found

  // ── Step 1 → 2: Upload document ─────────────────────────────────────────
  async function handleDocumentSubmit() {
    if (!state.documentType) { setTypeTouched(true); return }   // document type is mandatory
    if (!selectedFile) return
    setUploading(true)
    dispatch({ type: 'SET_LOADING', payload: true })
    try {
      const result = await uploadDocument(selectedFile, '', (pct) => setUploadProgress(pct), {
        documentType: state.documentType,
        fullName:     state.userDetails?.fullName,
        dob:          state.userDetails?.dob,
        phone:        state.userDetails?.phone,
      })
      dispatch({ type: 'DOCUMENT_SUCCESS', payload: result })
    } catch (err) {
      dispatch({ type: 'SET_ERROR', payload: err.message })
    } finally {
      setUploading(false)
    }
  }

  // ── Step 2 (optional): Aadhaar QR side ──────────────────────────────────
  async function handleQrUpload(file) {
    const result = await uploadAadhaarQr(state.sessionId, file)
    dispatch({ type: 'QR_SUCCESS', payload: result })
  }

  // ── Step 3 → 5: Face verify ─────────────────────────────────────────────
  async function handleFaceCapture({ base64, livenessVerified, extraFrames = [] }) {
    dispatch({ type: 'SET_STEP', payload: 5 })
    setProcessingFace(true)
    try {
      const result = await verifyFace(state.sessionId, base64, livenessVerified, extraFrames)
      dispatch({ type: 'FACE_SUCCESS', payload: result })
      navigate(`/result/${state.sessionId}`)
    } catch (err) {
      dispatch({ type: 'SET_ERROR', payload: err.message })
      dispatch({ type: 'SET_STEP', payload: 4 })
    } finally {
      setProcessingFace(false)
    }
  }

  return (
    <div className="min-h-screen py-12 px-4">
      <div className="max-w-3xl mx-auto space-y-8">
        {/* Header */}
        <div className="text-center space-y-2">
          <h1 className="text-3xl font-bold">Identity Verification</h1>
          <p className="text-white/40 text-sm">Complete all steps to verify your identity</p>
        </div>

        {/* Progress */}
        <ProgressSteps currentStep={currentStep} />

        {/* Error banner */}
        <AnimatePresence>
          {state.error && (
            <motion.div
              initial={{ opacity: 0, y: -10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              className="glass-card p-4 border-danger/30 flex items-start gap-3"
            >
              <span className="text-danger text-xl">⚠</span>
              <div>
                <p className="text-danger font-medium">Error</p>
                <p className="text-white/60 text-sm">{state.error}</p>
              </div>
              <button onClick={() => dispatch({ type: 'CLEAR_ERROR' })} className="ml-auto text-white/30 hover:text-white">✕</button>
            </motion.div>
          )}
        </AnimatePresence>

        {/* ── STEP 1: Your details ───────────────────────────────────────── */}
        {currentStep === 1 && (
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="glass-card p-8 space-y-6">
            <div>
              <h2 className="text-xl font-bold mb-1">Step 1 — Your Details</h2>
              <p className="text-white/40 text-sm">
                Enter your name and date of birth exactly as they appear on your document — we compare them with what is read from it — and a phone number to reach you.
              </p>
            </div>
            <UserDetailsForm
              initial={state.userDetails}
              onSubmit={(details) => dispatch({ type: 'DETAILS_SAVED', payload: details })}
            />
          </motion.div>
        )}

        {/* ── STEP 2: Document type + upload ─────────────────────────────── */}
        {currentStep === 2 && (
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="glass-card p-8 space-y-6">
            <div>
              <h2 className="text-xl font-bold mb-1">Step 2 — Upload Document</h2>
              <p className="text-white/40 text-sm">Choose the type of document, then upload a clear photo or scan of it</p>
            </div>

            <div className="space-y-1.5">
              <label htmlFor="documentType" className="text-sm text-white/60">
                Document type <span className="text-danger">*</span>
              </label>
              <select
                id="documentType"
                value={state.documentType}
                onChange={(e) => { dispatch({ type: 'SET_DOCUMENT_TYPE', payload: e.target.value }); setTypeTouched(true) }}
                aria-invalid={typeTouched && !state.documentType}
                className={`w-full rounded-xl bg-surface-700/60 border px-4 py-3 text-sm text-white focus:outline-none focus:border-primary ${
                  typeTouched && !state.documentType ? 'border-danger/60' : 'border-white/10'
                }`}
              >
                <option value="">Select a document type…</option>
                {DOCUMENT_TYPES.map((t) => (
                  <option key={t.value} value={t.value}>{t.label}</option>
                ))}
              </select>
              {!state.documentType && (
                <p className={`text-xs ${typeTouched ? 'text-danger' : 'text-white/30'}`}>
                  {typeTouched ? 'Cannot proceed — select a document type first.' : 'Required — you must select a document type to continue.'}
                </p>
              )}
            </div>

            <DocumentUpload
              onFileSelected={setSelectedFile}
              uploading={uploading}
              uploadProgress={uploadProgress}
            />
            <button
              onClick={handleDocumentSubmit}
              disabled={!state.documentType || !selectedFile || uploading}
              className="btn-primary w-full"
            >
              {uploading ? (
                <><span className="w-4 h-4 border-2 border-surface-900/50 border-t-surface-900 rounded-full animate-spin" /> Processing OCR…</>
              ) : 'Next: Extract Fields →'}
            </button>
            <button
              onClick={() => dispatch({ type: 'SET_STEP', payload: 1 })}
              disabled={uploading}
              className="text-white/40 text-sm hover:text-white/70 transition-colors mx-auto block"
            >
              ← Back to your details
            </button>
          </motion.div>
        )}

        {/* ── STEP 2: OCR Results ────────────────────────────────────────── */}
        {currentStep === 3 && state.documentResult && (
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="space-y-6">
            <div className="glass-card p-8 space-y-6">
              <div className="flex items-start justify-between">
                <div>
                  <h2 className="text-xl font-bold mb-1">Step 3 — OCR Results</h2>
                  <p className="text-white/40 text-sm">Review extracted information</p>
                </div>
                <div className="flex items-center gap-2 px-3 py-1 rounded-full bg-surface-700 text-xs font-mono uppercase">
                  <span className="w-2 h-2 rounded-full bg-primary" />
                  {state.documentResult.document_type}
                </div>
              </div>

              {/* Typed-in details vs what OCR read */}
              {state.documentResult.details_check && (
                state.documentResult.details_check.mismatches?.length > 0 ? (
                  <div className="flex items-start gap-3 p-3 rounded-xl bg-warning/10 border border-warning/20">
                    <span>⚠️</span>
                    <p className="text-sm">
                      What you entered doesn't match the document: {state.documentResult.details_check.mismatches
                        .map((k) => MISMATCH_LABELS[k] || k).join(', ')}. Check the values below, or go back and upload a clearer image.
                    </p>
                  </div>
                ) : state.documentResult.details_check.all_match ? (
                  <div className="flex items-center gap-3 p-3 rounded-xl bg-success/10 border border-success/20">
                    <span>✅</span>
                    <span className="text-sm">The details you entered match the document</span>
                  </div>
                ) : null
              )}

              {/* Confidence meter + fields */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-6 items-center">
                <ConfidenceMeter score={state.documentResult.document_confidence_score} label="OCR read confidence" />

                <div className="md:col-span-2 space-y-3">
                  {[
                    { label: 'Name',      value: state.documentResult.extracted_fields?.name,      valid: state.documentResult.field_validation?.name      },
                    { label: 'DOB',       value: state.documentResult.extracted_fields?.dob,       valid: state.documentResult.field_validation?.dob        },
                    { label: 'Gender',    value: state.documentResult.extracted_fields?.gender,    valid: true                                               },
                    { label: 'ID Number', value: state.documentResult.extracted_fields?.id_number, valid: state.documentResult.field_validation?.id_number  },
                  ].map(({ label, value, valid }) => (
                    <div key={label} className="flex items-center gap-3 bg-surface-700/50 rounded-xl px-4 py-3">
                      <span className={`w-2 h-2 rounded-full flex-shrink-0 ${valid ? 'bg-success' : 'bg-danger'}`} />
                      <span className="text-white/40 text-sm w-24 flex-shrink-0">{label}</span>
                      <span className="font-mono text-sm text-white truncate">{value || '—'}</span>
                      <span className="ml-auto text-xs">{valid ? '✓' : '✗'}</span>
                    </div>
                  ))}
                </div>
              </div>

              {/* Face extraction status */}
              <div className={`flex items-center gap-3 p-3 rounded-xl ${state.documentResult.document_face_extracted ? 'bg-success/10 border border-success/20' : 'bg-warning/10 border border-warning/20'}`}>
                <span>{state.documentResult.document_face_extracted ? '✅' : '⚠️'}</span>
                <span className="text-sm">
                  {state.documentResult.document_face_extracted
                    ? 'Face successfully extracted from document'
                    : 'No face detected — face match may fail'}
                </span>
              </div>
            </div>

            <VerificationBreakdown verification={state.documentResult.verification} />

            {/* Aadhaar back side / QR — shown before "Next" so it isn't missed.
                Also offered for unknown documents in case type detection missed an Aadhaar. */}
            {showQrPanel && (
              <AadhaarQrPanel qr={state.documentResult.aadhaar_qr} onUpload={handleQrUpload} />
            )}

            <button
              onClick={() => dispatch({ type: 'SET_STEP', payload: 4 })}
              className={qrPending ? 'btn-secondary w-full' : 'btn-primary w-full'}
            >
              {qrPending ? 'Skip QR check — continue to Live Face Capture →' : 'Next: Live Face Capture →'}
            </button>
          </motion.div>
        )}

        {/* ── STEP 3: Webcam capture ─────────────────────────────────────── */}
        {currentStep === 4 && (
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="glass-card p-8 space-y-6">
            <div>
              <h2 className="text-xl font-bold mb-1">Step 4 — Live Face Capture</h2>
              <p className="text-white/40 text-sm">
                Follow the on-screen liveness challenges, then capture your face
              </p>
            </div>
            <WebcamCapture onCapture={handleFaceCapture} sessionId={state.sessionId} />
          </motion.div>
        )}

        {/* ── STEP 4: Processing spinner ────────────────────────────────── */}
        {currentStep === 5 && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="glass-card p-16 flex flex-col items-center gap-6"
          >
            <div className="relative">
              <div className="w-20 h-20 border-4 border-primary/20 rounded-full" />
              <div className="absolute inset-0 border-4 border-transparent border-t-primary rounded-full animate-spin" />
              <div className="absolute inset-3 border-4 border-transparent border-t-accent rounded-full animate-spin-slow" />
            </div>
            <div className="text-center">
              <p className="text-lg font-semibold mb-1">Running Face Verification</p>
              <p className="text-white/40 text-sm">Generating face embeddings and computing cosine similarity…</p>
            </div>
            {[
              'Loading face model weights…',
              'Detecting face regions (MTCNN)…',
              'Generating 128-d embeddings…',
              'Computing cosine similarity…',
            ].map((msg, i) => (
              <motion.p
                key={msg}
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: i * 1.2 }}
                className="text-xs text-white/30 font-mono"
              >
                {'>'} {msg}
              </motion.p>
            ))}
          </motion.div>
        )}

        {/* Reset */}
        {currentStep < 5 && (
          <button
            onClick={() => dispatch({ type: 'RESET' })}
            className="text-white/20 text-sm hover:text-white/40 transition-colors mx-auto block"
          >
            ← Start over
          </button>
        )}
      </div>
    </div>
  )
}
