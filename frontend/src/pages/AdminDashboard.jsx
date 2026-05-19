import { useEffect, useState, useCallback } from 'react'
import { Link } from 'react-router-dom'
import { motion } from 'framer-motion'
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid } from 'recharts'
import { getVerificationHistory, getStats, deleteVerification } from '../services/api'
import StatusBadge from '../components/StatusBadge'

const COLORS = { APPROVED: '#10B981', REJECTED: '#EF4444', PENDING: '#F59E0B' }

export default function AdminDashboard() {
  const [stats,    setStats]    = useState(null)
  const [records,  setRecords]  = useState([])
  const [total,    setTotal]    = useState(0)
  const [page,     setPage]     = useState(1)
  const [filter,   setFilter]   = useState('')
  const [loading,  setLoading]  = useState(true)
  const [error,    setError]    = useState(null)

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

  async function handleDelete(sessionId) {
    if (!confirm('Delete this verification record?')) return
    try {
      await deleteVerification(sessionId)
      loadData()
    } catch (err) {
      alert(err.message)
    }
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
    <div className="min-h-screen py-10 px-4">
      <div className="max-w-7xl mx-auto space-y-8">

        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold">Admin Dashboard</h1>
            <p className="text-white/40 text-sm mt-1">KYC Verification Analytics</p>
          </div>
          <button onClick={loadData} className="btn-secondary text-sm px-4 py-2">
            ↻ Refresh
          </button>
        </div>

        {error && (
          <div className="glass-card p-4 border-danger/30 text-danger text-sm">⚠ {error}</div>
        )}

        {/* ── Stats cards ─────────────────────────────────────────────────── */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {[
            { label: 'Total Verifications', value: stats?.total     ?? '—', icon: '🔢', color: 'text-primary' },
            { label: 'Approved',            value: stats?.approved  ?? '—', icon: '✅', color: 'text-success' },
            { label: 'Rejected',            value: stats?.rejected  ?? '—', icon: '❌', color: 'text-danger'  },
            { label: 'Approval Rate',       value: stats ? `${(stats.approval_rate * 100).toFixed(1)}%` : '—', icon: '📈', color: 'text-primary' },
          ].map((card, i) => (
            <motion.div
              key={card.label}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.08 }}
              className="glass-card p-6"
            >
              <div className="flex items-center justify-between mb-3">
                <span className="text-2xl">{card.icon}</span>
                <span className={`text-2xl font-extrabold ${card.color}`}>{card.value}</span>
              </div>
              <p className="text-white/40 text-sm">{card.label}</p>
            </motion.div>
          ))}
        </div>

        {/* ── Charts ──────────────────────────────────────────────────────── */}
        {stats && stats.total > 0 && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* Pie chart */}
            <div className="glass-card p-6">
              <h2 className="font-bold mb-4">Decision Distribution</h2>
              <ResponsiveContainer width="100%" height={200}>
                <PieChart>
                  <Pie data={pieData} cx="50%" cy="50%" outerRadius={80} dataKey="value" label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}>
                    {pieData.map((entry) => (
                      <Cell key={entry.name} fill={COLORS[entry.name.toUpperCase()]} />
                    ))}
                  </Pie>
                  <Tooltip contentStyle={{ background: '#0F1629', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '0.75rem' }} />
                </PieChart>
              </ResponsiveContainer>
            </div>

            {/* Bar chart */}
            <div className="glass-card p-6">
              <h2 className="font-bold mb-4">Score Comparison (Recent)</h2>
              <ResponsiveContainer width="100%" height={200}>
                <BarChart data={barData} barGap={4}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                  <XAxis dataKey="name" tick={{ fill: 'rgba(255,255,255,0.3)', fontSize: 11 }} />
                  <YAxis domain={[0, 100]} tick={{ fill: 'rgba(255,255,255,0.3)', fontSize: 11 }} />
                  <Tooltip contentStyle={{ background: '#0F1629', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '0.75rem' }} />
                  <Bar dataKey="similarity" name="Face Similarity %" fill="#00D4FF" radius={[4, 4, 0, 0]} />
                  <Bar dataKey="doc_score"  name="Doc Score %"      fill="#7C3AED" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        )}

        {/* ── Records table ────────────────────────────────────────────────── */}
        <div className="glass-card overflow-hidden">
          {/* Table header */}
          <div className="p-6 border-b border-white/5 flex flex-col sm:flex-row items-start sm:items-center gap-4">
            <h2 className="font-bold flex-1">Verification History</h2>
            <div className="flex gap-2">
              {['', 'APPROVED', 'REJECTED', 'PENDING'].map((f) => (
                <button
                  key={f}
                  onClick={() => { setFilter(f); setPage(1) }}
                  className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${filter === f ? 'bg-primary/20 text-primary border border-primary/30' : 'bg-surface-700 text-white/40 hover:text-white'}`}
                >
                  {f || 'All'}
                </button>
              ))}
            </div>
          </div>

          {/* Table body */}
          {loading ? (
            <div className="p-12 text-center text-white/30">Loading…</div>
          ) : records.length === 0 ? (
            <div className="p-12 text-center">
              <p className="text-4xl mb-3">📭</p>
              <p className="text-white/30">No verification records found</p>
              <Link to="/verify" className="btn-primary mt-4 inline-flex">Start First Verification</Link>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-white/30 text-xs uppercase tracking-wider">
                    <th className="px-6 py-3 text-left">Session</th>
                    <th className="px-6 py-3 text-left">Doc Type</th>
                    <th className="px-6 py-3 text-left">Name</th>
                    <th className="px-6 py-3 text-center">Doc Score</th>
                    <th className="px-6 py-3 text-center">Face Sim.</th>
                    <th className="px-6 py-3 text-center">Status</th>
                    <th className="px-6 py-3 text-left">Time</th>
                    <th className="px-6 py-3 text-center">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/5">
                  {records.map((r) => (
                    <tr key={r.session_id} className="hover:bg-surface-700/30 transition-colors">
                      <td className="px-6 py-4 font-mono text-xs text-white/40">{r.session_id?.slice(0, 8)}…</td>
                      <td className="px-6 py-4 uppercase text-xs font-medium text-primary">{r.document_type}</td>
                      <td className="px-6 py-4 text-white/70 max-w-[120px] truncate">{r.extracted_fields?.name || '—'}</td>
                      <td className="px-6 py-4 text-center">
                        <ScorePill value={r.document_confidence_score} />
                      </td>
                      <td className="px-6 py-4 text-center">
                        <ScorePill value={r.similarity_score} />
                      </td>
                      <td className="px-6 py-4 text-center">
                        <StatusBadge status={r.final_decision} />
                      </td>
                      <td className="px-6 py-4 text-xs text-white/30">
                        {r.created_at ? new Date(r.created_at).toLocaleDateString() : '—'}
                      </td>
                      <td className="px-6 py-4 text-center">
                        <div className="flex items-center justify-center gap-2">
                          <Link to={`/result/${r.session_id}`} className="text-primary hover:underline text-xs">View</Link>
                          <button onClick={() => handleDelete(r.session_id)} className="text-danger/50 hover:text-danger text-xs transition-colors">Del</button>
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
            <div className="p-4 flex items-center justify-between border-t border-white/5 text-sm text-white/40">
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
    </div>
  )
}

function ScorePill({ value }) {
  if (value === null || value === undefined) return <span className="text-white/20">—</span>
  const pct = Math.round(value * 100)
  const color = pct >= 75 ? 'text-success' : pct >= 50 ? 'text-warning' : 'text-danger'
  return <span className={`font-mono font-semibold ${color}`}>{pct}%</span>
}
