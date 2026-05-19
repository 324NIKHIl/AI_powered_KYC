import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 300_000,  // 5 minutes for heavy processing (OCR, face extraction, etc.)
})

// ── Interceptors ─────────────────────────────────────────────────────────────
api.interceptors.response.use(
  (res) => {
    console.log('[API RESPONSE]', res.config?.method?.toUpperCase(), res.config?.url, res.data)
    return res
  },
  (err) => {
    let message =
      err.response?.data?.detail ||
      err.response?.data?.message ||
      err.message ||
      'An unexpected error occurred'
    
    // Better error messages
    if (err.code === 'ECONNABORTED') {
      message = 'Request timeout - server is taking too long. Please try again.'
    } else if (err.code === 'ENOTFOUND' || err.code === 'ECONNREFUSED') {
      message = 'Cannot connect to server. Make sure the backend is running.'
    }
    console.error('[API ERROR]', err.config?.method?.toUpperCase(), err.config?.url, message, err.response?.data)
    return Promise.reject(new Error(message))
  }
)

// ── Document Verification ─────────────────────────────────────────────────────

/**
 * Upload an identity document image/PDF for OCR and face extraction.
 * @param {File} file
 * @param {string} [sessionId]
 * @param {Function} [onProgress] - (percent: number) => void
 */
export async function uploadDocument(file, sessionId = '', onProgress) {
  console.log('[UPLOAD_DOCUMENT REQUEST]', {
    name: file?.name,
    type: file?.type,
    size: file?.size,
    sessionId,
  })
  const form = new FormData()
  form.append('file', file)
  if (sessionId) form.append('session_id', sessionId)

  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), 300_000) // 5 minute timeout

  try {
    const { data } = await api.post('/upload-document', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
      signal: controller.signal,
      onUploadProgress: (e) => {
        if (onProgress && e.total) onProgress(Math.round((e.loaded / e.total) * 100))
      },
    })
    console.log('[UPLOAD_DOCUMENT RESULT]', data)
    return data
  } catch (err) {
    if (err.name === 'AbortError') {
      throw new Error('Upload timed out after 5 minutes. Please check your internet connection and try again.')
    }
    throw err
  } finally {
    clearTimeout(timeoutId)
  }
}

// ── Face Verification ─────────────────────────────────────────────────────────

/**
 * Verify live face against the document face.
 * @param {string} sessionId
 * @param {string} liveFrameBase64 - base64 JPEG captured from webcam
 * @param {boolean} livenessVerified - whether frontend liveness challenge passed
 */
export async function verifyFace(sessionId, liveFrameBase64, livenessVerified = false) {
  console.log('[VERIFY_FACE REQUEST]', {
    sessionId,
    livenessVerified,
    payloadChars: liveFrameBase64?.length ?? 0,
  })
  const { data } = await api.post('/face-verify', {
    session_id:        sessionId,
    live_face_base64:  liveFrameBase64,
    liveness_verified: livenessVerified,
  })
  console.log('SIMILARITY:', data.similarity_score)
  console.log('VERIFIED:', data.verified)
  console.log('[VERIFY_FACE RESULT]', data)
  return data
}

/**
 * Quick server-side liveness check.
 * @param {string} frameBase64
 */
export async function checkLiveness(frameBase64) {
  const { data } = await api.post('/liveness-check', { frame_base64: frameBase64 })
  return data
}

// ── Admin ─────────────────────────────────────────────────────────────────────

export async function getVerificationHistory(page = 1, limit = 20, decision) {
  const params = { page, limit }
  if (decision) params.decision = decision
  const { data } = await api.get('/verification-history', { params })
  return data
}

export async function getStats() {
  const { data } = await api.get('/stats')
  return data
}

export async function getVerificationDetail(sessionId) {
  const { data } = await api.get(`/verification/${sessionId}`)
  console.log('[RESULT_DETAIL]', data)
  return data
}

export async function deleteVerification(sessionId) {
  await api.delete(`/verification/${sessionId}`)
}

export default api
