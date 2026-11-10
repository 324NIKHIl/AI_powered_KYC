import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { loginAdmin } from '../services/api'

export default function AdminLogin() {
  const navigate = useNavigate()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function submit(event) {
    event.preventDefault()
    setBusy(true)
    setError('')
    try {
      await loginAdmin(username, password)
      navigate('/admin', { replace: true })
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="min-h-[80vh] flex items-center justify-center px-4 py-12">
      <form onSubmit={submit} className="glass-card w-full max-w-md p-8 space-y-5">
        <div>
          <p className="text-primary text-xs uppercase tracking-[0.2em] font-semibold">Restricted area</p>
          <h1 className="text-3xl font-bold mt-2">Admin sign in</h1>
          <p className="text-white/40 text-sm mt-2">Sign in to review and manage KYC verifications.</p>
        </div>
        {error && <div role="alert" className="rounded-lg border border-danger/30 bg-danger/10 p-3 text-sm text-danger">{error}</div>}
        <label className="block text-sm text-white/60">Username
          <input autoComplete="username" required value={username} onChange={e => setUsername(e.target.value)} className="input-field mt-2" />
        </label>
        <label className="block text-sm text-white/60">Password
          <input type="password" autoComplete="current-password" required value={password} onChange={e => setPassword(e.target.value)} className="input-field mt-2" />
        </label>
        <button disabled={busy} className="btn-primary w-full">{busy ? 'Signing in…' : 'Sign in securely'}</button>
      </form>
    </div>
  )
}
