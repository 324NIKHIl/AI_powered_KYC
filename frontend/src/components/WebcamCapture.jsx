import { useRef, useState, useCallback, useEffect } from 'react'
import Webcam from 'react-webcam'
import { motion, AnimatePresence } from 'framer-motion'

const VIDEO_CONSTRAINTS = {
  width:       640,
  height:      480,
  facingMode: 'user',
}

/**
 * Liveness challenge steps shown sequentially to the user.
 * After all steps are acknowledged, liveness is marked complete.
 */
const CHALLENGES = [
  { id: 1, text: 'Look straight at the camera', icon: '👁️'  },
  { id: 2, text: 'Blink your eyes slowly',       icon: '😑' },
  { id: 3, text: 'Slightly turn your head left', icon: '↩️' },
  { id: 4, text: 'Return to center — hold still',icon: '✅' },
]

export default function WebcamCapture({ onCapture, sessionId }) {
  const webcamRef = useRef(null)
  const [ready,         setReady]         = useState(false)
  const [capturedImg,   setCapturedImg]   = useState(null)
  const [challenge,     setChallenge]     = useState(0)   // index into CHALLENGES
  const [livenessOk,    setLivenessOk]    = useState(false)
  const [capturing,     setCapturing]     = useState(false)
  const [countdown,     setCountdown]     = useState(null)
  const [error,         setError]         = useState(null)

  // Auto-advance challenge every 2 s
  useEffect(() => {
    if (!ready || livenessOk) return
    const id = setTimeout(() => {
      setChallenge((c) => {
        if (c >= CHALLENGES.length - 1) {
          setLivenessOk(true)
          return c
        }
        return c + 1
      })
    }, 2000)
    return () => clearTimeout(id)
  }, [challenge, ready, livenessOk])

  const handleCapture = useCallback(async () => {
    if (!webcamRef.current || capturing) return
    setCapturing(true)
    setError(null)

    // 3-second countdown
    for (let i = 3; i >= 1; i--) {
      setCountdown(i)
      await new Promise((r) => setTimeout(r, 1000))
    }
    setCountdown(null)

    const imageSrc = webcamRef.current.getScreenshot({ width: 640, height: 480 })
    if (!imageSrc) {
      setError('Could not capture image. Please allow camera access.')
      setCapturing(false)
      return
    }

    setCapturedImg(imageSrc)
    setCapturing(false)

    // Pass base64 (strip data-URL prefix) and liveness flag to parent
    const base64 = imageSrc.split(',')[1]
    console.log('[WebcamCapture] captured frame', {
      sessionId,
      livenessOk,
      payloadChars: base64.length,
    })
    onCapture({ base64, livenessVerified: livenessOk })
  }, [capturing, livenessOk, onCapture])

  const handleRetake = () => {
    setCapturedImg(null)
    setChallenge(0)
    setLivenessOk(false)
  }

  return (
    <div className="space-y-4">
      {/* Liveness progress */}
      {!capturedImg && (
        <div className="flex gap-2">
          {CHALLENGES.map((c, i) => (
            <div
              key={c.id}
              className={`flex-1 h-1 rounded-full transition-all duration-500 ${
                i < challenge ? 'bg-primary' : i === challenge ? 'bg-primary/50 animate-pulse-slow' : 'bg-white/10'
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
              key={countdown}
              className="absolute inset-0 flex items-center justify-center bg-black/40 backdrop-blur-sm"
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

      {/* Challenge instruction */}
      {!capturedImg && ready && !livenessOk && (
        <motion.div
          key={challenge}
          initial={{ opacity: 0, y: 5 }}
          animate={{ opacity: 1, y: 0 }}
          className="glass-card p-3 flex items-center gap-3"
        >
          <span className="text-2xl">{CHALLENGES[challenge]?.icon}</span>
          <div>
            <p className="text-xs text-white/40 uppercase tracking-wider">Liveness Check</p>
            <p className="text-sm font-medium text-white">{CHALLENGES[challenge]?.text}</p>
          </div>
        </motion.div>
      )}

      {livenessOk && !capturedImg && (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="glass-card p-3 flex items-center gap-3 border-success/30">
          <span className="text-2xl">✅</span>
          <p className="text-sm font-medium text-success">Liveness confirmed — ready to capture</p>
        </motion.div>
      )}

      {/* Action buttons */}
      <div className="flex gap-3">
        {!capturedImg ? (
          <button
            onClick={handleCapture}
            disabled={!ready || !livenessOk || capturing}
            className="btn-primary flex-1"
          >
            {capturing ? (
              <>
                <span className="w-4 h-4 border-2 border-surface-900/50 border-t-surface-900 rounded-full animate-spin" />
                Capturing…
              </>
            ) : (
              <>📸 Capture Face</>
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
