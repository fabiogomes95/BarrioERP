import { useState } from 'react'
import { type Order, setOrderDiscount } from '../../lib/api'
import { brl, maskCurrency, parseCurrency, toCurrencyInput } from '../../lib/format'
import { Field, ModalOverlay } from '../ui'
import { inputCls } from '../../lib/styles'

// ── Modal: Desconto ───────────────────────────────────────────────────────────

export function DiscountModal({
  order, onClose, onUpdated,
}: {
  order: Order
  onClose: () => void
  onUpdated: (o: Order) => void
}) {
  const subtotal = Number(order.subtotal)
  const [mode, setMode] = useState<'value' | 'percent'>('value')
  const [value, setValue] = useState(Number(order.discount) > 0 ? toCurrencyInput(order.discount) : '')
  const [percent, setPercent] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const discountValue = mode === 'value'
    ? parseCurrency(value)
    : Math.round(subtotal * (parseFloat(percent.replace(',', '.')) || 0)) / 100

  async function apply(amount: number) {
    setError(null)
    if (isNaN(amount) || amount < 0) { setError('Valor inválido'); return }
    if (amount > subtotal) { setError('O desconto não pode exceder o subtotal'); return }
    setSaving(true)
    try {
      const updated = await setOrderDiscount(order.id, amount)
      onUpdated(updated)
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro ao aplicar desconto')
    } finally {
      setSaving(false)
    }
  }

  return (
    <ModalOverlay onClose={onClose}>
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-stone-100 text-base font-bold">Desconto</h2>
        <button onClick={onClose} className="text-stone-600 hover:text-stone-400 transition-colors">
          <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      <div className="flex gap-1 p-1 rounded-xl mb-4" style={{ background: 'var(--color-app-bg)' }}>
        {(['value', 'percent'] as const).map(m => (
          <button key={m} onClick={() => setMode(m)}
            className={['flex-1 py-2 rounded-lg text-xs font-semibold transition-all',
              mode === m ? 'bg-amber-500/15 text-amber-400' : 'text-stone-500 hover:text-stone-300'].join(' ')}>
            {m === 'value' ? 'Valor (R$)' : 'Percentual (%)'}
          </button>
        ))}
      </div>

      {error && (
        <p className="text-red-400 text-xs bg-red-500/10 border border-red-500/20 rounded-xl px-3 py-2 mb-3">{error}</p>
      )}

      {mode === 'value' ? (
        <Field label="Desconto (R$)">
          <input type="text" inputMode="numeric" value={value} autoFocus
            onChange={e => setValue(maskCurrency(e.target.value))}
            placeholder="0,00" className={inputCls} style={{ background: 'var(--color-app-bg)' }} />
        </Field>
      ) : (
        <Field label="Desconto (%)">
          <input type="number" min={0} max={100} value={percent} autoFocus
            onChange={e => setPercent(e.target.value)}
            placeholder="ex: 10" className={inputCls} style={{ background: 'var(--color-app-bg)' }} />
        </Field>
      )}

      <div className="flex justify-between text-xs px-1 mt-3">
        <span className="text-stone-500">Desconto aplicado</span>
        <span className="text-amber-400 font-bold">{brl(discountValue || 0)}</span>
      </div>

      <div className="flex gap-2 mt-4">
        {Number(order.discount) > 0 && (
          <button onClick={() => apply(0)} disabled={saving}
            className="px-3 py-2.5 rounded-xl text-sm font-semibold text-red-400 border border-red-500/30
                       hover:bg-red-500/10 disabled:opacity-40 transition-colors">
            Remover
          </button>
        )}
        <button onClick={() => apply(discountValue)} disabled={saving}
          className="flex-1 py-2.5 rounded-xl text-sm font-semibold bg-amber-500 hover:bg-amber-400
                     text-stone-900 disabled:opacity-40 transition-colors">
          {saving ? 'Aplicando…' : 'Aplicar desconto'}
        </button>
      </div>
    </ModalOverlay>
  )
}
