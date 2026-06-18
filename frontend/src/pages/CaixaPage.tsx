import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  type DailyReport, type Order, type Table,
  fetchDailyReport, fetchHistory, fetchTables,
} from '../lib/api'
import { brl } from '../components/OrderDetailView'

const METHOD_LABEL: Record<string, string> = {
  cash: 'Dinheiro', credit_card: 'Crédito', debit_card: 'Débito',
  pix: 'Pix', voucher: 'Voucher', other: 'Outro',
}

function todayISO() {
  // Data local (America/Sao_Paulo via offset do navegador)
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

function timeOf(iso: string | null) {
  if (!iso) return ''
  return new Date(iso).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })
}

function StatCard({ label, value, hint, accent = 'amber' }: {
  label: string; value: string; hint?: string; accent?: 'amber' | 'green' | 'stone'
}) {
  const c = { amber: 'text-amber-400', green: 'text-green-400', stone: 'text-stone-200' }[accent]
  return (
    <div className="rounded-2xl p-4 border border-stone-800/60" style={{ background: '#161210' }}>
      <p className="text-stone-500 text-[11px] font-semibold uppercase tracking-wider">{label}</p>
      <p className={['text-2xl font-black mt-1.5 leading-none', c].join(' ')}>{value}</p>
      {hint && <p className="text-stone-600 text-xs mt-1.5">{hint}</p>}
    </div>
  )
}

export default function CaixaPage() {
  const navigate = useNavigate()
  const [day, setDay] = useState(todayISO())
  const [report, setReport] = useState<DailyReport | null>(null)
  const [history, setHistory] = useState<Order[]>([])
  const [tables, setTables] = useState<Table[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [rep, hist, ts] = await Promise.all([
        fetchDailyReport(day), fetchHistory(50), fetchTables(),
      ])
      setReport(rep)
      setHistory(hist)
      setTables(ts)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro ao carregar')
    } finally {
      setLoading(false)
    }
  }, [day])

  useEffect(() => { load() }, [load])

  return (
    <div className="h-full overflow-y-auto">
      <div className="max-w-3xl mx-auto px-4 sm:px-6 py-6">

        {/* Cabeçalho */}
        <div className="flex items-center justify-between gap-3 mb-6 flex-wrap">
          <div>
            <h1 className="text-stone-100 text-xl font-bold leading-tight">Caixa</h1>
            <p className="text-stone-500 text-sm mt-1">Faturamento e histórico de comandas</p>
          </div>
          <input type="date" value={day} max={todayISO()} onChange={e => setDay(e.target.value)}
            className="rounded-xl px-3 py-2 text-sm border border-stone-800/60 text-stone-200
                       focus:outline-none focus:border-amber-500/40 transition-all"
            style={{ background: '#161210' }} />
        </div>

        {error && (
          <div className="flex items-center gap-3 bg-red-500/10 border border-red-500/20
                          text-red-400 text-sm rounded-2xl px-4 py-3 mb-6">
            {error}
            <button onClick={load} className="ml-auto text-xs underline underline-offset-2">Tentar</button>
          </div>
        )}

        {loading ? (
          <div className="text-center py-16 text-stone-600 text-sm">Carregando…</div>
        ) : report && (
          <>
            {/* Métricas do dia */}
            <div className="grid grid-cols-3 gap-3 mb-5">
              <StatCard label="Faturado" value={brl(report.revenue_total)} accent="green" />
              <StatCard label="Comandas" value={String(report.orders_count)} accent="stone" />
              <StatCard label="Ticket médio" value={brl(report.average_ticket)} accent="amber" />
            </div>

            {/* Por forma de pagamento */}
            <div className="rounded-2xl border border-stone-800/60 overflow-hidden mb-5"
                 style={{ background: '#161210' }}>
              <div className="px-4 py-3 border-b border-stone-800/50">
                <h2 className="text-stone-200 text-sm font-bold">Por forma de pagamento</h2>
              </div>
              {report.by_payment_method.length === 0 ? (
                <p className="text-stone-600 text-xs px-4 py-4">Nenhum pagamento registrado no dia</p>
              ) : (
                report.by_payment_method.map(m => (
                  <div key={m.method} className="flex items-center justify-between px-4 py-2.5
                                                  border-b border-stone-800/30 last:border-0">
                    <span className="text-stone-300 text-sm">{METHOD_LABEL[m.method] ?? m.method}
                      <span className="text-stone-600 text-xs ml-2">({m.count})</span>
                    </span>
                    <span className="text-stone-200 text-sm font-semibold">{brl(m.total)}</span>
                  </div>
                ))
              )}
            </div>

            {/* Itens mais vendidos */}
            <div className="rounded-2xl border border-stone-800/60 overflow-hidden mb-5"
                 style={{ background: '#161210' }}>
              <div className="px-4 py-3 border-b border-stone-800/50">
                <h2 className="text-stone-200 text-sm font-bold">Itens mais vendidos</h2>
              </div>
              {report.top_items.length === 0 ? (
                <p className="text-stone-600 text-xs px-4 py-4">Nada vendido no dia</p>
              ) : (
                report.top_items.map((it, i) => (
                  <div key={it.name} className="flex items-center justify-between gap-3 px-4 py-2.5
                                                border-b border-stone-800/30 last:border-0">
                    <div className="flex items-center gap-3 min-w-0">
                      <span className="text-stone-600 text-xs font-bold w-4 shrink-0">{i + 1}</span>
                      <span className="text-stone-300 text-sm truncate">{it.name}</span>
                    </div>
                    <div className="flex items-center gap-3 shrink-0">
                      <span className="text-amber-400 text-sm font-bold">{it.quantity}×</span>
                      <span className="text-stone-500 text-xs w-20 text-right">{brl(it.total)}</span>
                    </div>
                  </div>
                ))
              )}
            </div>

            {/* Histórico de comandas fechadas */}
            <div className="rounded-2xl border border-stone-800/60 overflow-hidden"
                 style={{ background: '#161210' }}>
              <div className="px-4 py-3 border-b border-stone-800/50">
                <h2 className="text-stone-200 text-sm font-bold">Últimas comandas fechadas</h2>
              </div>
              {history.length === 0 ? (
                <p className="text-stone-600 text-xs px-4 py-4">Nenhuma comanda fechada ainda</p>
              ) : (
                history.map(o => {
                  const table = tables.find(t => t.id === o.table_id)
                  const items = o.items.filter(i => i.status !== 'cancelled').length
                  return (
                    <button key={o.id} onClick={() => navigate(`/comanda/${o.id}`)}
                      className="w-full flex items-center justify-between gap-3 px-4 py-3
                                 border-b border-stone-800/30 last:border-0 hover:bg-stone-800/30 transition-colors text-left">
                      <div className="min-w-0">
                        <p className="text-stone-200 text-sm font-medium truncate">
                          {o.customer_name ?? table?.label ?? 'Comanda avulsa'}
                        </p>
                        <p className="text-stone-600 text-xs mt-0.5">
                          {table ? `Mesa ${table.number}` : 'Balcão'} · {items} {items === 1 ? 'item' : 'itens'}
                          {o.closed_at ? ` · ${timeOf(o.closed_at)}` : ''}
                        </p>
                      </div>
                      <span className="text-stone-300 text-sm font-bold shrink-0">{brl(o.total)}</span>
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
