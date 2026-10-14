import { createContext, useContext, useReducer } from 'react'

/* ── State shape ─────────────────────────────────────────────────────────── */
const INITIAL = {
  sessionId:        null,
  step:             1,   // 1=upload, 2=ocr-preview, 3=webcam, 4=processing, 5=done
  documentResult:   null,
  faceResult:       null,
  error:            null,
  loading:          false,
}

/* ── Reducer ─────────────────────────────────────────────────────────────── */
function reducer(state, action) {
  console.log('[VERIFICATION DISPATCH]', action.type)
  switch (action.type) {
    case 'SET_LOADING':       return { ...state, loading: action.payload }
    case 'SET_ERROR':         return { ...state, error: action.payload, loading: false }
    case 'CLEAR_ERROR':       return { ...state, error: null }
    case 'SET_STEP':          return { ...state, step: action.payload }
    case 'DOCUMENT_SUCCESS':
      return {
        ...state,
        loading:        false,
        error:          null,
        sessionId:      action.payload.session_id,
        documentResult: action.payload,
        step:           2,
      }
    case 'QR_SUCCESS': {
      const { verification, ...qr } = action.payload || {}
      return {
        ...state,
        error:          null,
        documentResult: {
          ...state.documentResult,
          aadhaar_qr: qr,
          ...(verification ? { verification } : {}),
        },
      }
    }
    case 'FACE_SUCCESS':
      return {
        ...state,
        loading:    false,
        error:      null,
        faceResult: action.payload,
        step:       5,
      }
    case 'RESET':
      return INITIAL
    default:
      return state
  }
}

/* ── Context ─────────────────────────────────────────────────────────────── */
const VerificationContext = createContext(null)

export function VerificationProvider({ children }) {
  const [state, dispatch] = useReducer(reducer, INITIAL)
  return (
    <VerificationContext.Provider value={{ state, dispatch }}>
      {children}
    </VerificationContext.Provider>
  )
}

export function useVerification() {
  const ctx = useContext(VerificationContext)
  if (!ctx) throw new Error('useVerification must be used within VerificationProvider')
  return ctx
}
