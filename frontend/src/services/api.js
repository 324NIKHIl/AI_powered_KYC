import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 300_000,  // 5 minutes for heavy processing (OCR, face extraction, etc.)
})

api.interceptors.request.use((config) => {
  const token = sessionStorage.getItem('adminToken')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

// ── Interceptors ─────────────────────────────────────────────────────────────
api.interceptors.response.use(
  (res) => {
    console.log('[API RESPONSE]', res.config?.method?.toUpperCase(), res.config?.url, res.status)
    return res
  },
  (err) => {
    if (err.response?.status === 401 && !err.config?.url?.includes('/admin/login')) {
      sessionStorage.removeItem('adminToken')
      sessionStorage.removeItem('adminUsername')
      if (window.location.pathname.startsWith('/admin')) window.location.assign('/admin/login')
    }
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
    console.error('[API ERROR]', err.config?.method?.toUpperCase(), err.config?.url, err.response?.status, message)
    return Promise.reject(new Error(message))
  }
)

// ── Document Verification ─────────────────────────────────────────────────────

/**
 * Upload an identity document image/PDF for OCR and face extraction.
 * @param {File} file
 * @param {string} [sessionId]
 * @param {Function} [onProgress] - (percent: number) => void
 * @param {{documentType: string, fullName?: string, dob?: string, phone?: string}} [details]
 *        documentType is mandatory (the backend rejects the upload without it)
 */
export async function uploadDocument(file, sessionId = '', onProgress, details = {}) {
  const form = new FormData()
  form.append('file', file)
  if (sessionId) form.append('session_id', sessionId)
  form.append('document_type', details.documentType || '')
  if (details.fullName) form.append('full_name', details.fullName)
  if (details.dob)      form.append('dob', details.dob)
  if (details.phone)    form.append('phone', details.phone)

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

/**
 * Upload the side of an Aadhaar card that carries the Secure QR code
 * (e.g. the back of a PVC card) for UIDAI signature verification.
 * @param {string} sessionId
 * @param {File} file
 */
export async function uploadAadhaarQr(sessionId, file) {
  const form = new FormData()
  form.append('file', file)
  form.append('session_id', sessionId)
  const { data } = await api.post('/upload-aadhaar-qr', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
}

// ── Face Verification ─────────────────────────────────────────────────────────

/**
 * Verify live face against the document face.
 * @param {string} sessionId
 * @param {string} liveFrameBase64 - base64 JPEG captured from webcam
 * @param {boolean} livenessVerified - whether frontend liveness challenge passed
 */
export async function verifyFace(sessionId, liveFrameBase64, livenessVerified = false, extraFrames = [], challenge = null) {
  const { data } = await api.post('/face-verify', {
    challenge_id:            challenge?.challengeId ?? null,
    challenge_frames_base64: challenge?.frames ?? [],
    session_id:        sessionId,
    live_face_base64:  liveFrameBase64,
    liveness_verified: livenessVerified,
    extra_frames_base64: extraFrames,
  })
  return data
}

/**
 * Ask the server for a randomized single-use left/right liveness challenge.
 * Resolves to { challenge_id, steps: [{ id: 'center'|'left'|'right', prompt }], expires_in }.
 */
export async function getLivenessChallenge(sessionId) {
  const { data } = await api.post('/liveness-challenge', { session_id: sessionId })
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
  return data
}

export async function getVerificationFaceImage(sessionId, imageType) {
  const { data } = await api.get(`/admin/verification/${sessionId}/face-image/${imageType}`, { responseType: 'blob' })
  if (!data.type?.startsWith('image/')) {
    throw new Error('The backend face-image route is unavailable. Restart the backend and refresh this page.')
  }
  return data
}

export async function deleteVerification(sessionId) {
  await api.delete(`/verification/${sessionId}`)
}

export async function loginAdmin(username, password) {
  const { data } = await api.post('/admin/login', { username, password })
  sessionStorage.setItem('adminToken', data.access_token)
  sessionStorage.setItem('adminUsername', data.username)
  return data
}

export function logoutAdmin() {
  sessionStorage.removeItem('adminToken')
  sessionStorage.removeItem('adminUsername')
}

export async function updateVerificationDetails(sessionId, extracted_fields, reason) {
  const { data } = await api.put(`/admin/verification/${sessionId}/details`, { extracted_fields, reason })
  return data
}

export async function recordManualDecision(sessionId, decision, reason) {
  const { data } = await api.put(`/admin/verification/${sessionId}/decision`, { decision, reason })
  return data
}

export default api
