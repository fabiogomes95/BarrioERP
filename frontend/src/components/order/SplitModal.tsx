import { useState, useEffect, useCallback } from 'react'
import {
  type Order, type Payment, type PaymentMethod, fetchOrderPayments, registerPayment, finishOrder,
} from '../../lib/api'
import { brl, maskCurrency, parseCurrency, toCurrencyInput } from '../../lib/format'
import { paidSlots, splitAmounts, splitByShares } from '../../lib/split'
import { Field, ModalOverlay } from '../ui'
import { inputCls } from '../../lib/styles'
import { closeOrFinish } from './closeOrFinish'
import { PAYMENT_METHODS } from './paymentMethods'

// ── Modal: Dividir conta ──────────────────────────────────────────────────────

export function SplitModal({
  order, onClose, onFinished, onPaidUpdate,
}: {
  order: Order
  onClose: () => void
  onFinished: (orderId: string) => void
  onPaidUpdate?: (payments: Payment[]) => void
}) {
  const [mode, setMode] = useState<'equal' | 'items'>('equal')
  const [count, setCount] = useState(2)
  const [assignments, setAssignments] = useState<Record<string, number>>({})
  const [payments, setPayments] = useState<Payment[]>([])
  const [loading, setLoading] = useState(true)
  const [activeSlot, setActiveSlot] = useState<number | null>(null)
  const [method, setMethod] = useState<PaymentMethod>('cash')
  const [amount, setAmount] = useState('')
  const [tendered, setTendered] = useState('')
  const [saving, setSaving] = useState(false)
  const [finishing, setFinishing] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const total = Number(order.total)
  const paid = payments
    .filter(p => p.status === 'confirmed')
    .reduce((sum, p) => sum + Number(p.amount), 0)
  const remaining = Math.max(0, Math.round((total - paid) * 100) / 100)
  const fullyPaid = remaining <= 0

  const activeItems = order.items.filter(i => i.status !== 'cancelled')
  const unassignedItems = mode === 'items'
    ? activeItems.filter(it => assignments[it.id] === undefined || assignments[it.id] >= count)
    : []
  const readyToPay = mode === 'equal' || unassignedItems.length === 0

  const amounts = mode === 'equal'
    ? splitAmounts(total, count)
    : readyToPay
      ? splitByShares(
          total,
          Array.from({ length: count }, (_, p) =>
            activeItems.filter(it => assignments[it.id] === p)
              .reduce((sum, it) => sum + Number(it.subtotal), 0)),
        )
      : Array(count).fill(0)

  const slotPaid = paidSlots(amounts, paid)

  function assignItem(itemId: string, person: number) {
    setAssignments(prev => {
      const next = { ...prev }
      if (next[itemId] === person) delete next[itemId]
      else next[itemId] = person
      return next
    })
  }

  const tenderedNum = parseCurrency(tendered)
  const amountNum = parseCurrency(amount)
  const change =
    method === 'cash' && !isNaN(tenderedNum) && !isNaN(amountNum) && tenderedNum > amountNum
      ? tenderedNum - amountNum
      : 0

  const refreshPayments = useCallback(async () => {
    const ps = await fetchOrderPayments(order.id)
    setPayments(ps)
    return ps
  }, [order.id])

  useEffect(() => {
    refreshPayments().finally(() => setLoading(false))
  }, [refreshPayments])

  useEffect(() => {
    onPaidUpdate?.(payments)
  }, [payments, onPaidUpdate])

  function openSlot(i: number) {
    setError(null)
    setActiveSlot(i)
    setAmount(toCurrencyInput(Math.min(amounts[i], remaining)))
    setTendered('')
    setMethod('cash')
  }

  async function handlePaySlot(e: React.FormEvent) {
    e.preventDefault()
    // Guarda de reentrância — ver comentário equivalente no PaymentModal.
    if (saving) return
    setError(null)
    const value = parseCurrency(amount)
    if (isNaN(value) || value <= 0) { setError('Informe um valor válido'); return }

    // Fecha o teclado virtual antes de trocar de tela (mesmo motivo do
    // PaymentModal — senão o teclado cobre o que aparece no lugar do formulário).
    ;(document.activeElement as HTMLElement | null)?.blur()

    setSaving(true)
    try {
      await registerPayment({
        order_id: order.id,
        method,
        amount: value.toFixed(2),
        amount_tendered:
          method === 'cash' && !isNaN(tenderedNum) ? tenderedNum.toFixed(2) : null,
        reference: null,
      })
      await refreshPayments()
      setActiveSlot(null)
      setTendered('')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro ao registrar pagamento')
      // Mesmo comentário do PaymentModal: se o erro foi "já paga" (clique
      // duplo etc.), isso puxa o estado real e a tela se corrige sozinha.
      await refreshPayments().catch(() => {})
    } finally {
      setSaving(false)
    }
  }

  async function handleFinish() {
    setError(null)
    setFinishing(true)
    try {
      await closeOrFinish(order.id, order.version, finishOrder)
      onFinished(order.id)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro ao finalizar comanda')
    } finally {
      setFinishing(false)
    }
  }

  return (
    <ModalOverlay onClose={onClose}>
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-stone-100 text-base font-bold">Dividir conta</h2>
        <button onClick={onClose} className="text-stone-600 hover:text-stone-400 transition-colors">
          <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      {/* Modo de divisão */}
      <div className="flex gap-1 p-1 rounded-xl mb-4" style={{ background: 'var(--color-app-bg)' }}>
        {([['equal', 'Igualmente'], ['items', 'Por item']] as const).map(([m, label]) => (
          <button key={m} onClick={() => setMode(m)}
            className={[
              'flex-1 py-2 rounded-lg text-xs font-semibold transition-all',
              mode === m ? 'bg-amber-500/15 text-amber-400' : 'text-stone-500 hover:text-stone-300',
            ].join(' ')}>
            {label}
          </button>
        ))}
      </div>

      {/* Stepper de pessoas */}
      <div className="flex items-center justify-between rounded-2xl p-4 mb-4" style={{ background: 'var(--color-app-bg)' }}>
        <span className="text-stone-500 text-sm">Dividir entre</span>
        <div className="flex items-center gap-3">
          <button type="button" onClick={() => setCount(c => Math.max(2, c - 1))} disabled={count <= 2}
            className="w-8 h-8 flex items-center justify-center rounded-lg border border-stone-700/60
                       text-stone-300 hover:bg-stone-800/60 disabled:opacity-30 transition-colors">
            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
              <path strokeLinecap="round" d="M5 12h14" />
            </svg>
          </button>
          <span className="text-stone-100 text-base font-black w-16 text-center tabular-nums">
            {count} {count === 1 ? 'pessoa' : 'pessoas'}
          </span>
          <button type="button" onClick={() => setCount(c => Math.min(20, c + 1))} disabled={count >= 20}
            className="w-8 h-8 flex items-center justify-center rounded-lg border border-stone-700/60
                       text-stone-300 hover:bg-stone-800/60 disabled:opacity-30 transition-colors">
            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
              <path strokeLinecap="round" d="M12 5v14M5 12h14" />
            </svg>
          </button>
        </div>
      </div>

      {/* Atribuição de itens por pessoa */}
      {mode === 'items' && (
        <div className="rounded-2xl p-3 mb-4 space-y-1" style={{ background: 'var(--color-app-bg)' }}>
          {activeItems.length === 0 ? (
            <p className="text-stone-600 text-xs text-center py-2">Comanda sem itens</p>
          ) : (
            activeItems.map(item => (
              <div key={item.id} className="flex items-center justify-between gap-2 py-1.5">
                <div className="min-w-0 flex-1">
                  <p className="text-stone-300 text-xs truncate">{item.quantity}x {item.item_name}</p>
                  <p className="text-stone-600 text-[11px]">{brl(item.subtotal)}</p>
                </div>
                <div className="flex items-center gap-1 shrink-0">
                  {Array.from({ length: count }, (_, p) => (
                    <button key={p} type="button" onClick={() => assignItem(item.id, p)}
                      title={`Pessoa ${p + 1}`}
                      className={[
                        'w-6 h-6 rounded-full text-[10px] font-bold transition-all border',
                        assignments[item.id] === p
                          ? 'bg-amber-500 text-stone-900 border-amber-500'
                          : 'text-stone-500 border-stone-700/60 hover:border-stone-600',
                      ].join(' ')}>
                      {p + 1}
                    </button>
                  ))}
                </div>
              </div>
            ))
          )}
          {unassignedItems.length > 0 && (
            <p className="text-amber-400 text-[11px] pt-1.5 border-t border-stone-800/60">
              {unassignedItems.length} {unassignedItems.length === 1 ? 'item sem atribuir' : 'itens sem atribuir'} — toque no número da pessoa
            </p>
          )}
        </div>
      )}

      {/* Resumo financeiro */}
      <div className="rounded-2xl p-4 mb-4 space-y-1.5" style={{ background: 'var(--color-app-bg)' }}>
        <div className="flex justify-between text-sm">
          <span className="text-stone-500">Total da conta</span>
          <span className="text-stone-200 font-semibold">{brl(total)}</span>
        </div>
        <div className="flex justify-between text-sm">
          <span className="text-stone-500">Pago</span>
          <span className="text-green-400 font-semibold">{brl(paid)}</span>
        </div>
        <div className="flex justify-between pt-1.5 border-t border-stone-800/60">
          <span className="text-stone-300 text-sm font-bold">{fullyPaid ? 'Quitada' : 'Falta'}</span>
          <span className={['text-base font-black', fullyPaid ? 'text-green-400' : 'text-amber-400'].join(' ')}>
            {brl(remaining)}
          </span>
        </div>
      </div>

      {error && (
        <p className="text-red-400 text-xs bg-red-500/10 border border-red-500/20
                       rounded-xl px-3 py-2 mb-3">{error}</p>
      )}

      {loading ? (
        <div className="text-center py-6 text-stone-600 text-sm">Carregando pagamentos…</div>
      ) : !readyToPay ? (
        <p className="text-stone-600 text-sm text-center py-4">
          Atribua todos os itens a alguém pra ver o valor de cada pessoa
        </p>
      ) : (
        <>
          {/* Lista de parcelas por pessoa */}
          <div className="space-y-1.5 mb-2">
            {amounts.map((slotAmount, i) => (
              <div key={i} className="rounded-xl overflow-hidden" style={{ background: 'var(--color-app-bg)' }}>
                <div className="flex items-center justify-between px-3.5 py-2.5">
                  <span className="text-stone-300 text-sm font-medium">Pessoa {i + 1}</span>
                  <div className="flex items-center gap-3">
                    <span className="text-stone-200 text-sm font-semibold">{brl(slotAmount)}</span>
                    {slotPaid[i] ? (
                      <span className="text-green-400 text-xs font-bold">✓ Pago</span>
                    ) : (
                      <button
                        onClick={() => (activeSlot === i ? setActiveSlot(null) : openSlot(i))}
                        className="text-xs font-bold text-amber-400 hover:text-amber-300 transition-colors px-2 py-1">
                        {activeSlot === i ? 'Fechar' : 'Receber'}
                      </button>
                    )}
                  </div>
                </div>

                {activeSlot === i && !slotPaid[i] && (
                  <form onSubmit={handlePaySlot} className="px-3.5 pb-3.5 space-y-3">
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
                      <Field label="Valor (R$)">
                        <input type="text" inputMode="numeric" value={amount}
                          onChange={e => setAmount(maskCurrency(e.target.value))}
                          placeholder="0,00" className={inputCls} style={{ background: 'var(--color-app-surface)' }} />
                      </Field>
                      {method === 'cash' && (
                        <Field label="Recebido (R$)">
                          <input type="text" inputMode="numeric" value={tendered}
                            onChange={e => setTendered(maskCurrency(e.target.value))}
                            placeholder="0,00" className={inputCls} style={{ background: 'var(--color-app-surface)' }} />
                        </Field>
                      )}
                    </div>

                    {method === 'cash' && change > 0 && (
                      <div className="flex justify-between text-xs px-1">
                        <span className="text-stone-500">Troco</span>
                        <span className="text-amber-400 font-bold">{brl(change)}</span>
                      </div>
                    )}

                    <button type="submit" disabled={saving}
                      className="w-full py-2 rounded-xl text-sm font-semibold
                                 bg-amber-500 hover:bg-amber-400 text-stone-900
                                 disabled:opacity-40 transition-colors">
                      {saving ? 'Registrando…' : 'Registrar pagamento'}
                    </button>
                  </form>
                )}
              </div>
            ))}
          </div>

          {fullyPaid && (
            <button onClick={handleFinish} disabled={finishing}
              className="w-full py-3 rounded-xl text-sm font-bold mt-3
                         bg-green-500 hover:bg-green-400 text-stone-900
                         disabled:opacity-40 transition-colors">
              {finishing ? 'Finalizando…' : 'Finalizar comanda e liberar mesa'}
            </button>
          )}
        </>
      )}
    </ModalOverlay>
  )
}
