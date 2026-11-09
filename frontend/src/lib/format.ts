import type { OrderItem } from './api'

// Utilidades de formatação (moeda, tempo) — pt-BR

/**
 * Máscara de moeda baseada em centavos.
 * O usuário digita apenas dígitos e a vírgula é posicionada sozinha:
 *   "4"     → "0,04"
 *   "48"    → "0,48"
 *   "4800"  → "48,00"
 *   "125000"→ "1.250,00"
 * Campo vazio continua vazio (para o placeholder aparecer).
 */
export function maskCurrency(input: string): string {
  const digits = input.replace(/\D/g, '')
  if (!digits) return ''
  const value = parseInt(digits, 10) / 100
  return value.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

/**
 * Converte o texto mascarado de volta para número.
 * Remove separadores de milhar (.) e troca a vírgula decimal por ponto.
 *   "1.250,00" → 1250
 *   "48,00"    → 48
 * Retorna NaN se vazio/ inválido.
 */
export function parseCurrency(masked: string): number {
  if (!masked.trim()) return NaN
  return parseFloat(masked.replace(/\./g, '').replace(',', '.'))
}

/**
 * Recebe um valor numérico (ou string "48.00" da API) e devolve o texto
 * mascarado para preencher um input — ex.: editar um item já existente.
 */
export function toCurrencyInput(value: string | number): string {
  const n = Number(value)
  if (isNaN(n)) return ''
  return maskCurrency(String(Math.round(n * 100)))
}

/** R$ 1.250,00 */
export function brl(v: string | number) {
  return Number(v).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })
}

/** Tempo desde `iso`, curto: agora, 5min, 2h, 3d. */
export function timeAgo(iso: string) {
  const diff = Date.now() - new Date(iso).getTime()
  const m = Math.floor(diff / 60000)
  if (m < 1) return 'agora'
  if (m < 60) return `${m}min`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h}h`
  return `${Math.floor(h / 24)}d`
}

/** Hora (HH:mm) do último lançamento do item — quantidade incrementada conta como novo lançamento. */
export function itemTime(item: OrderItem) {
  return new Date(item.updated_at).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })
}
