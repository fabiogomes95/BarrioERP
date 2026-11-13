import { useState, useEffect, useCallback } from 'react'
import {
  type Order, type Payment, fetchOrderPayments, registerPayment, voidPayment, finishOrder,
} from '../../lib/api'
import { brl, maskCurrency, parseCurrency, toCurrencyInput } from '../../lib/format'
import { Field, ModalOverlay } from '../ui'
import { inputCls } from '../../lib/styles'
import { closeOrFinish } from './closeOrFinish'
import { METHOD_LABEL, PAYMENT_METHODS } from './paymentMethods'

// ── Modal: Receber pagamento ──────────────────────────────────────────────────

export function PaymentModal({
  order, onClose, onFinished, onPaidUpdate,
}: {
  order: Order
  onClose: () => void
  onFinished: (orderId: string) => void
  onPaidUpdate?: (payments: Payment[]) => void
}) {
  const [payments, setPayments] = useState<Payment[]>([])
  const [loading, setLoading] = useState(true)
  const [method, setMethod] = useState<PaymentMethod>('cash')
  const [amount, setAmount] = useState('')
  const [tendered, setTendered] = useState('')
  const [reference, setReference] = useState('')
  const [saving, setSaving] = useState(false)
  const [finishing, setFinishing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [confirmVoidId, setConfirmVoidId] = useState<string | null>(null)
  const [voiding, setVoiding] = useState(false)

  const total = Number(order.total)
  const paid = payments
    .filter(p => p.status === 'confirmed')
    .reduce((sum, p) => sum + Number(p.amount), 0)
  const remaining = Math.max(0, Math.round((total - paid) * 100) / 100)
  const fullyPaid = remaining <= 0

  // Troco previsto para dinheiro
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

  // Notifica o pai com a lista de pagamentos sempre que ela muda
  useEffect(() => {
    onPaidUpdate?.(payments)
  }, [payments, onPaidUpdate])

  // Ao mudar o saldo devedor, pré-preenche o valor com o restante
  useEffect(() => {
    if (!loading) setAmount(remaining > 0 ? toCurrencyInput(remaining) : '')
  }, [remaining, loading])

  async function handleVoidPayment(paymentId: string) {
    setError(null)
    setVoiding(true)
    try {
      await voidPayment(paymentId)
      await refreshPayments()
      setConfirmVoidId(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro ao estornar pagamento')
    } finally {
      setVoiding(false)
    }
  }

  async function handleAddPayment(e: React.FormEvent) {
    e.preventDefault()
    // Guarda de reentrância síncrona: num toque duplo rápido (comum no
    // celular), o segundo clique pode disparar antes do React re-renderizar
    // o botão com disabled=true. Sem isso, os dois submits chegavam ao
    // backend — o primeiro registrava o pagamento, o segundo era barrado
    // pela proteção "comanda já paga" do servidor, e a tela ficava travada
    // mostrando esse erro em vez do botão de finalizar (ver correção no
    // catch abaixo também).
    if (saving) return
    setError(null)
    const value = parseCurrency(amount)
    if (isNaN(value) || value <= 0) { setError('Informe um valor válido'); return }

    // Fecha o teclado virtual do celular antes de trocar de tela — senão o
    // teclado fica aberto cobrindo o botão "Finalizar comanda" que aparece
    // no lugar do formulário, e parece que nada aconteceu ao registrar.
    ;(document.activeElement as HTMLElement | null)?.blur()

    setSaving(true)
    try {
      await registerPayment({
        order_id: order.id,
        method,
        amount: value.toFixed(2),
        amount_tendered:
          method === 'cash' && !isNaN(tenderedNum) ? tenderedNum.toFixed(2) : null,
        reference: reference.trim() || null,
      })
      await refreshPayments()
      setTendered('')
      setReference('')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro ao registrar pagamento')
      // Mesmo quando ESTE registro falhou, busca o estado real da comanda:
      // se o erro foi "já está totalmente paga" (ex: clique duplo, ou outro
      // caixa registrou ao mesmo tempo), isso atualiza `payments` e o modal
      // troca sozinho pro botão "Finalizar" — sem isso, a tela ficava presa
      // mostrando "não pago" mesmo com o pagamento já garantido no banco,
      // obrigando a sair e voltar pra ver que já tinha dado certo.
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
        <h2 className="text-stone-100 text-base font-bold">Receber pagamento</h2>
        <button onClick={onClose} className="text-stone-600 hover:text-stone-400 transition-colors">
          <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

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

      {/* Pagamentos já registrados */}
      {payments.filter(p => p.status === 'confirmed').length > 0 && (
        <div className="space-y-1 mb-4">
          {payments.filter(p => p.status === 'confirmed').map(p => (
            confirmVoidId === p.id ? (
              <div key={p.id} className="flex items-center justify-between text-xs px-3 py-2 rounded-lg
                                          bg-red-500/10 border border-red-500/20">
                <span className="text-red-300">Estornar este pagamento?</span>
                <div className="flex items-center gap-2">
                  <button type="button" onClick={() => setConfirmVoidId(null)} disabled={voiding}
                    className="px-2 py-1 rounded-md text-stone-400 hover:text-stone-200 disabled:opacity-40">
                    Não
                  </button>
                  <button type="button" onClick={() => handleVoidPayment(p.id)} disabled={voiding}
                    className="px-2 py-1 rounded-md font-semibold text-red-400 hover:text-red-300 disabled:opacity-40">
                    {voiding ? 'Estornando…' : 'Sim, estornar'}
                  </button>
                </div>
              </div>
            ) : (
              <div key={p.id} className="flex items-center justify-between text-xs px-3 py-2 rounded-lg"
                   style={{ background: 'var(--color-app-bg)' }}>
                <span className="text-stone-400">{METHOD_LABEL[p.method] ?? p.method}</span>
                <div className="flex items-center gap-2">
                  {p.change_given && Number(p.change_given) > 0 && (
                    <span className="text-stone-600">troco {brl(p.change_given)}</span>
                  )}
                  <span className="text-stone-300 font-semibold">{brl(p.amount)}</span>
                  <button type="button" onClick={() => setConfirmVoidId(p.id)}
                    title="Estornar pagamento (corrigir erro de lançamento)"
                    className="text-stone-600 hover:text-red-400 transition-colors">
                    <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                    </svg>
                  </button>
                </div>
              </div>
            )
          ))}
        </div>
      )}

      {loading ? (
        <div className="text-center py-6 text-stone-600 text-sm">Carregando pagamentos…</div>
      ) : !fullyPaid ? (
        <form onSubmit={handleAddPayment} className="space-y-3">
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
            <Field label="Valor (R$)">
              <input type="text" inputMode="numeric" value={amount}
                onChange={e => setAmount(maskCurrency(e.target.value))}
                placeholder="0,00" className={inputCls} style={{ background: 'var(--color-app-bg)' }} />
            </Field>
            {method === 'cash' && (
              <Field label="Recebido (R$)">
                <input type="text" inputMode="numeric" value={tendered}
                  onChange={e => setTendered(maskCurrency(e.target.value))}
                  placeholder="0,00" className={inputCls} style={{ background: 'var(--color-app-bg)' }} />
              </Field>
            )}
          </div>

          {method === 'cash' && change > 0 && (
            <div className="flex justify-between text-xs px-1">
              <span className="text-stone-500">Troco</span>
              <span className="text-amber-400 font-bold">{brl(change)}</span>
            </div>
          )}

          {method !== 'cash' && (
            <Field label="Referência (opcional)">
              <input type="text" value={reference} onChange={e => setReference(e.target.value)}
                placeholder="NSU, txid do Pix…" className={inputCls} style={{ background: 'var(--color-app-bg)' }} />
            </Field>
          )}

          <button type="submit" disabled={saving}
            className="w-full py-2.5 rounded-xl text-sm font-semibold
                       bg-amber-500 hover:bg-amber-400 text-stone-900
                       disabled:opacity-40 transition-colors">
            {saving ? 'Registrando…' : 'Registrar pagamento'}
          </button>
        </form>
      ) : (
        <button onClick={handleFinish} disabled={finishing}
          className="w-full py-3 rounded-xl text-sm font-bold
                     bg-green-500 hover:bg-green-400 text-stone-900
                     disabled:opacity-40 transition-colors">
          {finishing ? 'Finalizando…' : 'Finalizar comanda e liberar mesa'}
        </button>
      )}
    </ModalOverlay>
  )
}
