import { describe, expect, it } from 'vitest'
import type { OrderItem } from './api'
import { groupForReceipt, groupForScreen } from './groupItems'

let n = 0
function item(p: Partial<OrderItem>): OrderItem {
  n++
  return {
    id: `id-${String(n).padStart(3, '0')}`, order_id: 'o1', item_name: 'Churrasco', unit_price: '15.00',
    quantity: 1, subtotal: '15.00', notes: null, status: 'served', cancelled_at: null, cancelled_reason: null,
    created_at: `2026-11-13T20:${String(n).padStart(2, '0')}:00Z`, updated_at: '2026-11-13T22:00:00Z', ...p,
  }
}

describe('groupForReceipt', () => {
  it('junta 5 + 7 churrascos lançados em horas diferentes', () => {
    const g = groupForReceipt([
      item({ quantity: 5, subtotal: '75.00' }),
      item({ item_name: 'Cerveja', unit_price: '12.00', quantity: 2, subtotal: '24.00' }),
      item({ quantity: 7, subtotal: '105.00', status: 'preparing' }),
    ])
    expect(g.map(x => [x.item_name, x.quantity, x.subtotal])).toEqual([
      ['Churrasco', 12, 180], ['Cerveja', 2, 24],
    ])
    expect(g[0].unit_price).toBe(15)
    expect(g[0].items).toHaveLength(2)
  })

  it('preço diferente não junta (promoção, preço alterado no meio da noite)', () => {
    const g = groupForReceipt([item({}), item({ unit_price: '12.00', subtotal: '12.00' })])
    expect(g).toHaveLength(2)
  })

  it('cancelado não entra na conta', () => {
    const g = groupForReceipt([item({ quantity: 5, subtotal: '75.00' }), item({ quantity: 7, subtotal: '105.00', status: 'cancelled' })])
    expect(g).toEqual([expect.objectContaining({ quantity: 5, subtotal: 75 })])
  })

  it('observação não separa na conta (ela nem aparece lá)', () => {
    expect(groupForReceipt([item({ notes: 'ao ponto' }), item({ notes: 'bem passado' })])).toHaveLength(1)
  })

  it('soma centavos sem erro de float', () => {
    const g = groupForReceipt([item({ unit_price: '0.10', subtotal: '0.10' }), item({ unit_price: '0.10', subtotal: '0.10' }),
      item({ unit_price: '0.10', subtotal: '0.10' })])
    expect(g[0].subtotal).toBe(0.3)
  })

  it('grupo fica na posição do primeiro lançamento', () => {
    const g = groupForReceipt([
      item({ item_name: 'Cerveja', created_at: '2026-11-13T21:00:00Z' }),
      item({ item_name: 'Churrasco', created_at: '2026-11-13T20:00:00Z' }),
      item({ item_name: 'Churrasco', created_at: '2026-11-13T22:00:00Z' }),
    ])
    expect(g.map(x => x.item_name)).toEqual(['Churrasco', 'Cerveja'])
  })
})

describe('groupForScreen', () => {
  it('observação diferente fica separada (pra cozinha é outra coisa)', () => {
    expect(groupForScreen([item({ notes: 'ao ponto' }), item({ notes: 'bem passado' }), item({ notes: 'Ao ponto ' })]))
      .toHaveLength(2)
  })
})
