import { describe, expect, it } from 'vitest'
import { paidSlots, splitAmounts, splitByShares } from './split'

const sumCents = (xs: number[]) => xs.reduce((a, b) => a + Math.round(b * 100), 0)

describe('splitAmounts (dividir igual)', () => {
  it('R$ 100 em 3: a soma fecha exatamente, centavo extra vai pro primeiro', () => {
    expect(splitAmounts(100, 3)).toEqual([33.34, 33.33, 33.33])
  })

  it('nunca perde nem cria centavo, em vários totais e números de pessoas', () => {
    for (const total of [0.01, 7.77, 74.8, 199.99, 1234.56]) {
      for (let n = 1; n <= 12; n++) {
        const parts = splitAmounts(total, n)
        expect(parts).toHaveLength(n)
        expect(sumCents(parts)).toBe(Math.round(total * 100))
        // diferença máxima entre partes: 1 centavo
        expect(Math.round((Math.max(...parts) - Math.min(...parts)) * 100)).toBeLessThanOrEqual(1)
      }
    }
  })

  it('valores de ponto flutuante problemáticos (0,1 + 0,2) não quebram', () => {
    expect(sumCents(splitAmounts(0.1 + 0.2, 2))).toBe(30)
  })
})

describe('splitByShares (cada um paga o que consumiu)', () => {
  it('proporcional ao consumo, inclusive com a taxa de serviço embutida', () => {
    // consumo 60 e 40, total com 10% = 110
    expect(splitByShares(110, [60, 40])).toEqual([66, 44])
  })

  it('fecha o total exato mesmo com frações que não dividem', () => {
    const parts = splitByShares(100, [1, 1, 1])
    expect(sumCents(parts)).toBe(10000)
    expect(parts.sort()).toEqual([33.33, 33.33, 33.34])
  })

  it('maiores restos: o centavo vai pra quem perdeu mais no arredondamento', () => {
    // 10,00 em 2/3 e 1/3 → 6,666… e 3,333… → 6,67 e 3,33
    expect(splitByShares(10, [2, 1])).toEqual([6.67, 3.33])
  })

  it('pessoa sem item fica com zero; ninguém com item → tudo zero', () => {
    expect(splitByShares(50, [50, 0])).toEqual([50, 0])
    expect(splitByShares(50, [0, 0])).toEqual([0, 0])
  })

  it('nunca perde centavo com consumos variados', () => {
    const cases: [number, number[]][] = [[187.33, [45.5, 12, 99.9]], [74.8, [6, 6, 6, 6, 6, 6, 6]], [1, [3, 3, 3]]]
    for (const [total, shares] of cases) expect(sumCents(splitByShares(total, shares))).toBe(Math.round(total * 100))
  })
})

describe('paidSlots (quais parcelas já foram pagas)', () => {
  it('marca as primeiras parcelas cobertas pelo valor pago', () => {
    expect(paidSlots([33.34, 33.33, 33.33], 0)).toEqual([false, false, false])
    expect(paidSlots([33.34, 33.33, 33.33], 33.34)).toEqual([true, false, false])
    expect(paidSlots([33.34, 33.33, 33.33], 66.67)).toEqual([true, true, false])
    expect(paidSlots([33.34, 33.33, 33.33], 100)).toEqual([true, true, true])
  })

  it('tolera o erro de arredondamento do ponto flutuante', () => {
    // 0,1 + 0,2 = 0,30000000000000004 em JS
    expect(paidSlots([0.1, 0.2], 0.3)).toEqual([true, true])
  })

  it('pagamento parcial de uma parcela não a marca como paga', () => {
    expect(paidSlots([50, 50], 49.99)).toEqual([false, false])
  })
})
