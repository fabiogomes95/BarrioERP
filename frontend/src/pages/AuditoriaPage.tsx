import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { type AuditLogEntry, fetchAuditLogs } from '../lib/api'
import { AdminTabs } from '../components/ui'

function brl(v: string | number) {
  return Number(v).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })
}

function safeParse(json: string | null): Record<string, any> | null {
  if (!json) return null
  try { return JSON.parse(json) } catch { return null }
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

const ACTION_CONFIG: Record<string, { label: string; color: string; bg: string }> = {
  'order.open':                  { label: 'Comanda aberta',      color: 'text-green-400',  bg: 'bg-green-500/10' },
  'order.close':                 { label: 'Fechada em fiado',    color: 'text-amber-400',  bg: 'bg-amber-500/10' },
  'order.finish':                { label: 'Comanda finalizada',  color: 'text-green-400',  bg: 'bg-green-500/10' },
  'order.reopen':                { label: 'Comanda reaberta',    color: 'text-blue-400',   bg: 'bg-blue-500/10' },
  'order.cancel':                { label: 'Comanda apagada',     color: 'text-red-400',    bg: 'bg-red-500/10' },
  'order_item.add':              { label: 'Item adicionado',     color: 'text-green-400',  bg: 'bg-green-500/10' },
  'order_item.cancel':           { label: 'Item cancelado',      color: 'text-red-400',    bg: 'bg-red-500/10' },
  'order_item.quantity_change':  { label: 'Quantidade alterada', color: 'text-amber-400',  bg: 'bg-amber-500/10' },
  'payment.register':            { label: 'Pagamento recebido',  color: 'text-green-400',  bg: 'bg-green-500/10' },
}

const FILTERS: { key: string; label: string }[] = [
  { key: '',                          label: 'Todos' },
  { key: 'order_item.add',            label: 'Itens adicionados' },
  { key: 'order_item.cancel',         label: 'Itens cancelados' },
  { key: 'order_item.quantity_change', label: 'Qtd. alterada' },
  { key: 'payment.register',          label: 'Pagamentos' },
  { key: 'order.open',                label: 'Comandas abertas' },
  { key: 'order.finish',              label: 'Comandas finalizadas' },
  { key: 'order.close',               label: 'Fechadas em fiado' },
  { key: 'order.cancel',              label: 'Comandas apagadas' },
]

const PAYMENT_METHOD_LABEL: Record<string, string> = {
  cash: 'Dinheiro', credit_card: 'Crédito', debit_card: 'Débito', pix: 'Pix', voucher: 'Voucher', other: 'Outro',
}

function extractOrderId(entry: AuditLogEntry): string | null {
  if (entry.resource_type === 'order') return entry.resource_id
  const after = safeParse(entry.after)
  const before = safeParse(entry.before)
  return after?.order_id ?? after?.order?.order_id ?? before?.order?.order_id ?? null
}

/** Nome do cliente/mesa a que a ação se refere (não confundir com quem executou a ação). */
function extractCustomerName(entry: AuditLogEntry): string | null {
  const after = safeParse(entry.after)
  const before = safeParse(entry.before)
  return after?.customer_name ?? after?.order?.customer_name
    ?? before?.customer_name ?? before?.order?.customer_name ?? null
}

function summarize(entry: AuditLogEntry): string {
  const after = safeParse(entry.after)
  const before = safeParse(entry.before)
  switch (entry.action) {
    case 'order_item.add':
      return `${after?.quantity}x ${after?.item_name} — ${brl(after?.unit_price ?? 0)}`
    case 'order_item.cancel': {
      const name = after?.item?.item_name ?? before?.item?.item_name
      const qty = before?.item?.quantity
      const reason = after?.item?.reason
      if (!name) return `Registro antigo, sem detalhes do item${reason ? ` — motivo: ${reason}` : ''}`
      return `${qty ? `${qty}x ` : ''}${name}${reason ? ` — motivo: ${reason}` : ''}`
    }
    case 'order_item.quantity_change':
      return `${before?.item_name ?? '?'}: ${before?.quantity} → ${after?.quantity}`
    case 'payment.register': {
      const method = PAYMENT_METHOD_LABEL[after?.method] ?? after?.method ?? ''
      const change = Number(after?.change_given ?? 0)
      return `${method} — ${brl(after?.amount ?? 0)}${change > 0 ? ` (troco ${brl(change)})` : ''}`
    }
    case 'order.finish':
    case 'order.close':
    case 'order.cancel':
      return after?.total ? `Total: ${brl(after.total)}` : ''
    default:
      return ''
  }
}

export default function AuditoriaPage() {
  const navigate = useNavigate()
  const [entries, setEntries] = useState<AuditLogEntry[]>([])
  const [filter, setFilter] = useState('')
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async (p: number, replace: boolean) => {
    try {
      const res = await fetchAuditLogs({ page: p, pageSize: 50, action: filter || undefined })
      setEntries(prev => replace ? res.items : [...prev, ...res.items])
      setTotal(res.total)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro ao carregar auditoria')
    }
  }, [filter])

  // Carrega ao trocar filtro
  useEffect(() => {
    setLoading(true)
    setPage(1)
    load(1, true).finally(() => setLoading(false))
  }, [load])

  // Auto-refresh silencioso a cada 20s (só a primeira página, pra pegar eventos novos)
  useEffect(() => {
    const id = setInterval(() => { load(1, true) }, 20_000)
    return () => clearInterval(id)
  }, [load])

  async function loadMore() {
    setLoadingMore(true)
    const next = page + 1
    await load(next, false)
    setPage(next)
    setLoadingMore(false)
  }

  return (
    <div className="h-full overflow-y-auto">
      <div className="max-w-3xl mx-auto px-4 sm:px-6 py-6">
        <div className="mb-4">
          <h1 className="text-stone-100 text-xl font-bold leading-tight">Auditoria</h1>
          <p className="text-stone-500 text-sm mt-1">Histórico de tudo que foi feito nas comandas</p>
        </div>

        <AdminTabs />

        <div className="flex items-center justify-between gap-3 mb-4 flex-wrap">
          <p className="text-stone-500 text-xs">
            {loading ? 'Carregando…' : `${total} registro${total !== 1 ? 's' : ''}`}
          </p>
          <div className="flex gap-1.5 flex-wrap">
            {FILTERS.map(f => (
              <button key={f.key} onClick={() => setFilter(f.key)}
                className={[
                  'px-3 py-1 rounded-full text-xs font-semibold transition-all border',
                  filter === f.key
                    ? 'bg-amber-500/15 text-amber-400 border-amber-500/30'
                    : 'text-stone-500 border-stone-800/60 hover:text-stone-300',
                ].join(' ')}>
                {f.label}
              </button>
            ))}
          </div>
        </div>

        {error && (
          <div className="bg-red-500/10 border border-red-500/20 text-red-400 text-sm rounded-2xl px-4 py-3 mb-4">
            {error}
          </div>
        )}

        {loading ? (
          <div className="text-center py-16 text-stone-600 text-sm">Carregando…</div>
        ) : entries.length === 0 ? (
          <div className="text-center py-16">
            <p className="text-stone-500 text-sm">Nenhum registro encontrado</p>
          </div>
        ) : (
          <>
            <div className="rounded-2xl border border-stone-800/60 overflow-hidden" style={{ background: 'var(--color-app-surface)' }}>
              {entries.map(entry => {
                const cfg = ACTION_CONFIG[entry.action] ?? { label: entry.action, color: 'text-stone-400', bg: 'bg-stone-500/10' }
                const orderId = extractOrderId(entry)
                const customerName = extractCustomerName(entry)
                const summary = summarize(entry)
                return (
                  <div key={entry.id}
                    onClick={() => orderId && navigate(`/comanda/${orderId}`)}
                    className={[
                      'flex items-start gap-3 px-4 py-3 border-b border-stone-800/30 last:border-0',
                      orderId ? 'cursor-pointer hover:bg-stone-800/30 transition-colors' : '',
                    ].join(' ')}>
                    <span className={['shrink-0 mt-0.5 text-[10px] font-bold uppercase tracking-wider px-2 py-1 rounded-full', cfg.color, cfg.bg].join(' ')}>
                      {cfg.label}
                    </span>
                    <div className="flex-1 min-w-0">
                      {(customerName || summary) && (
                        <p className="text-stone-300 text-sm truncate">
                          {customerName && <span className="font-semibold text-stone-200">{customerName}</span>}
                          {customerName && summary && <span className="text-stone-600"> · </span>}
                          {summary}
                        </p>
                      )}
                      <p className="text-stone-600 text-xs mt-0.5">
                        {entry.user_name ?? 'Sistema'} · {timeAgo(entry.created_at)} · {new Date(entry.created_at).toLocaleString('pt-BR')}
                      </p>
                    </div>
                  </div>
                )
              })}
            </div>

            {entries.length < total && (
              <button onClick={loadMore} disabled={loadingMore}
                className="w-full mt-3 py-2.5 rounded-xl text-sm font-semibold
                           text-stone-400 border border-stone-800/60 hover:bg-stone-800/50
                           disabled:opacity-40 transition-colors">
                {loadingMore ? 'Carregando…' : 'Carregar mais'}
              </button>
            )}
          </>
        )}
      </div>
    </div>
  )
}
