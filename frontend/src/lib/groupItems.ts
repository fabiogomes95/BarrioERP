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
