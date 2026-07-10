import { useEffect, useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  type FiadoCustomerGroup,
  fetchFiadoGrouped, fetchOrderPayments, registerPayment, reopenOrder,
  type Payment, type PaymentMethod,
} from '../lib/api'
import { maskCurrency, parseCurrency, toCurrencyInput } from '../lib/format'
import { inputCls, ErrorBanner, Spinner } from '../components/ui'

function brl(v: string | number) {
  return Number(v).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })
}

const ORDER_TYPE_LABEL: Record<string, string> = {
  counter: 'Consumo no local',
  delivery: 'Delivery',
  pickup: 'Retirada',
}

const PAYMENT_METHODS: { value: PaymentMethod; label: string; icon: string }[] = [
  { value: 'cash',        label: 'Dinheiro', icon: '💵' },
  { value: 'credit_card', label: 'Crédito',  icon: '💳' },
  { value: 'debit_card',  label: 'Débito',   icon: '💳' },
  { value: 'pix',         label: 'Pix',      icon: '⚡' },
  { value: 'voucher',     label: 'Voucher',  icon: '🎟️' },
]

const METHOD_LABEL: Record<string, string> = Object.fromEntries(
  PAYMENT_METHODS.map(m => [m.value, m.label]),
)

// ── Modal de pagamento do fiado ───────────────────────────────────────────────

function FiadoPaymentModal({
  entry,
  onClose,
  onPaid,
}: {
  entry: { order_id: string; total: string | number; paid: string | number; table_number?: number | null; customer_name?: string | null }
  onClose: () => void
  onPaid: () => void
}) {
  const [payments, setPayments] = useState<Payment[]>([])
  const [loading, setLoading] = useState(true)
  const [method, setMethod] = useState<PaymentMethod>('cash')
  const [amount, setAmount] = useState('')
  const [tendered, setTendered] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [livePaid, setLivePaid] = useState(Number(entry.paid))
  const total = Number(entry.total)
  const remaining = Math.max(0, Math.round((total - livePaid) * 100) / 100)
  const fullyPaid = remaining <= 0

  const tenderedNum = parseCurrency(tendered)
  const amountNum = parseCurrency(amount)
  const change =
    method === 'cash' && !isNaN(tenderedNum) && !isNaN(amountNum) && tenderedNum > amountNum
      ? tenderedNum - amountNum
      : 0

  const refresh = useCallback(async () => {
    const ps = await fetchOrderPayments(entry.order_id)
    setPayments(ps)
    const paid = ps.filter(p => p.status === 'confirmed').reduce((s, p) => s + Number(p.amount), 0)
    setLivePaid(paid)
    return paid
  }, [entry.order_id])

  useEffect(() => {
    refresh().finally(() => setLoading(false))
  }, [refresh])

  useEffect(() => {
    if (!loading) setAmount(remaining > 0 ? toCurrencyInput(remaining) : '')
  }, [remaining, loading])

  useEffect(() => {
    const h = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', h)
    return () => document.removeEventListener('keydown', h)
  }, [onClose])

  async function handlePay(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    const value = parseCurrency(amount)
    if (isNaN(value) || value <= 0) { setError('Informe um valor válido'); return }

    setSaving(true)
    try {
      await registerPayment({
        order_id: entry.order_id,
        method,
        amount: value.toFixed(2),
        amount_tendered: method === 'cash' && !isNaN(tenderedNum) ? tenderedNum.toFixed(2) : null,
      })
      const newPaid = await refresh()
      setTendered('')
      if (newPaid >= total) onPaid()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro ao registrar pagamento')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-4"
         style={{ background: 'rgba(0,0,0,0.75)', backdropFilter: 'blur(4px)' }}
         onClick={onClose}>
      <div className="w-full max-w-md rounded-3xl border border-stone-800/70 p-5"
           style={{ background: '#161210' }}
           onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <div>
            <h2 className="text-stone-100 text-base font-bold">Receber fiado</h2>
            <p className="text-stone-500 text-xs mt-0.5">
              {entry.table_number ? `Mesa ${entry.table_number}` : entry.customer_name ?? '—'}
            </p>
          </div>
          <button onClick={onClose} className="text-stone-600 hover:text-stone-400 transition-colors">
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="rounded-2xl p-4 mb-4 space-y-1.5" style={{ background: '#0d0b08' }}>
          <div className="flex justify-between text-sm">
            <span className="text-stone-500">Total da conta</span>
            <span className="text-stone-200 font-semibold">{brl(total)}</span>
          </div>
          <div className="flex justify-between text-sm">
            <span className="text-stone-500">Já pago</span>
            <span className="text-green-400 font-semibold">{brl(livePaid)}</span>
          </div>
          <div className="flex justify-between pt-1.5 border-t border-stone-800/60">
            <span className="text-stone-300 text-sm font-bold">{fullyPaid ? 'Quitada!' : 'Falta'}</span>
            <span className={['text-base font-black', fullyPaid ? 'text-green-400' : 'text-amber-400'].join(' ')}>
              {brl(remaining)}
            </span>
          </div>
        </div>

        {error && (
          <p className="text-red-400 text-xs bg-red-500/10 border border-red-500/20 rounded-xl px-3 py-2 mb-3">
            {error}
          </p>
        )}

        {payments.length > 0 && (
          <div className="space-y-1 mb-4">
            {payments.map(p => (
              <div key={p.id} className="flex items-center justify-between text-xs px-3 py-2 rounded-lg"
                   style={{ background: '#0d0b08' }}>
                <span className="text-stone-400">{METHOD_LABEL[p.method] ?? p.method}</span>
                <span className="text-stone-300 font-semibold">{brl(p.amount)}</span>
              </div>
            ))}
          </div>
        )}

        {loading ? (
          <div className="text-center py-6 text-stone-600 text-sm">Carregando…</div>
        ) : fullyPaid ? (
          <div className="text-center py-4">
            <p className="text-green-400 font-bold text-base">✓ Conta quitada!</p>
            <button onClick={onPaid}
              className="mt-3 w-full py-2.5 rounded-xl text-sm font-semibold
                         bg-green-500 hover:bg-green-400 text-stone-900 transition-colors">
              Fechar
            </button>
          </div>
        ) : (
          <form onSubmit={handlePay} className="space-y-3">
            <div className="grid grid-cols-5 gap-1.5">
              {PAYMENT_METHODS.map(m => (
                <button key={m.value} type="button" onClick={() => setMethod(m.value)}
                  className={[
                    'flex flex-col items-center gap-1 py-2 rounded-xl text-[10px] font-semibold transition-all border',
                    method === m.value
                      ? 'bg-amber-500/15 text-amber-400 border-amber-500/30'
                      : 'text-stone-500 border-stone-800/60 hover:text-stone-300',
                  ].join(' ')}>
                  <span className="text-base leading-none">{m.icon}</span>
                  {m.label}
                </button>
              ))}
            </div>

            <div className={method === 'cash' ? 'grid grid-cols-2 gap-3' : ''}>
              <div>
                <label className="block text-[11px] font-semibold text-stone-500 uppercase tracking-wider mb-1.5">
                  Valor (R$)
                </label>
                <input type="text" inputMode="numeric" value={amount}
                  onChange={e => setAmount(maskCurrency(e.target.value))}
                  placeholder="0,00" className={inputCls} style={{ background: '#0d0b08' }} />
              </div>
              {method === 'cash' && (
                <div>
                  <label className="block text-[11px] font-semibold text-stone-500 uppercase tracking-wider mb-1.5">
                    Recebido (R$)
                  </label>
                  <input type="text" inputMode="numeric" value={tendered}
                    onChange={e => setTendered(maskCurrency(e.target.value))}
                    placeholder="0,00" className={inputCls} style={{ background: '#0d0b08' }} />
                </div>
              )}
            </div>

            {method === 'cash' && change > 0 && (
              <div className="flex justify-between text-xs px-1">
                <span className="text-stone-500">Troco</span>
                <span className="text-amber-400 font-bold">{brl(change)}</span>
              </div>
            )}

            <button type="submit" disabled={saving}
              className="w-full py-2.5 rounded-xl text-sm font-semibold
                         bg-amber-500 hover:bg-amber-400 text-stone-900
                         disabled:opacity-40 transition-colors">
              {saving ? 'Registrando…' : 'Registrar pagamento'}
            </button>
          </form>
        )}
      </div>
    </div>
  )
}

// ── Card de entrada de fiado individual ────────────────────────────────────────

function FiadoEntryCard({
  entry,
  onReceive,
  onReopen,
  reopening,
}: {
  entry: FiadoCustomerGroup['entries'][number]
  onReceive: () => void
  onReopen: () => void
  reopening?: boolean
}) {
  const total = Number(entry.total)
  const paid = Number(entry.paid)
  const remaining = Number(entry.remaining)

  return (
    <div className="rounded-xl border border-stone-800/60 p-4"
         style={{ background: '#161210' }}>
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="text-stone-400 text-xs">
              {new Date(entry.created_at).toLocaleDateString('pt-BR')}
              {' · '}
              {ORDER_TYPE_LABEL[entry.order_type] ?? entry.order_type}
            </span>
          </div>
          <div className="mt-2 flex items-center gap-4 text-xs">
            <span className="text-stone-500">
              Total: <span className="text-stone-300 font-medium">{brl(total)}</span>
            </span>
            <span className="text-green-600">
              Pago: <span className="text-green-500 font-medium">{brl(paid)}</span>
            </span>
          </div>
        </div>
        <div className="text-right shrink-0">
          <p className="text-amber-400 text-2xl font-bold leading-none">{brl(remaining)}</p>
        </div>
      </div>

      <div className="mt-3 flex gap-2">
        <button onClick={onReceive}
          className="flex-1 py-2 rounded-xl text-sm font-semibold
                     bg-amber-500 hover:bg-amber-400 text-stone-900 transition-colors">
          Receber {brl(remaining)}
        </button>
        <button onClick={onReopen} disabled={reopening}
          className="py-2 px-4 rounded-xl text-sm font-semibold
                     border border-stone-700 text-stone-300 hover:bg-stone-700/50
                     disabled:opacity-40 transition-colors">
          {reopening ? 'Abrindo…' : 'Reabrir'}
        </button>
      </div>
    </div>
  )
}

// ── Grupo de cliente ──────────────────────────────────────────────────────────

function CustomerGroup({
  group,
  onReceive,
  onReopen,
  reopeningId,
}: {
  group: FiadoCustomerGroup
  onReceive: (entry: FiadoCustomerGroup['entries'][number]) => void
  onReopen: (entry: FiadoCustomerGroup['entries'][number]) => void
  reopeningId?: string | null
}) {
  const [collapsed, setCollapsed] = useState(false)

  return (
    <div className="rounded-2xl border border-stone-800/60 overflow-hidden"
         style={{ background: '#0f0d0a' }}>
      {/* Header do grupo */}
      <button onClick={() => setCollapsed(!collapsed)}
        className="w-full flex items-center justify-between px-5 py-4 hover:bg-stone-800/30 transition-colors text-left">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-stone-800 flex items-center justify-center text-sm font-bold text-amber-400">
            {group.customer_name.charAt(0).toUpperCase()}
          </div>
          <div>
            <h2 className="text-stone-100 font-bold">{group.customer_name}</h2>
            <p className="text-stone-500 text-xs">
              {group.entries.length} {group.entries.length === 1 ? 'comanda' : 'comandas'}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-4">
          <div className="text-right">
            <p className="text-[10px] text-stone-600 uppercase tracking-wider">Débito total</p>
            <p className="text-amber-400 font-black text-lg">{brl(group.total_remaining)}</p>
          </div>
          <svg className={['w-5 h-5 text-stone-500 transition-transform', collapsed ? '' : 'rotate-180'].join(' ')}
               fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
          </svg>
        </div>
      </button>

      {/* Lista de entradas */}
      {!collapsed && (
        <div className="px-4 pb-4 space-y-2">
          {group.entries.map(entry => (
            <FiadoEntryCard
              key={entry.order_id}
              entry={entry}
              onReceive={() => onReceive(entry)}
              onReopen={() => onReopen(entry)}
              reopening={reopeningId === entry.order_id}
            />
          ))}
        </div>
      )}
    </div>
  )
}

// ── Página Fiado ───────────────────────────────────────────────────────────────

export default function FiadoPage() {
  const navigate = useNavigate()
  const [groups, setGroups] = useState<FiadoCustomerGroup[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [payingEntry, setPayingEntry] = useState<FiadoCustomerGroup['entries'][number] | null>(null)
  const [reopening, setReopening] = useState<string | null>(null)

  function load() {
    setLoading(true)
    setError(null)
    fetchFiadoGrouped()
      .then(setGroups)
      .catch(err => setError(err instanceof Error ? err.message : 'Erro ao carregar fiado'))
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [])

  function handlePaid() {
    setPayingEntry(null)
    load()
  }

  async function handleReopen(entry: FiadoCustomerGroup['entries'][number]) {
    setReopening(entry.order_id)
    setError(null)
    try {
      await reopenOrder(entry.order_id)
      navigate(`/comanda/${entry.order_id}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro ao reabrir comanda')
      setReopening(null)
    }
  }

  return (
    <div className="p-4 sm:p-6 max-w-xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-stone-100 text-xl font-bold">Fiado</h1>
          <p className="text-stone-500 text-sm mt-0.5">Contas com pagamento pendente</p>
        </div>
        <button onClick={load}
          className="text-stone-500 hover:text-amber-400 transition-colors p-2 rounded-lg hover:bg-stone-800/50"
          title="Atualizar">
          <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.75}>
            <path strokeLinecap="round" strokeLinejoin="round"
              d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
          </svg>
        </button>
      </div>

      {error && <ErrorBanner message={error} onRetry={load} />}

      {loading ? (
        <Spinner text="Carregando fiados..." />
      ) : groups.length === 0 ? (
        <div className="text-center py-16">
          <div className="text-5xl mb-4">✅</div>
          <p className="text-stone-300 font-semibold">Nenhuma conta em fiado</p>
          <p className="text-stone-600 text-sm mt-1">Todos os pedidos estão quitados.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {groups.map(group => (
            <CustomerGroup
              key={group.customer_name}
              group={group}
              onReceive={entry => setPayingEntry(entry)}
              onReopen={handleReopen}
              reopeningId={reopening}
            />
          ))}
        </div>
      )}

      {payingEntry && (
        <FiadoPaymentModal
          entry={payingEntry}
          onClose={() => setPayingEntry(null)}
          onPaid={handlePaid}
        />
      )}
    </div>
  )
}
