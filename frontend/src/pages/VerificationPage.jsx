import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { useVerification } from '../context/VerificationContext'
import { uploadDocument, verifyFace } from '../services/api'
import ProgressSteps from '../components/ProgressSteps'
import DocumentUpload from '../components/DocumentUpload'
import WebcamCapture from '../components/WebcamCapture'
import ConfidenceMeter from '../components/ConfidenceMeter'

export default function VerificationPage() {
  const { state, dispatch } = useVerification()
  const navigate = useNavigate()

  const [selectedFile,   setSelectedFile]   = useState(null)
  const [uploading,      setUploading]      = useState(false)
  const [uploadProgress, setUploadProgress] = useState(0)
  const [processingFace, setProcessingFace] = useState(false)

  const currentStep = state.step

  // ── Step 1 → 2: Upload document ─────────────────────────────────────────
  async function handleDocumentSubmit() {
    if (!selectedFile) return
    console.log('[VerificationPage] document submit', {
      fileName: selectedFile.name,
      fileType: selectedFile.type,
      fileSize: selectedFile.size,
    })
    setUploading(true)
    dispatch({ type: 'SET_LOADING', payload: true })
    try {
      const result = await uploadDocument(selectedFile, '', (pct) => setUploadProgress(pct))
      console.log('[VerificationPage] document result', result)
      dispatch({ type: 'DOCUMENT_SUCCESS', payload: result })
    } catch (err) {
      dispatch({ type: 'SET_ERROR', payload: err.message })
    } finally {
      setUploading(false)
    }
  }

  // ── Step 3 → 5: Face verify ─────────────────────────────────────────────
  async function handleFaceCapture({ base64, livenessVerified }) {
    console.log('[VerificationPage] face capture', {
      sessionId: state.sessionId,
      livenessVerified,
      payloadChars: base64?.length ?? 0,
    })
    dispatch({ type: 'SET_STEP', payload: 4 })
    setProcessingFace(true)
    try {
      const result = await verifyFace(state.sessionId, base64, livenessVerified)
      console.log('[VerificationPage] face result', result)
      dispatch({ type: 'FACE_SUCCESS', payload: result })
      navigate(`/result/${state.sessionId}`)
    } catch (err) {
      dispatch({ type: 'SET_ERROR', payload: err.message })
      dispatch({ type: 'SET_STEP', payload: 3 })
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

        {/* ── STEP 1: Upload ─────────────────────────────────────────────── */}
        {currentStep === 1 && (
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="glass-card p-8 space-y-6">
            <div>
              <h2 className="text-xl font-bold mb-1">Step 1 — Upload Document</h2>
              <p className="text-white/40 text-sm">Upload a clear photo or scan of your identity document</p>
            </div>
            <DocumentUpload
              onFileSelected={setSelectedFile}
              uploading={uploading}
              uploadProgress={uploadProgress}
            />
            <button
              onClick={handleDocumentSubmit}
              disabled={!selectedFile || uploading}
              className="btn-primary w-full"
            >
              {uploading ? (
                <><span className="w-4 h-4 border-2 border-surface-900/50 border-t-surface-900 rounded-full animate-spin" /> Processing OCR…</>
              ) : 'Next: Extract Fields →'}
            </button>
          </motion.div>
        )}

        {/* ── STEP 2: OCR Results ────────────────────────────────────────── */}
        {currentStep === 2 && state.documentResult && (
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="space-y-6">
            <div className="glass-card p-8 space-y-6">
              <div className="flex items-start justify-between">
                <div>
                  <h2 className="text-xl font-bold mb-1">Step 2 — OCR Results</h2>
                  <p className="text-white/40 text-sm">Review extracted information</p>
                </div>
                <div className="flex items-center gap-2 px-3 py-1 rounded-full bg-surface-700 text-xs font-mono uppercase">
                  <span className="w-2 h-2 rounded-full bg-primary" />
                  {state.documentResult.document_type}
                </div>
              </div>

              {/* Confidence meter + fields */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-6 items-center">
                <ConfidenceMeter score={state.documentResult.document_confidence_score} label="Doc Score" />

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

              <button onClick={() => dispatch({ type: 'SET_STEP', payload: 3 })} className="btn-primary w-full">
                Next: Live Face Capture →
              </button>
            </div>
          </motion.div>
        )}

        {/* ── STEP 3: Webcam capture ─────────────────────────────────────── */}
        {currentStep === 3 && (
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="glass-card p-8 space-y-6">
            <div>
              <h2 className="text-xl font-bold mb-1">Step 3 — Live Face Capture</h2>
              <p className="text-white/40 text-sm">
                Follow the on-screen liveness challenges, then capture your face
              </p>
            </div>
            <WebcamCapture onCapture={handleFaceCapture} sessionId={state.sessionId} />
          </motion.div>
        )}

        {/* ── STEP 4: Processing spinner ────────────────────────────────── */}
        {currentStep === 4 && (
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
        {currentStep < 4 && (
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
