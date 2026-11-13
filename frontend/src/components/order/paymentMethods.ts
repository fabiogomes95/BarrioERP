import type { PaymentMethod } from '../../lib/api'

// Formas de pagamento dos modais de receber e dividir conta
export const PAYMENT_METHODS: { value: PaymentMethod; label: string; icon: string }[] = [
  { value: 'cash',        label: 'Dinheiro', icon: '💵' },
  { value: 'credit_card', label: 'Crédito',  icon: '💳' },
  { value: 'debit_card',  label: 'Débito',   icon: '💳' },
  { value: 'pix',         label: 'Pix',      icon: '⚡' },
  { value: 'voucher',     label: 'Voucher',  icon: '🎟️' },
]

export const METHOD_LABEL: Record<string, string> = Object.fromEntries(
  PAYMENT_METHODS.map(m => [m.value, m.label]),
)
