
import { useRef, useState, useCallback } from 'react'
import Webcam from 'react-webcam'
import { motion, AnimatePresence } from 'framer-motion'
import { getLivenessChallenge } from '../services/api'

const VIDEO_CONSTRAINTS = {
  width: 640,
  height: 480,
  facingMode: 'user',
}

const ICONS = {
  center: '👁️',
  left: '⬅️',
  right: '➡️',
}

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))
const b64 = (dataUrl) => dataUrl.split(',')[1]

export default function WebcamCapture({ onCapture, sessionId }) {
  const webcamRef = useRef(null)

  const [ready, setReady] = useState(false)
  const [capturedImg, setCapturedImg] = useState(null)
  const [running, setRunning] = useState(false)
  const [steps, setSteps] = useState([])
  const [stepIdx, setStepIdx] = useState(-1)
  const [countdown, setCountdown] = useState(null)
  const [phase, setPhase] = useState('idle')
  const [error, setError] = useState(null)

  const shot = () =>
    webcamRef.current?.getScreenshot({ width: 640, height: 480 })

  const startChallenge = useCallback(async () => {
    if (!webcamRef.current || running) return

    setRunning(true)
    setError(null)
    setPhase('preparing')

    try {
      const challenge = await getLivenessChallenge(sessionId)
      setSteps(challenge.steps)

      const frames = []
      let selfie = null
      const extraFrames = []

      for (let i = 0; i < challenge.steps.length; i++) {
        setStepIdx(i)

        // Preparation countdown: 3 seconds
        setPhase('preparing')
        for (let c = 3; c >= 1; c--) {
          setCountdown(c)
          await sleep(1000)
        }

        setCountdown(null)

        // Give the user 5 seconds to perform the requested movement.
        setPhase('turning')
        await sleep(5000)

        // Capture 3 frames over 600ms to improve capture reliability.
        setPhase('capturing')
        const stepFrames = []

        for (let k = 0; k < 3; k++) {
          const frame = shot()
          if (frame) stepFrames.push(frame)
          await sleep(300)
        }

        if (stepFrames.length === 0) {
          throw new Error('Could not capture image. Please allow camera access.')
        }

        // Use the middle frame for this challenge step.
        const selectedFrame = stepFrames[Math.floor(stepFrames.length / 2)]
        frames.push(b64(selectedFrame))

        if (i === 0) {
          selfie = selectedFrame

          // Extra frames for passive temporal analysis.
          for (let k = 0; k < 4; k++) {
            const f = shot()
            if (f) extraFrames.push(b64(f))
            await sleep(250)
          }
        }

        setPhase('captured')
        await sleep(700)
      }

      setCapturedImg(selfie)
      setStepIdx(-1)
      setPhase('complete')

      onCapture({
        base64: b64(selfie),
        livenessVerified: true,
        extraFrames,
        challenge: {
          challengeId: challenge.challenge_id,
          frames,
        },
      })
    } catch (err) {
      setStepIdx(-1)
      setCountdown(null)
      setPhase('idle')
      setError(
        err?.response?.data?.detail ||
        err.message ||
        'Liveness check failed. Please try again.'
      )
    } finally {
      setRunning(false)
    }
  }, [running, sessionId, onCapture])

  const handleRetake = () => {
    setCapturedImg(null)
    setSteps([])
    setStepIdx(-1)
    setPhase('idle')
    setError(null)
  }

  const current = steps[stepIdx]

  return (
    <div className="space-y-4">

      {/* Instruction ABOVE webcam */}
      {!capturedImg && current && (
        <motion.div
          key={stepIdx}
          initial={{ opacity: 0, y: -8 }}
          animate={{ opacity: 1, y: 0 }}
          className="glass-card p-4 text-center"
        >
          <div className="text-4xl mb-2">
            {ICONS[current.id]}
          </div>

          <p className="text-xs text-white/50 uppercase tracking-wider">
            Liveness check — Step {stepIdx + 1} of {steps.length}
          </p>

          <p className="text-lg font-semibold text-white mt-1">
            {current.prompt}
          </p>

          <p className="text-sm text-white/60 mt-2">
            {phase === 'preparing' && 'Get ready...'}
            {phase === 'turning' && 'Slowly move your head and hold the position.'}
            {phase === 'capturing' && 'Hold still. Capturing your face...'}
            {phase === 'captured' && '✓ Position captured. Preparing next step...'}
          </p>
        </motion.div>
      )}

      {/* Progress */}
      {!capturedImg && steps.length > 0 && (
        <div className="flex gap-2">
          {steps.map((s, i) => (
            <div
              key={`${s.id}-${i}`}
              className={`flex-1 h-1 rounded-full ${
                i < stepIdx
                  ? 'bg-primary'
                  : i === stepIdx
                    ? 'bg-primary animate-pulse'
                    : 'bg-white/10'
              }`}
            />
          ))}
        </div>
      )}

      {/* Webcam */}
      <div className="webcam-container relative aspect-video bg-surface-800 rounded-2xl overflow-hidden">

        {capturedImg ? (
          <img
            src={capturedImg}
            alt="Captured face"
            className="w-full h-full object-cover"
          />
        ) : (
          <Webcam
            ref={webcamRef}
            videoConstraints={VIDEO_CONSTRAINTS}
            screenshotFormat="image/jpeg"
            screenshotQuality={0.92}
            onUserMedia={() => setReady(true)}
            onUserMediaError={() =>
              setError('Camera access denied. Please allow camera permissions.')
            }
            className="w-full h-full object-cover"
            mirrored
          />
        )}

        {/* Face guide */}
        {!capturedImg && ready && (
          <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
            <svg width="200" height="260" viewBox="0 0 200 260">
              <ellipse
                cx="100"
                cy="120"
                rx="75"
                ry="95"
                fill="none"
                stroke="#00D4FF"
                strokeWidth="2"
                strokeDasharray="8 6"
              />
            </svg>
          </div>
        )}

        {/* Countdown */}
        <AnimatePresence>
          {countdown !== null && (
            <motion.div
              key={`${stepIdx}-${countdown}`}
              className="absolute inset-0 flex items-center justify-center bg-black/40"
              initial={{ opacity: 0, scale: 0.7 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 1.2 }}
            >
              <span className="text-8xl font-bold text-primary">
                {countdown}
              </span>
            </motion.div>
          )}
        </AnimatePresence>

        {phase === 'captured' && (
          <div className="absolute inset-0 flex items-center justify-center bg-black/40">
            <span className="text-xl font-bold text-green-400">
              ✓ Captured
            </span>
          </div>
        )}
      </div>

      {/* Guidance before starting */}
      {!capturedImg && !running && ready && (
        <p className="text-sm text-white/60 text-center">
          Keep your face visible. Follow each instruction slowly
          and wait for the capture confirmation.
        </p>
      )}

      {/* Buttons */}
      <div className="flex gap-3">
        {!capturedImg ? (
          <button
            onClick={startChallenge}
            disabled={!ready || running}
            className="btn-primary flex-1"
          >
            {running ? 'Following liveness instructions...' : '📸 Start Liveness Check'}
          </button>
        ) : (
          <button
            onClick={handleRetake}
            className="btn-secondary flex-1"
          >
            ↩ Retake
          </button>
        )}
      </div>

      {error && (
        <motion.p
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="text-danger text-sm"
        >
          ⚠ {error}
        </motion.p>
      )}
    </div>
  )
}
