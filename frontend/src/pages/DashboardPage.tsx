import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  type Order, type Table,
  fetchOpenOrders, fetchTables, getUser,
} from '../lib/api'

// ── Helpers ───────────────────────────────────────────────────────────────────

function brl(v: string | number) {
  return Number(v).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })
}

function timeAgo(iso: string) {
  const diff = Date.now() - new Date(iso).getTime()
  const m = Math.floor(diff / 60000)
  if (m < 1) return 'agora'
  if (m < 60) return `${m}min`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h}h`
  return `${Math.floor(h / 24)}d`
}

function greeting() {
  const h = new Date().getHours()
  if (h < 12) return 'Bom dia'
  if (h < 18) return 'Boa tarde'
  return 'Boa noite'
}

// ── Card de métrica ───────────────────────────────────────────────────────────

function StatCard({
  label, value, hint, accent = 'amber', onClick,
}: {
  label: string
  value: string
  hint?: string
  accent?: 'amber' | 'green' | 'orange' | 'stone'
  onClick?: () => void
}) {
  const accentText = {
    amber: 'text-amber-400',
    green: 'text-green-400',
    orange: 'text-orange-400',
    stone: 'text-stone-200',
  }[accent]

  return (
    <button
      onClick={onClick}
      disabled={!onClick}
      className={[
        'text-left rounded-2xl p-4 border border-stone-800/60 transition-all',
        onClick ? 'hover:border-stone-700/70 hover:bg-stone-800/20 cursor-pointer' : 'cursor-default',
      ].join(' ')}
      style={{ background: '#161210' }}
    >
      <p className="text-stone-500 text-[11px] font-semibold uppercase tracking-wider">{label}</p>
      <p className={['text-2xl font-black mt-1.5 leading-none', accentText].join(' ')}>{value}</p>
      {hint && <p className="text-stone-600 text-xs mt-1.5">{hint}</p>}
    </button>
  )
}

// ── Página ────────────────────────────────────────────────────────────────────

export default function DashboardPage() {
  const [orders, setOrders] = useState<Order[]>([])
  const [tables, setTables] = useState<Table[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const navigate = useNavigate()
  const user = getUser()

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [os, ts] = await Promise.all([fetchOpenOrders(), fetchTables()])
      setOrders(os)
      setTables(ts)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro ao carregar')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  // Auto-refresh silencioso a cada 30s
  useEffect(() => {
    const id = setInterval(async () => {
      try {
        const [os, ts] = await Promise.all([fetchOpenOrders(), fetchTables()])
        setOrders(os)
        setTables(ts)
      } catch {}
    }, 30_000)
    return () => clearInterval(id)
  }, [])

  // Métricas derivadas dos dados ao vivo
  const openCount = orders.length
  const billRequested = orders.filter(o => o.status === 'bill_requested').length
  const openTotal = orders.reduce((sum, o) => sum + Number(o.total), 0)
  const avgTicket = openCount > 0 ? openTotal / openCount : 0

  const activeTables = tables.filter(t => t.is_active)
  const occupied = activeTables.filter(t => t.status === 'occupied' || t.status === 'bill_requested').length
  const free = activeTables.filter(t => t.status === 'free').length
  const occupancyPct = activeTables.length > 0 ? Math.round((occupied / activeTables.length) * 100) : 0

  // Comandas abertas há mais tempo (atenção do garçom)
  const oldest = [...orders]
    .sort((a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime())
    .slice(0, 5)

  return (
    <div className="h-full overflow-y-auto">
      <div className="max-w-4xl mx-auto px-4 sm:px-6 py-6">

        {/* Cabeçalho */}
        <div className="flex items-start justify-between mb-6">
          <div>
            <h1 className="text-stone-100 text-xl font-bold leading-tight">
              {greeting()}{user?.name ? `, ${user.name.split(' ')[0]}` : ''} 👋
            </h1>
            <p className="text-stone-500 text-sm mt-1">Visão ao vivo da operação</p>
          </div>
          <button onClick={load} disabled={loading}
            className="flex items-center justify-center w-9 h-9 rounded-xl
                       border border-stone-800/60 text-stone-500 hover:text-stone-300
                       hover:border-stone-700/60 disabled:opacity-40 transition-all"
            style={{ background: '#161210' }}>
            <svg className={['w-4 h-4', loading ? 'animate-spin' : ''].join(' ')}
                 fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round"
                    d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
          </button>
        </div>

        {error && (
          <div className="flex items-center gap-3 bg-red-500/10 border border-red-500/20
                          text-red-400 text-sm rounded-2xl px-4 py-3 mb-6">
            {error}
            <button onClick={load} className="ml-auto text-xs underline underline-offset-2">Tentar</button>
          </div>
        )}

        {loading ? (
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="rounded-2xl p-4 border border-stone-800/60 animate-pulse"
                   style={{ background: '#161210' }}>
                <div className="w-20 h-3 bg-stone-800 rounded" />
                <div className="w-16 h-7 bg-stone-800 rounded mt-3" />
                <div className="w-24 h-3 bg-stone-800 rounded mt-3" />
              </div>
            ))}
          </div>
        ) : (
          <>
            {/* Métricas */}
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-6">
              <StatCard
                label="Em aberto"
                value={brl(openTotal)}
                hint={`${openCount} ${openCount === 1 ? 'comanda' : 'comandas'}`}
                accent="amber"
                onClick={() => navigate('/pedidos')}
              />
              <StatCard
                label="Ticket médio"
                value={brl(avgTicket)}
                hint="por comanda aberta"
                accent="stone"
              />
              <StatCard
                label="Contas pedidas"
                value={String(billRequested)}
                hint={billRequested > 0 ? 'aguardando pagamento' : 'nenhuma pendente'}
                accent="orange"
                onClick={() => navigate('/pedidos')}
              />
              <StatCard
                label="Ocupação"
                value={`${occupancyPct}%`}
                hint={`${occupied} ocupadas · ${free} livres`}
                accent="green"
                onClick={() => navigate('/mesas')}
              />
            </div>

            {/* Comandas que precisam de atenção */}
            <div className="rounded-2xl border border-stone-800/60 overflow-hidden"
                 style={{ background: '#161210' }}>
              <div className="px-4 py-3 border-b border-stone-800/50 flex items-center justify-between">
                <h2 className="text-stone-200 text-sm font-bold">Comandas abertas há mais tempo</h2>
                <button onClick={() => navigate('/pedidos')}
                  className="text-amber-400/80 hover:text-amber-400 text-xs font-semibold transition-colors">
                  Ver todas →
                </button>
              </div>

              {oldest.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-12 text-center px-4">
                  <div className="w-12 h-12 rounded-2xl bg-stone-800/60 flex items-center justify-center mb-3 text-2xl">
                    ✨
                  </div>
                  <p className="text-stone-400 text-sm font-medium">Nenhuma comanda aberta</p>
                  <p className="text-stone-600 text-xs mt-1">Tudo tranquilo por aqui</p>
                </div>
              ) : (
                oldest.map(o => {
                  const table = tables.find(t => t.id === o.table_id)
                  return (
                    <button key={o.id} onClick={() => navigate('/pedidos')}
                      className="w-full flex items-center justify-between gap-3 px-4 py-3
                                 border-b border-stone-800/30 last:border-0
                                 hover:bg-stone-800/30 transition-colors text-left">
                      <div className="flex items-center gap-3 min-w-0">
                        <span className="text-lg font-black text-stone-100 leading-none shrink-0 w-7">
                          {table?.number ?? '—'}
                        </span>
                        <div className="min-w-0">
                          <p className="text-stone-200 text-sm font-medium truncate">
                            {o.customer_name ?? table?.label ?? 'Comanda'}
                          </p>
                          <p className="text-stone-600 text-xs mt-0.5">
                            aberta há {timeAgo(o.created_at)}
                            {o.status === 'bill_requested' && (
                              <span className="text-orange-400/80"> · conta pedida</span>
                            )}
                          </p>
                        </div>
                      </div>
                      <span className="text-amber-400 text-sm font-bold shrink-0">{brl(o.total)}</span>
                    </button>
                  )
                })
              )}
            </div>
          </>
        )}
      </div>
    </div>
  )
}
