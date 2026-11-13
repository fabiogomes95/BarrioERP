import { describe, expect, it } from 'vitest'
import { remainingToPay } from './api'

describe('remainingToPay', () => {
  it('desconta o que já foi pago', () => {
    expect(remainingToPay({ total: '50.00', paid: '30.00' })).toBe(20)
  })
  it('sem pagamento mostra o total', () => {
    expect(remainingToPay({ total: '19.80' })).toBeCloseTo(19.8)
    expect(remainingToPay({ total: '19.80', paid: '0' })).toBeCloseTo(19.8)
  })
  it('nunca fica negativo', () => {
    expect(remainingToPay({ total: '10.00', paid: '12.00' })).toBe(0)
  })
})
