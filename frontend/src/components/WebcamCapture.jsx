import { useRef, useState, useCallback } from 'react'
import Webcam from 'react-webcam'
import { motion, AnimatePresence } from 'framer-motion'
import { getLivenessChallenge } from '../services/api'

const VIDEO_CONSTRAINTS = {
  width:       640,
  height:      480,
  facingMode: 'user',
}

const ICONS = { center: '👁️', left: '⬅️', right: '➡️' }
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const b64 = (dataUrl) => dataUrl.split(',')[1]

/**
 * Active liveness: the server chooses a left/right order and checks the requested yaw direction.
 */
export default function WebcamCapture({ onCapture, sessionId }) {
  const webcamRef = useRef(null)
  const [ready,       setReady]       = useState(false)
  const [capturedImg, setCapturedImg] = useState(null)
  const [running,     setRunning]     = useState(false)
  const [steps,       setSteps]       = useState([])      // [{id, prompt}] from the server
  const [stepIdx,     setStepIdx]     = useState(-1)
  const [countdown,   setCountdown]   = useState(null)
  const [error,       setError]       = useState(null)

  const shot = () => webcamRef.current?.getScreenshot({ width: 640, height: 480 })

  const startChallenge = useCallback(async () => {
    if (!webcamRef.current || running) return
    setRunning(true)
    setError(null)
    try {
      const challenge = await getLivenessChallenge(sessionId)
      setSteps(challenge.steps)

      const frames = []
      let selfie = null
      const extraFrames = []

      for (let i = 0; i < challenge.steps.length; i++) {
        setStepIdx(i)
        // Time to read the prompt and move the head, then hold still for the frame.
        for (let c = 3; c >= 1; c--) {
          setCountdown(c)
          await sleep(900)
        }
        setCountdown(null)

        const frame = shot()
        if (!frame) throw new Error('Could not capture image. Please allow camera access.')

        if (i === 0) {
          // The straight-ahead frame is the selfie used for the face match.
          selfie = frame
          frames.push(b64(frame))
          for (let k = 0; k < 4; k++) {
            await sleep(250)
            const f = shot()
            if (f) extraFrames.push(b64(f))
          }
        } else {
          frames.push(b64(frame))
        }
      }

      setCapturedImg(selfie)
      setStepIdx(-1)
      onCapture({
        base64: b64(selfie),
        livenessVerified: true, // advisory only — the server decides from the frames below
        extraFrames,
        challenge: { challengeId: challenge.challenge_id, frames },
      })
    } catch (err) {
      setStepIdx(-1)
      setCountdown(null)
      setError(err?.response?.data?.detail || err.message || 'Liveness check failed. Please try again.')
    } finally {
      setRunning(false)
    }
  }, [running, sessionId, onCapture])

  const handleRetake = () => {
    setCapturedImg(null)
    setSteps([])
    setStepIdx(-1)
  }

  const current = steps[stepIdx]

  return (
    <div className="space-y-4">
      {/* Progress */}
      {!capturedImg && steps.length > 0 && (
        <div className="flex gap-2">
          {steps.map((s, i) => (
            <div
              key={s.id}
              className={`flex-1 h-1 rounded-full transition-all duration-500 ${
                i < stepIdx ? 'bg-primary' : i === stepIdx ? 'bg-primary/50 animate-pulse-slow' : 'bg-white/10'
              }`}
            />
          ))}
        </div>
      )}

      {/* Webcam / captured frame */}
      <div className="webcam-container aspect-video bg-surface-800 rounded-2xl overflow-hidden">
        {capturedImg ? (
          <img src={capturedImg} alt="Captured face" className="w-full h-full object-cover" />
        ) : (
          <Webcam
            ref={webcamRef}
            videoConstraints={VIDEO_CONSTRAINTS}
            screenshotFormat="image/jpeg"
            screenshotQuality={0.92}
            onUserMedia={() => setReady(true)}
            onUserMediaError={() => setError('Camera access denied. Please allow camera permissions.')}
            className="w-full h-full object-cover"
            mirrored
          />
        )}

        {/* Face guide overlay */}
        {!capturedImg && ready && (
          <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
            <svg width="200" height="260" viewBox="0 0 200 260" className="opacity-30">
              <ellipse cx="100" cy="120" rx="75" ry="95" fill="none" stroke="#00D4FF" strokeWidth="2" strokeDasharray="8 6" />
            </svg>
          </div>
        )}

        {/* Countdown overlay */}
        <AnimatePresence>
          {countdown && (
            <motion.div
              key={`${stepIdx}-${countdown}`}
              className="absolute inset-0 flex items-center justify-center bg-black/30 backdrop-blur-sm"
              initial={{ opacity: 0, scale: 0.5 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 1.5 }}
            >
              <span className="text-8xl font-bold text-primary" style={{ textShadow: '0 0 40px #00D4FF' }}>
                {countdown}
              </span>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* Current prompt */}
      {!capturedImg && current && (
        <motion.div
          key={stepIdx}
          initial={{ opacity: 0, y: 5 }}
          animate={{ opacity: 1, y: 0 }}
          className="glass-card p-3 flex items-center gap-3"
        >
          <span className="text-2xl">{ICONS[current.id]}</span>
          <div>
            <p className="text-xs text-white/40 uppercase tracking-wider">
              Liveness check — step {stepIdx + 1} of {steps.length}
            </p>
            <p className="text-sm font-medium text-white">{current.prompt}</p>
          </div>
        </motion.div>
      )}

      {!capturedImg && !running && ready && (
        <p className="text-xs text-white/40">
          Look straight at the camera, then slowly turn toward each direction shown. A turn beyond the minimum still passes.
        </p>
      )}

      {/* Action buttons */}
      <div className="flex gap-3">
        {!capturedImg ? (
          <button onClick={startChallenge} disabled={!ready || running} className="btn-primary flex-1">
            {running ? (
              <>
                <span className="w-4 h-4 border-2 border-surface-900/50 border-t-surface-900 rounded-full animate-spin" />
                Follow the prompts…
              </>
            ) : (
              <>📸 Start Liveness Check</>
            )}
          </button>
        ) : (
          <button onClick={handleRetake} className="btn-secondary flex-1">
            ↩ Retake
          </button>
        )}
      </div>

      {error && (
        <motion.p initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="text-danger text-sm">
          ⚠ {error}
        </motion.p>
      )}
    </div>
  )
}
