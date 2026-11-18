import { useEffect, useState, useCallback } from 'react'
import { Link, useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import { motion } from 'framer-motion'
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid } from 'recharts'
import { getVerificationHistory, getStats, deleteVerification, updateVerificationDetails, recordManualDecision, logoutAdmin } from '../services/api'
import StatusBadge from '../components/StatusBadge'

const COLORS = { APPROVED: '#0F766E', REJECTED: '#DC2626', PENDING: '#D97706' }

export default function AdminDashboard() {
  const navigate = useNavigate()
  const location = useLocation()
  const [searchParams, setSearchParams] = useSearchParams()
  const [stats,    setStats]    = useState(null)
  const [records,  setRecords]  = useState([])
  const [total,    setTotal]    = useState(0)
  const [page,     setPage]     = useState(() => Math.max(1, Number(searchParams.get('page')) || 1))
  const [filter,   setFilter]   = useState(() => searchParams.get('decision') || '')
  const [loading,  setLoading]  = useState(true)
  const [error,    setError]    = useState(null)
  const [editing, setEditing] = useState(null)
  const [editReason, setEditReason] = useState('')
  const [saving, setSaving] = useState(false)

  const LIMIT = 10

  const loadData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [s, h] = await Promise.all([
        getStats(),
        getVerificationHistory(page, LIMIT, filter || undefined),
      ])
      setStats(s)
      setRecords(h.records)
      setTotal(h.total)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [page, filter])

  useEffect(() => { loadData() }, [loadData])

  useEffect(() => {
    const params = new URLSearchParams()
    if (page > 1) params.set('page', String(page))
    if (filter) params.set('decision', filter)
    setSearchParams(params, { replace: true })
  }, [page, filter, setSearchParams])

  useEffect(() => {
    if (!loading && sessionStorage.getItem('adminDashboardScrollY') !== null) {
      const scrollY = Number(sessionStorage.getItem('adminDashboardScrollY')) || 0
      sessionStorage.removeItem('adminDashboardScrollY')
      requestAnimationFrame(() => window.scrollTo(0, scrollY))
    }
  }, [loading])

  async function handleDelete(sessionId) {
    if (!confirm('Delete this verification record?')) return
    try {
      await deleteVerification(sessionId)
      loadData()
    } catch (err) {
      alert(err.message)
    }
  }

  async function handleDecision(sessionId, decision) {
    const reason = window.prompt(`Reason for manually ${decision.toLowerCase()} this verification:`)
    if (reason === null) return
    if (reason.trim().length < 3) { window.alert('Please enter a reason (at least 3 characters).'); return }
    try {
      await recordManualDecision(sessionId, decision, reason.trim())
      await loadData()
    } catch (err) { setError(err.message) }
  }

  async function saveDetails(event) {
    event.preventDefault()
    if (!editReason.trim()) return
    setSaving(true)
    try {
      const extracted_fields = Object.fromEntries(new FormData(event.currentTarget).entries())
      delete extracted_fields.reason
      await updateVerificationDetails(editing.session_id, extracted_fields, editReason.trim())
      setEditing(null)
      setEditReason('')
      await loadData()
    } catch (err) { setError(err.message) }
    finally { setSaving(false) }
  }

  const pieData = stats ? [
    { name: 'Approved', value: stats.approved },
    { name: 'Rejected', value: stats.rejected },
    { name: 'Pending',  value: stats.pending  },
  ].filter(d => d.value > 0) : []

  const barData = records.slice(0, 8).map((r, i) => ({
    name:       `#${i + 1}`,
    similarity: Math.round((r.similarity_score ?? 0) * 100),
    doc_score:  Math.round((r.document_confidence_score ?? 0) * 100),
  }))

  return (
    <div className="min-h-screen bg-slate-50/70 px-4 py-8 sm:py-10">
      <div className="mx-auto max-w-7xl space-y-7">

        {/* Header */}
        <div className="flex flex-col gap-5 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[.16em] text-primary">Administration</p>
            <h1 className="mt-2 text-3xl font-bold tracking-tight text-slate-900 sm:text-4xl">Verification overview</h1>
            <p className="mt-2 text-sm text-slate-500">Monitor cases, review risk signals, and manage verification decisions.</p>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={loadData} disabled={loading} className="btn-secondary text-sm px-4 py-2.5">
              <RefreshIcon /> {loading ? 'Refreshing…' : 'Refresh data'}
            </button>
            <button onClick={() => { logoutAdmin(); navigate('/admin/login', { replace: true }) }} className="rounded-xl px-4 py-2.5 text-sm font-semibold text-slate-600 transition hover:bg-slate-100 hover:text-slate-900">Sign out</button>
          </div>
        </div>

        {error && (
          <div className="glass-card p-4 border-danger/30 text-danger text-sm">⚠ {error}</div>
        )}

        {/* ── Stats cards ─────────────────────────────────────────────────── */}
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
          {[
            { label: 'Total verifications', value: stats?.total ?? '—', icon: 'total', color: 'text-slate-900', tint: 'bg-slate-100 text-slate-600' },
            { label: 'Approved', value: stats?.approved ?? '—', icon: 'approved', color: 'text-emerald-700', tint: 'bg-emerald-50 text-emerald-700' },
            { label: 'Pending review', value: stats?.pending ?? '—', icon: 'pending', color: 'text-amber-700', tint: 'bg-amber-50 text-amber-700' },
            { label: 'Rejected', value: stats?.rejected ?? '—', icon: 'rejected', color: 'text-red-700', tint: 'bg-red-50 text-red-700' },
            { label: 'Approval rate', value: stats ? `${(stats.approval_rate * 100).toFixed(1)}%` : '—', icon: 'rate', color: 'text-primary', tint: 'bg-teal-50 text-primary' },
          ].map((card, i) => (
            <motion.div
              key={card.label}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.08 }}
              className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm transition hover:shadow-card"
            >
              <div className="flex items-start justify-between gap-3">
                <span className={`flex h-10 w-10 items-center justify-center rounded-xl ${card.tint}`}><MetricIcon name={card.icon} /></span>
                <span className={`text-2xl font-bold tracking-tight ${card.color}`}>{card.value}</span>
              </div>
              <p className="mt-4 text-xs font-medium text-slate-500">{card.label}</p>
            </motion.div>
          ))}
        </div>

        {/* ── Charts ──────────────────────────────────────────────────────── */}
        {stats && stats.total > 0 && (
          <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
            {/* Pie chart */}
            <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6">
              <div className="mb-3"><h2 className="font-semibold text-slate-900">Decision distribution</h2><p className="mt-1 text-xs text-slate-500">Current outcomes across all verification records</p></div>
              <div className="relative">
              <ResponsiveContainer width="100%" height={220}>
                <PieChart>
                  <Pie data={pieData} cx="50%" cy="50%" innerRadius={58} outerRadius={82} paddingAngle={3} dataKey="value" stroke="none">
                    {pieData.map((entry) => (
                      <Cell key={entry.name} fill={COLORS[entry.name.toUpperCase()]} />
                    ))}
                  </Pie>
                  <Tooltip contentStyle={{ background: '#FFFFFF', border: '1px solid #E2E8F0', borderRadius: '0.75rem', color: '#0F172A' }} />
                </PieChart>
              </ResponsiveContainer>
              <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center"><span className="text-2xl font-bold text-slate-900">{stats.total}</span><span className="text-[11px] text-slate-500">total cases</span></div>
              </div>
              <div className="flex flex-wrap justify-center gap-x-5 gap-y-2 border-t border-slate-100 pt-4">
                {pieData.map(item => <div key={item.name} className="flex items-center gap-2 text-xs text-slate-600"><span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: COLORS[item.name.toUpperCase()] }} />{item.name}<span className="font-semibold text-slate-800">{item.value}</span></div>)}
              </div>
            </div>

            {/* Bar chart */}
            <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6">
              <div className="mb-3"><h2 className="font-semibold text-slate-900">Recent check scores</h2><p className="mt-1 text-xs text-slate-500">Document read confidence and face similarity by case</p></div>
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={barData} barGap={5} margin={{ top: 8, right: 8, left: -16, bottom: 0 }}>
                  <CartesianGrid vertical={false} strokeDasharray="3 3" stroke="#E2E8F0" />
                  <XAxis dataKey="name" tick={{ fill: '#64748B', fontSize: 11 }} axisLine={false} tickLine={false} />
                  <YAxis domain={[0, 100]} tick={{ fill: '#64748B', fontSize: 11 }} axisLine={false} tickLine={false} />
                  <Tooltip cursor={{ fill: '#F8FAFC' }} contentStyle={{ background: '#FFFFFF', border: '1px solid #E2E8F0', borderRadius: '0.75rem', color: '#0F172A' }} />
                  <Bar dataKey="similarity" name="Face Similarity %" fill="#0F766E" radius={[4, 4, 0, 0]} />
                  <Bar dataKey="doc_score"  name="Doc Score %"      fill="#4F46E5" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
              <div className="flex justify-center gap-5 border-t border-slate-100 pt-4 text-xs text-slate-600"><span className="flex items-center gap-2"><i className="h-2.5 w-2.5 rounded-sm bg-primary" />Face similarity</span><span className="flex items-center gap-2"><i className="h-2.5 w-2.5 rounded-sm bg-indigo-600" />Document confidence</span></div>
            </div>
          </div>
        )}

        {/* ── Records table ────────────────────────────────────────────────── */}
        <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
          {/* Table header */}
          <div className="flex flex-col items-start gap-4 border-b border-slate-200 p-5 sm:flex-row sm:items-center sm:justify-between sm:p-6">
            <div><h2 className="font-semibold text-slate-900">Verification history</h2><p className="mt-1 text-xs text-slate-500">Inspect records and take manual action when needed.</p></div>
            <div className="flex flex-wrap gap-1 rounded-xl bg-slate-100 p-1">
              {['', 'APPROVED', 'REJECTED', 'PENDING'].map((f) => (
                <button
                  key={f}
                  onClick={() => { setFilter(f); setPage(1) }}
                  className={`rounded-lg px-3 py-1.5 text-xs font-semibold transition-colors ${filter === f ? 'bg-white text-primary shadow-sm' : 'text-slate-500 hover:text-slate-800'}`}
                >
                  {f || 'All'}
                </button>
              ))}
            </div>
          </div>

          {/* Table body */}
          {loading ? (
            <div className="p-14 text-center text-sm text-slate-500">Loading verification records…</div>
          ) : records.length === 0 ? (
            <div className="p-12 text-center">
              <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-2xl bg-slate-100 text-slate-500"><MetricIcon name="total" /></div>
              <p className="font-medium text-slate-700">No verification records found</p>
              <Link to="/verify" className="btn-primary mt-4 inline-flex">Start First Verification</Link>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-slate-50 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
                    <th className="px-5 py-3.5 text-left">Session</th>
                    <th className="px-5 py-3.5 text-left">Document</th>
                    <th className="px-5 py-3.5 text-left">Applicant</th>
                    <th className="px-5 py-3.5 text-center">OCR</th>
                    <th className="px-5 py-3.5 text-center">Face match</th>
                    <th className="px-5 py-3.5 text-center">Status</th>
                    <th className="px-5 py-3.5 text-left">Date</th>
                    <th className="px-5 py-3.5 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/5">
                  {records.map((r) => (
                    <tr key={r.session_id} className="transition-colors hover:bg-slate-50">
                      <td className="whitespace-nowrap px-5 py-4 font-mono text-xs text-slate-500">{r.session_id?.slice(0, 8)}…</td>
                      <td className="whitespace-nowrap px-5 py-4 text-xs font-semibold uppercase tracking-wide text-primary">{r.document_type?.replace(/_/g, ' ')}</td>
                      <td className="max-w-[160px] truncate px-5 py-4 font-medium text-slate-700">{r.extracted_fields?.name || '—'}</td>
                      <td className="px-5 py-4 text-center">
                        <ScorePill value={r.document_confidence_score} />
                      </td>
                      <td className="px-5 py-4 text-center">
                        <ScorePill value={r.similarity_score} />
                      </td>
                      <td className="px-5 py-4 text-center">
                        <StatusBadge status={r.kyc_status || r.final_decision} />
                      </td>
                      <td className="whitespace-nowrap px-5 py-4 text-xs text-slate-500">
                        {r.created_at ? new Date(r.created_at).toLocaleDateString() : '—'}
                      </td>
                      <td className="px-5 py-4 text-right">
                        <div className="flex items-center justify-end gap-1.5 whitespace-nowrap">
                          <Link
                            to={`/result/${r.session_id}`}
                            state={{ returnTo: `${location.pathname}${location.search}` }}
                            onClick={() => sessionStorage.setItem('adminDashboardScrollY', String(window.scrollY))}
                            className="rounded-lg px-2 py-1.5 text-xs font-semibold text-primary hover:bg-teal-50"
                          >View</Link>
                          <button onClick={() => { setEditing(r); setEditReason('') }} className="rounded-lg px-2 py-1.5 text-xs font-semibold text-slate-600 hover:bg-slate-100">Edit</button>
                          <button onClick={() => handleDecision(r.session_id, 'APPROVED')} className="rounded-lg px-2 py-1.5 text-xs font-semibold text-emerald-700 hover:bg-emerald-50">Approve</button>
                          <button onClick={() => handleDecision(r.session_id, 'REJECTED')} className="rounded-lg px-2 py-1.5 text-xs font-semibold text-red-700 hover:bg-red-50">Reject</button>
                          <button aria-label="Delete verification" onClick={() => handleDelete(r.session_id)} className="rounded-lg px-2 py-1.5 text-xs font-semibold text-slate-400 transition-colors hover:bg-red-50 hover:text-red-700">Delete</button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Pagination */}
          {total > LIMIT && (
            <div className="flex items-center justify-between border-t border-slate-200 p-4 text-sm text-slate-500">
              <span>{total} total records</span>
              <div className="flex gap-2">
                <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1} className="btn-secondary px-3 py-1.5 text-xs disabled:opacity-30">← Prev</button>
                <span className="px-3 py-1.5">Page {page} / {Math.ceil(total / LIMIT)}</span>
                <button onClick={() => setPage(p => p + 1)} disabled={page * LIMIT >= total} className="btn-secondary px-3 py-1.5 text-xs disabled:opacity-30">Next →</button>
              </div>
            </div>
          )}
        </div>
      </div>
      {editing && (
        <div className="fixed inset-0 z-[10000] bg-black/70 backdrop-blur-sm flex items-center justify-center p-4" role="dialog" aria-modal="true" aria-labelledby="edit-title">
          <form onSubmit={saveDetails} className="glass-card w-full max-w-xl p-6 space-y-4 max-h-[90vh] overflow-y-auto">
            <div className="flex items-start justify-between gap-4">
              <div><h2 id="edit-title" className="text-xl font-bold">Correct extracted details</h2><p className="text-xs text-white/40 mt-1">{editing.session_id}</p></div>
              <button type="button" onClick={() => setEditing(null)} className="text-white/50 hover:text-white" aria-label="Close">✕</button>
            </div>
            {['name', 'dob', 'gender', 'id_number', 'address'].map(field => (
              <label key={field} className="block text-sm text-white/60 capitalize">{field.replace('_', ' ')}
                <input name={field} defaultValue={editing.extracted_fields?.[field] || ''} className="input-field mt-1" />
              </label>
            ))}
            <label className="block text-sm text-white/60">Reason for correction
              <textarea required minLength={3} maxLength={1000} value={editReason} onChange={e => setEditReason(e.target.value)} className="input-field mt-1 min-h-24" />
            </label>
            <div className="flex justify-end gap-3"><button type="button" onClick={() => setEditing(null)} className="btn-secondary">Cancel</button><button disabled={saving} className="btn-primary">{saving ? 'Saving…' : 'Save correction'}</button></div>
          </form>
        </div>
      )}
    </div>
  )
}

function RefreshIcon() {
  return <svg aria-hidden="true" viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M20 7v5h-5M4.8 10a7.5 7.5 0 0 1 12.7-3L20 12M4 17v-5h5m10.2 2a7.5 7.5 0 0 1-12.7 3L4 12" /></svg>
}

function MetricIcon({ name }) {
  const paths = {
    total: <><rect x="5" y="4" width="14" height="16" rx="2" /><path d="M8 8h8M8 12h8M8 16h5" /></>,
    approved: <><circle cx="12" cy="12" r="8.5" /><path d="m8.5 12 2.3 2.3 4.8-5" /></>,
    pending: <><circle cx="12" cy="12" r="8.5" /><path d="M12 7v5l3.5 2" /></>,
    rejected: <><circle cx="12" cy="12" r="8.5" /><path d="m9 9 6 6m0-6-6 6" /></>,
    rate: <><path d="M4 18V6m0 12h16" /><path d="m7 14 4-4 3 2 5-6" /><path d="M15.5 6H19v3.5" /></>,
  }

  return <svg aria-hidden="true" viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">{paths[name]}</svg>
}

function ScorePill({ value }) {
  if (value === null || value === undefined) return <span className="text-white/20">—</span>
  const pct = Math.round(value * 100)
  const color = pct >= 75 ? 'text-success' : pct >= 50 ? 'text-warning' : 'text-danger'
  return <span className={`font-mono font-semibold ${color}`}>{pct}%</span>
}
