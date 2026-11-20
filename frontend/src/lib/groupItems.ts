import type { OrderItem } from './api'

/**
 * Itens iguais lançados em momentos diferentes (5 churrascos às 20h, mais 7
 * às 21h30) continuam separados no banco — cada lançamento tem sua situação
 * na cozinha, horário, cancelamento e estoque. Aqui eles só são JUNTADOS pra
 * mostrar: "12x Churrasco".
 */
export interface ItemGroup {
  key: string
  item_name: string
  unit_price: number
  notes: string | null
  quantity: number
  subtotal: number
  /** Lançamentos do grupo, na ordem em que foram feitos */
  items: OrderItem[]
}

function byLaunch(a: OrderItem, b: OrderItem) {
  return Date.parse(a.created_at) - Date.parse(b.created_at) || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0)
}

function group(items: OrderItem[], keyOf: (i: OrderItem) => string): ItemGroup[] {
  const groups = new Map<string, ItemGroup>()
  for (const it of [...items].sort(byLaunch)) {
    const key = keyOf(it)
    const g = groups.get(key)
    if (g) {
      g.quantity += it.quantity
      // soma em centavos: 0,10 + 0,20 em float dá 0,30000000000000004
      g.subtotal = Math.round(g.subtotal * 100 + Number(it.subtotal) * 100) / 100
      g.items.push(it)
    } else {
      groups.set(key, {
        key, item_name: it.item_name, unit_price: Number(it.unit_price), notes: it.notes ?? null,
        quantity: it.quantity, subtotal: Number(it.subtotal), items: [it],
      })
    }
  }
  // Map mantém a ordem de inserção: o grupo fica na posição do 1º lançamento
  return [...groups.values()]
}

const norm = (s: string | null | undefined) => (s ?? '').trim().toLowerCase()

/**
 * Pra conta do cliente (impressa / WhatsApp): junta mesmo nome + mesmo preço.
 * Observação não entra — ela nem aparece na conta, e "12x Churrasco" é o que
 * o cliente quer conferir. Cancelados ficam de fora.
 */
export function groupForReceipt(items: OrderItem[]): ItemGroup[] {
  return group(items.filter(i => i.status !== 'cancelled'),
    i => `${norm(i.item_name)}|${Number(i.unit_price).toFixed(2)}`)
}

/**
 * Pra tela da comanda: junta mesmo nome + preço + observação ("ao ponto" e
 * "bem passado" ficam separados — pra cozinha são coisas diferentes).
 */
export function groupForScreen(items: OrderItem[]): ItemGroup[] {
  return group(items, i => `${norm(i.item_name)}|${Number(i.unit_price).toFixed(2)}|${norm(i.notes)}`)
}

// ── Separação por noite (comandas mescladas de dias diferentes) ───────────────

/** A "noite" D vai de D 06:00 até D+1 06:00 — mesma regra do resumo da noite (backend). */
const NIGHT_CUTOFF_HOUR = 6
const WEEKDAY = ['dom', 'seg', 'ter', 'qua', 'qui', 'sex', 'sáb']

/** Chave da noite do lançamento ("2026-11-18"), em hora local. */
export function nightKey(iso: string): string {
  const d = new Date(Date.parse(iso) - NIGHT_CUTOFF_HOUR * 3600_000)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

/** "qua 18/11" */
export function nightLabel(key: string): string {
  const [y, m, d] = key.split('-').map(Number)
  return `${WEEKDAY[new Date(y, m - 1, d).getDay()]} ${String(d).padStart(2, '0')}/${String(m).padStart(2, '0')}`
}

export interface NightSection<T> {
  key: string
  label: string
  items: T[]
}

/**
 * Separa os lançamentos por noite, na ordem das noites. Comanda de uma noite
 * só → uma seção (quem chama não mostra cabeçalho). Usado quando duas
 * comandas de dias diferentes foram mescladas: o cliente precisa ver o que
 * pediu em cada dia.
 */
export function splitByNight(items: OrderItem[]): NightSection<OrderItem>[] {
  const map = new Map<string, OrderItem[]>()
  for (const it of [...items].sort(byLaunch)) {
    const k = nightKey(it.created_at)
    const list = map.get(k)
    if (list) list.push(it)
    else map.set(k, [it])
  }
  return [...map.keys()].sort().map(k => ({ key: k, label: nightLabel(k), items: map.get(k)! }))
}

export interface ReceiptSection {
  /** null quando a comanda é de uma noite só (conta sai igual sempre saiu) */
  label: string | null
  subtotal: number
  groups: ItemGroup[]
}

/** Conta do cliente: uma seção por noite (só se tiver mais de uma), itens agrupados dentro dela. */
export function receiptSections(items: OrderItem[]): ReceiptSection[] {
  const nights = splitByNight(items.filter(i => i.status !== 'cancelled'))
  if (nights.length <= 1) return [{ label: null, subtotal: 0, groups: groupForReceipt(items) }]
  return nights.map(n => {
    const groups = groupForReceipt(n.items)
    const subtotal = Math.round(groups.reduce((s, g) => s + g.subtotal * 100, 0)) / 100
    return { label: n.label, subtotal, groups }
  })
}
