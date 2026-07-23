import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  type DailyReport, type Order, type Table, type CashSession, type PeriodReport,
  fetchDailyReport, fetchHistory, fetchTables, fetchCurrentCash, fetchPeriodReport,
  openCash, addCashMovement, closeCash, getUser,
} from '../lib/api'
import { brl } from '../components/OrderDetailView'
import { maskCurrency, parseCurrency } from '../lib/format'
import { inputCls } from '../components/ui'
import { exportDailyReportCSV, printDailyReport } from '../lib/reportExport'

const METHOD_LABEL: Record<string, string> = {
  cash: 'Dinheiro', credit_card: 'Crédito', debit_card: 'Débito',
  pix: 'Pix', voucher: 'Voucher', other: 'Outro',
}

function todayISO() {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

function toISO(d: Date) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

function daysAgoISO(n: number) {
  const d = new Date()
  d.setDate(d.getDate() - n)
  return toISO(d)
}

function firstDayOfMonthISO() {
  const d = new Date()
  return toISO(new Date(d.getFullYear(), d.getMonth(), 1))
}

function fmtDatePt(iso: string) {
  return new Date(iso + 'T12:00:00').toLocaleDateString('pt-BR')
}

function timeOf(iso: string | null) {
  if (!iso) return ''
  return new Date(iso).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })
}

function StatCard({ label, value, hint, accent = 'amber' }: {
  label: string; value: string; hint?: string; accent?: 'amber' | 'green' | 'stone' | 'red'
}) {
  const c = { amber: 'text-amber-400', green: 'text-green-400', stone: 'text-stone-200', red: 'text-red-400' }[accent]
  return (
    <div className="rounded-2xl p-4 border border-stone-800/60" style={{ background: 'var(--color-app-surface)' }}>
      <p className="text-stone-500 text-[11px] font-semibold uppercase tracking-wider">{label}</p>
      <p className={['text-2xl font-black mt-1.5 leading-none', c].join(' ')}>{value}</p>
      {hint && <p className="text-stone-600 text-xs mt-1.5">{hint}</p>}
    </div>
  )
}

// ── Painel de Caixa ───────────────────────────────────────────────────────────

function CashPanel({ session, onRefresh }: { session: CashSession | null; onRefresh: () => void }) {
  const [mode, setMode] = useState<'idle' | 'open' | 'movement' | 'close'>('idle')
  const [openingAmount, setOpeningAmount] = useState('')
  const [openNotes, setOpenNotes] = useState('')
  const [movKind, setMovKind] = useState<'sangria' | 'suprimento'>('sangria')
  const [movAmount, setMovAmount] = useState('')
  const [movReason, setMovReason] = useState('')
  const [countedAmount, setCountedAmount] = useState('')
  const [closeNotes, setCloseNotes] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  function reset() { setMode('idle'); setError(null) }

  async function handleOpen(e: React.FormEvent) {
    e.preventDefault(); setSaving(true); setError(null)
    try {
      await openCash({
        opening_amount: parseCurrency(openingAmount) || 0,
        notes: openNotes.trim() || null,
      })
      reset(); onRefresh()
    } catch (err) { setError(err instanceof Error ? err.message : 'Erro') }
    finally { setSaving(false) }
  }

  async function handleMovement(e: React.FormEvent) {
    e.preventDefault(); setSaving(true); setError(null)
    try {
      await addCashMovement({
        kind: movKind,
        amount: parseCurrency(movAmount),
        reason: movReason.trim() || null,
      })
      reset(); onRefresh()
    } catch (err) { setError(err instanceof Error ? err.message : 'Erro') }
    finally { setSaving(false) }
  }

  async function handleClose(e: React.FormEvent) {
    e.preventDefault(); setSaving(true); setError(null)
    try {
      await closeCash({
        counted_amount: parseCurrency(countedAmount),
        notes: closeNotes.trim() || null,
      })
      reset(); onRefresh()
    } catch (err) { setError(err instanceof Error ? err.message : 'Erro') }
    finally { setSaving(false) }
  }

  const diff = session?.difference != null ? Number(session.difference) : null

  return (
    <div className="rounded-2xl border border-stone-800/60 overflow-hidden mb-5"
         style={{ background: 'var(--color-app-surface)' }}>
      {/* Header */}
      <div className="px-4 py-3 border-b border-stone-800/50 flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <div className={[
            'w-2 h-2 rounded-full',
            session?.status === 'open' ? 'bg-green-400' : 'bg-stone-600',
          ].join(' ')} />
          <h2 className="text-stone-200 text-sm font-bold">Controle de Caixa</h2>
          {session?.status === 'open' && (
            <span className="text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full
                             bg-green-500/10 text-green-400 border border-green-500/25">Aberto</span>
          )}
          {(!session || session.status === 'closed') && (
            <span className="text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full
                             bg-stone-800/60 text-stone-500 border border-stone-700/40">Fechado</span>
          )}
        </div>
        {session?.status === 'open' && mode === 'idle' && (
          <div className="flex gap-2">
            <button onClick={() => setMode('movement')}
              className="text-xs font-semibold text-stone-400 border border-stone-700/60 rounded-lg px-3 py-1.5
                         hover:bg-stone-800/50 transition-colors">
              Mov.
            </button>
            <button onClick={() => setMode('close')}
              className="text-xs font-semibold text-red-400 border border-red-500/30 rounded-lg px-3 py-1.5
                         hover:bg-red-500/10 transition-colors">
              Fechar caixa
            </button>
          </div>
        )}
      </div>

      {error && (
        <p className="text-red-400 text-xs bg-red-500/10 border border-red-500/20 rounded-xl mx-4 mt-3 px-3 py-2">
          {error}
        </p>
      )}

      {/* Caixa fechado — abrir */}
      {(!session || session.status === 'closed') && mode === 'idle' && (
        <div className="px-4 py-4">
          <p className="text-stone-600 text-xs mb-3">Nenhum caixa aberto hoje.</p>
          <button onClick={() => setMode('open')}
            className="px-4 py-2 rounded-xl text-sm font-semibold bg-amber-500 hover:bg-amber-400
                       text-stone-900 transition-colors">
            Abrir caixa
          </button>
        </div>
      )}

      {/* Form: abrir caixa */}
      {mode === 'open' && (
        <form onSubmit={handleOpen} className="px-4 py-4 space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-[11px] font-semibold text-stone-500 uppercase tracking-wider mb-1.5">
                Fundo de troco (R$)
              </label>
              <input type="text" inputMode="numeric" value={openingAmount}
                onChange={e => setOpeningAmount(maskCurrency(e.target.value))}
                placeholder="0,00" className={inputCls} style={{ background: 'var(--color-app-bg)' }} />
            </div>
            <div>
              <label className="block text-[11px] font-semibold text-stone-500 uppercase tracking-wider mb-1.5">
                Observação (opcional)
              </label>
              <input type="text" value={openNotes} onChange={e => setOpenNotes(e.target.value)}
                placeholder="…" className={inputCls} style={{ background: 'var(--color-app-bg)' }} />
            </div>
          </div>
          <div className="flex gap-2">
            <button type="button" onClick={reset}
              className="px-4 py-2 rounded-xl text-sm font-semibold text-stone-400 border border-stone-700/60
                         hover:bg-stone-800/50 transition-colors">
              Cancelar
            </button>
            <button type="submit" disabled={saving}
              className="px-6 py-2 rounded-xl text-sm font-semibold bg-amber-500 hover:bg-amber-400
                         text-stone-900 disabled:opacity-40 transition-colors">
              {saving ? 'Abrindo…' : 'Confirmar abertura'}
            </button>
          </div>
        </form>
      )}

      {/* Caixa aberto — resumo */}
      {session?.status === 'open' && mode === 'idle' && (
        <div className="px-4 py-3 space-y-2">
          <div className="grid grid-cols-4 gap-3">
            <div>
              <p className="text-stone-600 text-[10px] uppercase tracking-wider font-semibold">Fundo</p>
              <p className="text-stone-300 text-sm font-bold mt-0.5">{brl(session.opening_amount)}</p>
            </div>
            <div>
              <p className="text-stone-600 text-[10px] uppercase tracking-wider font-semibold">Vendas dinheiro</p>
              <p className="text-stone-300 text-sm font-bold mt-0.5">{brl(session.cash_sales)}</p>
            </div>
            <div>
              <p className="text-stone-600 text-[10px] uppercase tracking-wider font-semibold">Suprimentos</p>
              <p className="text-green-400 text-sm font-bold mt-0.5">+{brl(session.suprimentos)}</p>
            </div>
            <div>
              <p className="text-stone-600 text-[10px] uppercase tracking-wider font-semibold">Sangrias</p>
              <p className="text-red-400 text-sm font-bold mt-0.5">−{brl(session.sangrias)}</p>
            </div>
          </div>
          <div className="flex items-center justify-between pt-2 border-t border-stone-800/50">
            <span className="text-stone-400 text-xs font-semibold">Esperado em caixa</span>
            <span className="text-amber-400 text-sm font-bold">{brl(session.expected_so_far)}</span>
          </div>
          {session.movements.length > 0 && (
            <div className="space-y-1 pt-1">
              {session.movements.map(m => (
                <div key={m.id} className="flex items-center justify-between text-xs px-3 py-1.5 rounded-lg"
                     style={{ background: 'var(--color-app-bg)' }}>
                  <span className={m.kind === 'sangria' ? 'text-red-400' : 'text-green-400'}>
                    {m.kind === 'sangria' ? '↓ Sangria' : '↑ Suprimento'}
                    {m.reason && <span className="text-stone-600 ml-1.5">{m.reason}</span>}
                  </span>
                  <span className="text-stone-300 font-semibold">
                    {m.kind === 'sangria' ? '−' : '+'}{brl(m.amount)}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Form: sangria / suprimento */}
      {mode === 'movement' && (
        <form onSubmit={handleMovement} className="px-4 py-4 space-y-3">
          <div className="flex gap-1 p-1 rounded-xl" style={{ background: 'var(--color-app-bg)' }}>
            {(['sangria', 'suprimento'] as const).map(k => (
              <button key={k} type="button" onClick={() => setMovKind(k)}
                className={[
                  'flex-1 py-2 rounded-lg text-xs font-semibold transition-all',
                  movKind === k
                    ? k === 'sangria' ? 'bg-red-500/15 text-red-400' : 'bg-green-500/15 text-green-400'
                    : 'text-stone-500 hover:text-stone-300',
                ].join(' ')}>
                {k === 'sangria' ? '↓ Sangria (retirada)' : '↑ Suprimento (reforço)'}
              </button>
            ))}
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-[11px] font-semibold text-stone-500 uppercase tracking-wider mb-1.5">
                Valor (R$)
              </label>
              <input type="text" inputMode="numeric" required value={movAmount}
                onChange={e => setMovAmount(maskCurrency(e.target.value))}
                placeholder="0,00" className={inputCls} style={{ background: 'var(--color-app-bg)' }} />
            </div>
            <div>
              <label className="block text-[11px] font-semibold text-stone-500 uppercase tracking-wider mb-1.5">
                Motivo (opcional)
              </label>
              <input type="text" value={movReason} onChange={e => setMovReason(e.target.value)}
                placeholder="…" className={inputCls} style={{ background: 'var(--color-app-bg)' }} />
            </div>
          </div>
          <div className="flex gap-2">
            <button type="button" onClick={reset}
              className="px-4 py-2 rounded-xl text-sm font-semibold text-stone-400 border border-stone-700/60
                         hover:bg-stone-800/50 transition-colors">
              Cancelar
            </button>
            <button type="submit" disabled={saving}
              className="px-6 py-2 rounded-xl text-sm font-semibold bg-amber-500 hover:bg-amber-400
                         text-stone-900 disabled:opacity-40 transition-colors">
              {saving ? 'Salvando…' : 'Registrar'}
            </button>
          </div>
        </form>
      )}

      {/* Form: fechar caixa */}
      {mode === 'close' && (
        <form onSubmit={handleClose} className="px-4 py-4 space-y-3">
          <div className="rounded-xl px-3.5 py-3 text-sm" style={{ background: 'var(--color-app-bg)' }}>
            <p className="text-stone-500 text-xs mb-1">Esperado em caixa (dinheiro)</p>
            <p className="text-amber-400 text-xl font-black">{brl(session!.expected_so_far)}</p>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-[11px] font-semibold text-stone-500 uppercase tracking-wider mb-1.5">
                Valor contado (R$)
              </label>
              <input type="text" inputMode="numeric" required value={countedAmount}
                onChange={e => setCountedAmount(maskCurrency(e.target.value))}
                placeholder="0,00" className={inputCls} style={{ background: 'var(--color-app-bg)' }} autoFocus />
            </div>
            <div>
              <label className="block text-[11px] font-semibold text-stone-500 uppercase tracking-wider mb-1.5">
                Observação (opcional)
              </label>
              <input type="text" value={closeNotes} onChange={e => setCloseNotes(e.target.value)}
                placeholder="…" className={inputCls} style={{ background: 'var(--color-app-bg)' }} />
            </div>
          </div>
          {countedAmount && (
            <div className="flex justify-between text-xs px-1">
              <span className="text-stone-500">Diferença</span>
              {(() => {
                const diff = parseCurrency(countedAmount) - Number(session!.expected_so_far)
                return (
                  <span className={diff < 0 ? 'text-red-400 font-bold' : 'text-green-400 font-bold'}>
                    {diff >= 0 ? '+' : ''}{brl(diff)}
                  </span>
                )
              })()}
            </div>
          )}
          <div className="flex gap-2">
            <button type="button" onClick={reset}
              className="px-4 py-2 rounded-xl text-sm font-semibold text-stone-400 border border-stone-700/60
                         hover:bg-stone-800/50 transition-colors">
              Cancelar
            </button>
            <button type="submit" disabled={saving}
              className="px-6 py-2 rounded-xl text-sm font-semibold bg-red-500/80 hover:bg-red-500
                         text-stone-100 disabled:opacity-40 transition-colors">
              {saving ? 'Fechando…' : 'Fechar caixa'}
            </button>
          </div>
        </form>
      )}

      {/* Caixa fechado — mostrar resumo do último fechamento */}
      {session?.status === 'closed' && mode === 'idle' && session.closed_at && (
        <div className="px-4 py-3 space-y-1 text-xs">
          <div className="flex justify-between">
            <span className="text-stone-600">Fechado às</span>
            <span className="text-stone-400">{timeOf(session.closed_at)}</span>
          </div>
          {session.expected_amount != null && (
            <div className="flex justify-between">
              <span className="text-stone-600">Esperado</span>
              <span className="text-stone-400">{brl(session.expected_amount)}</span>
            </div>
          )}
          {session.counted_amount != null && (
            <div className="flex justify-between">
              <span className="text-stone-600">Contado</span>
              <span className="text-stone-400">{brl(session.counted_amount)}</span>
            </div>
          )}
          {diff != null && (
            <div className="flex justify-between font-bold">
              <span className="text-stone-500">Diferença</span>
              <span className={diff < 0 ? 'text-red-400' : diff > 0 ? 'text-green-400' : 'text-stone-400'}>
                {diff >= 0 ? '+' : ''}{brl(diff)}
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ── Relatório por período ────────────────────────────────────────────────────

function PeriodView({ report }: { report: PeriodReport }) {
  return (
    <>
      <div className="grid grid-cols-3 gap-3 mb-5">
        <StatCard label="Faturado" value={brl(report.revenue_total)} accent="green" />
        <StatCard label="Comandas" value={String(report.orders_count)} accent="stone" />
        <StatCard label="Ticket médio" value={brl(report.average_ticket)} accent="amber" />
      </div>

      <div className="rounded-2xl border border-stone-800/60 overflow-hidden mb-5"
           style={{ background: 'var(--color-app-surface)' }}>
        <div className="px-4 py-3 border-b border-stone-800/50">
          <h2 className="text-stone-200 text-sm font-bold">Por forma de pagamento</h2>
        </div>
        {report.by_payment_method.length === 0 ? (
          <p className="text-stone-600 text-xs px-4 py-4">Nenhum pagamento registrado no período</p>
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

      <div className="rounded-2xl border border-stone-800/60 overflow-hidden mb-5"
           style={{ background: 'var(--color-app-surface)' }}>
        <div className="px-4 py-3 border-b border-stone-800/50">
          <h2 className="text-stone-200 text-sm font-bold">Itens mais vendidos</h2>
        </div>
        {report.top_items.length === 0 ? (
          <p className="text-stone-600 text-xs px-4 py-4">Nada vendido no período</p>
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

      <div className="rounded-2xl border border-stone-800/60 overflow-hidden"
           style={{ background: 'var(--color-app-surface)' }}>
        <div className="px-4 py-3 border-b border-stone-800/50">
          <h2 className="text-stone-200 text-sm font-bold">Faturamento por dia</h2>
        </div>
        {report.daily_breakdown.length === 0 ? (
          <p className="text-stone-600 text-xs px-4 py-4">Nenhuma comanda fechada no período</p>
        ) : (
          report.daily_breakdown.map(d => (
            <div key={d.date} className="flex items-center justify-between px-4 py-2.5
                                          border-b border-stone-800/30 last:border-0">
              <span className="text-stone-300 text-sm">{fmtDatePt(d.date)}
                <span className="text-stone-600 text-xs ml-2">
                  ({d.orders_count} {d.orders_count === 1 ? 'comanda' : 'comandas'})
                </span>
              </span>
              <span className="text-stone-200 text-sm font-semibold">{brl(d.revenue_total)}</span>
            </div>
          ))
        )}
      </div>
    </>
  )
}

// ── Página Caixa ──────────────────────────────────────────────────────────────

export default function CaixaPage() {
  const navigate = useNavigate()
  const [scope, setScope] = useState<'day' | 'period'>('day')
  const [day, setDay] = useState(todayISO())
  const [periodStart, setPeriodStart] = useState(daysAgoISO(6))
  const [periodEnd, setPeriodEnd] = useState(todayISO())
  const [report, setReport] = useState<DailyReport | null>(null)
  const [periodReport, setPeriodReport] = useState<PeriodReport | null>(null)
  const [history, setHistory] = useState<Order[]>([])
  const [tables, setTables] = useState<Table[]>([])
  const [cashSession, setCashSession] = useState<CashSession | null | undefined>(undefined)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const refreshCash = useCallback(async () => {
    try {
      setCashSession(await fetchCurrentCash())
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro ao recarregar caixa')
    }
  }, [])

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      if (scope === 'period') {
        const [rep, ts] = await Promise.all([
          fetchPeriodReport(periodStart, periodEnd), fetchTables(),
        ])
        setPeriodReport(rep)
        setTables(ts)
        return
      }
      const [rep, hist, ts, cash] = await Promise.all([
        fetchDailyReport(day), fetchHistory(100, day), fetchTables(), fetchCurrentCash(),
      ])
      setReport(rep)
      setHistory(hist)
      setTables(ts)
      setCashSession(cash)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro ao carregar')
    } finally {
      setLoading(false)
    }
  }, [scope, day, periodStart, periodEnd])

  useEffect(() => { load() }, [load])

  return (
    <div className="h-full overflow-y-auto">
      <div className="max-w-3xl mx-auto px-4 sm:px-6 py-6">

        {/* Cabeçalho */}
        <div className="flex items-center justify-between gap-3 mb-4 flex-wrap">
          <div>
            <h1 className="text-stone-100 text-xl font-bold leading-tight">Caixa</h1>
            <p className="text-stone-500 text-sm mt-1">Faturamento e histórico de comandas</p>
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            {/* Dia único x Período */}
            <div className="flex gap-1 p-1 rounded-xl" style={{ background: 'var(--color-app-bg)' }}>
              <button onClick={() => setScope('day')}
                className={['px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors',
                  scope === 'day' ? 'bg-amber-500/15 text-amber-400' : 'text-stone-500 hover:text-stone-300'].join(' ')}>
                Dia
              </button>
              <button onClick={() => setScope('period')}
                className={['px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors',
                  scope === 'period' ? 'bg-amber-500/15 text-amber-400' : 'text-stone-500 hover:text-stone-300'].join(' ')}>
                Período
              </button>
            </div>

            {scope === 'day' ? (
              <>
                <input type="date" value={day} max={todayISO()} onChange={e => setDay(e.target.value)}
                  className="rounded-xl px-3 py-2 text-sm border border-stone-800/60 text-stone-200
                             focus:outline-none focus:border-amber-500/40 transition-all"
                  style={{ background: 'var(--color-app-surface)' }} />
                {report && (
                  <>
                    <button
                      onClick={() => exportDailyReportCSV(report, history, tables, day)}
                      title="Exportar CSV"
                      className="px-3 py-2 rounded-xl text-xs font-semibold border transition-colors
                                 text-stone-300 border-stone-700/60 hover:bg-stone-800/50 hover:border-stone-600">
                      CSV
                    </button>
                    <button
                      onClick={() => printDailyReport(report, history, tables, day, getUser()?.company_name ?? 'BarrioERP')}
                      title="Exportar PDF (imprimir e salvar como PDF)"
                      className="px-3 py-2 rounded-xl text-xs font-semibold border transition-colors
                                 text-stone-300 border-stone-700/60 hover:bg-stone-800/50 hover:border-stone-600">
                      PDF
                    </button>
                  </>
                )}
              </>
            ) : (
              <>
                <input type="date" value={periodStart} max={periodEnd} onChange={e => setPeriodStart(e.target.value)}
                  className="rounded-xl px-3 py-2 text-sm border border-stone-800/60 text-stone-200
                             focus:outline-none focus:border-amber-500/40 transition-all"
                  style={{ background: 'var(--color-app-surface)' }} />
                <span className="text-stone-600 text-xs">até</span>
                <input type="date" value={periodEnd} min={periodStart} max={todayISO()} onChange={e => setPeriodEnd(e.target.value)}
                  className="rounded-xl px-3 py-2 text-sm border border-stone-800/60 text-stone-200
                             focus:outline-none focus:border-amber-500/40 transition-all"
                  style={{ background: 'var(--color-app-surface)' }} />
              </>
            )}
          </div>
        </div>

        {scope === 'period' && (
          <div className="flex items-center gap-1.5 mb-6 flex-wrap">
            {[
              { label: '7 dias', start: daysAgoISO(6) },
              { label: '15 dias', start: daysAgoISO(14) },
              { label: '30 dias', start: daysAgoISO(29) },
              { label: 'Este mês', start: firstDayOfMonthISO() },
            ].map(p => (
              <button key={p.label}
                onClick={() => { setPeriodStart(p.start); setPeriodEnd(todayISO()) }}
                className="px-2.5 py-1 rounded-full text-[11px] font-semibold border transition-colors
                           text-stone-500 border-stone-700/60 hover:bg-stone-800/50 hover:text-stone-300">
                {p.label}
              </button>
            ))}
          </div>
        )}

        {error && (
          <div className="flex items-center gap-3 bg-red-500/10 border border-red-500/20
                          text-red-400 text-sm rounded-2xl px-4 py-3 mb-6">
            {error}
            <button onClick={load} className="ml-auto text-xs underline underline-offset-2">Tentar</button>
          </div>
        )}

        {/* Painel de caixa (sempre visível, só carrega quando day === hoje) */}
        {scope === 'day' && cashSession !== undefined && day === todayISO() && (
          <CashPanel session={cashSession} onRefresh={refreshCash} />
        )}

        {loading ? (
          <div className="text-center py-16 text-stone-600 text-sm">Carregando…</div>
        ) : scope === 'period' ? (
          periodReport && <PeriodView report={periodReport} />
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
                 style={{ background: 'var(--color-app-surface)' }}>
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
                 style={{ background: 'var(--color-app-surface)' }}>
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
                 style={{ background: 'var(--color-app-surface)' }}>
              <div className="px-4 py-3 border-b border-stone-800/50">
                <h2 className="text-stone-200 text-sm font-bold">
                  Comandas fechadas {day !== todayISO() ? `em ${new Date(day + 'T12:00:00').toLocaleDateString('pt-BR')}` : 'hoje'}
                </h2>
              </div>
              {history.length === 0 ? (
                <p className="text-stone-600 text-xs px-4 py-4">Nenhuma comanda fechada no período</p>
              ) : (
                history.map(o => {
                  const table = tables.find(t => t.id === o.table_id)
                  const items = o.items.filter(i => i.status !== 'cancelled').length
                  return (
                    <button key={o.id} onClick={() => navigate(`/comanda/${o.id}`)}
                      className="w-full flex items-center justify-between gap-3 px-4 py-3
                                 border-b border-stone-800/30 last:border-0 hover:bg-stone-800/30 transition-colors text-left">
                      <div className="min-w-0">
                        <div className="flex items-center gap-1.5">
                          <p className="text-stone-200 text-sm font-medium truncate">
                            {o.customer_name ?? table?.label ?? 'Comanda avulsa'}
                          </p>
                          {o.is_fiado && (
                            <span className="shrink-0 text-[9px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded-full
                                             text-amber-400 bg-amber-500/15 border border-amber-500/30">
                              Fiado
                            </span>
                          )}
                        </div>
                        <p className="text-stone-600 text-xs mt-0.5">
                          {table ? `Mesa ${table.number}` : 'Balcão'} · {items} {items === 1 ? 'item' : 'itens'}
                          {o.closed_at ? ` · ${timeOf(o.closed_at)}` : ''}
                        </p>
                      </div>
                      <span className={['text-sm font-bold shrink-0', o.is_fiado ? 'text-amber-400' : 'text-stone-300'].join(' ')}>
                        {brl(o.total)}
                      </span>
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
