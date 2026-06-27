import { useEffect, useState, useCallback } from 'react'
import {
  fetchFiado, fetchOrderPayments, registerPayment,
  type FiadoEntry, type Payment, type PaymentMethod,
} from '../lib/api'
import { maskCurrency, parseCurrency, toCurrencyInput } from '../lib/format'

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

const inputCls = `w-full rounded-xl px-3.5 py-2.5 text-sm border border-stone-800/80
  text-stone-100 placeholder-stone-700 focus:outline-none transition-all
  focus:border-amber-500/40 focus:ring-1 focus:ring-amber-500/20`.replace(/\s+/g, ' ')

// ── Modal de pagamento do fiado ───────────────────────────────────────────────

function FiadoPaymentModal({
  entry,
  onClose,
  onPaid,
}: {
  entry: FiadoEntry
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

  // saldo em tempo real (pode mudar ao registrar pagamentos)
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

  // pré-preenche com o saldo devedor
  useEffect(() => {
    if (!loading) setAmount(remaining > 0 ? toCurrencyInput(remaining) : '')
  }, [remaining, loading])

  // fecha o modal via Escape
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
      if (newPaid >= total) {
        // fiado quitado — fecha modal e atualiza lista
        onPaid()
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro ao registrar pagamento')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-4"
      style={{ background: 'rgba(0,0,0,0.75)', backdropFilter: 'blur(4px)' }}
      onClick={onClose}
    >
      <div
        className="w-full max-w-md rounded-3xl border border-stone-800/70 p-5"
        style={{ background: '#161210' }}
        onClick={e => e.stopPropagation()}
      >
        {/* Cabeçalho */}
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

        {/* Resumo */}
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

        {/* Pagamentos já registrados */}
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
            {/* Forma de pagamento */}
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

// ── Página Fiado ───────────────────────────────────────────────────────────────

export default function FiadoPage() {
  const [entries, setEntries] = useState<FiadoEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [payingEntry, setPayingEntry] = useState<FiadoEntry | null>(null)

  function load() {
    setLoading(true)
    fetchFiado()
      .then(setEntries)
      .catch(() => {})
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [])

  function handlePaid() {
    setPayingEntry(null)
    load()
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

      {loading ? (
        <div className="text-center py-16 text-stone-600 text-sm">Carregando...</div>
      ) : entries.length === 0 ? (
        <div className="text-center py-16">
          <div className="text-5xl mb-4">✅</div>
          <p className="text-stone-300 font-semibold">Nenhuma conta em fiado</p>
          <p className="text-stone-600 text-sm mt-1">Todos os pedidos estão quitados.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {entries.map(entry => (
            <div
              key={entry.order_id}
              className="rounded-xl border border-stone-800/60 p-4"
              style={{ background: '#161210' }}
            >
              <div className="flex items-start justify-between gap-4">
                <div className="min-w-0 flex-1">
                  <p className="text-stone-100 font-semibold truncate">
                    {entry.table_number
                      ? `Mesa ${entry.table_number}`
                      : entry.customer_name ?? '—'}
                  </p>
                  <p className="text-stone-500 text-xs mt-0.5">
                    {ORDER_TYPE_LABEL[entry.order_type] ?? entry.order_type}
                    {' · '}
                    {new Date(entry.created_at).toLocaleDateString('pt-BR')}
                  </p>
                  <div className="mt-2.5 flex items-center gap-4 text-xs">
                    <span className="text-stone-500">
                      Total: <span className="text-stone-300 font-medium">{brl(entry.total)}</span>
                    </span>
                    <span className="text-green-600">
                      Pago: <span className="text-green-500 font-medium">{brl(entry.paid)}</span>
                    </span>
                  </div>
                </div>
                <div className="text-right shrink-0">
                  <p className="text-[10px] text-stone-600 uppercase tracking-wider mb-1">Falta</p>
                  <p className="text-amber-400 text-2xl font-bold leading-none">{brl(entry.remaining)}</p>
                </div>
              </div>

              {/* Botão receber */}
              <button
                onClick={() => setPayingEntry(entry)}
                className="mt-3 w-full py-2 rounded-xl text-sm font-semibold
                           bg-amber-500 hover:bg-amber-400 text-stone-900 transition-colors"
              >
                Receber {brl(entry.remaining)}
              </button>
            </div>
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
