import { describe, expect, it } from 'vitest'
import { brl, maskCurrency, parseCurrency, timeAgo, toCurrencyInput } from './format'

// toLocaleString põe um espaço não separável (U+00A0) entre "R$" e o número
const norm = (s: string) => s.replace(/\u00a0/g, ' ')

describe('máscara de moeda (campo de valor do caixa)', () => {
  it('posiciona a vírgula conforme os dígitos', () => {
    expect(maskCurrency('4')).toBe('0,04')
    expect(maskCurrency('48')).toBe('0,48')
    expect(maskCurrency('4800')).toBe('48,00')
    expect(maskCurrency('125000')).toBe('1.250,00')
  })

  it('ignora letras/símbolos e deixa vazio quando não há dígito', () => {
    expect(maskCurrency('R$ 1a2b3')).toBe('1,23')
    expect(maskCurrency('')).toBe('')
    expect(maskCurrency('abc')).toBe('')
  })

  it('ida e volta: o que é digitado é o que é cobrado', () => {
    for (const v of [0.01, 4.5, 48, 74.8, 1250, 99999.99]) {
      expect(parseCurrency(toCurrencyInput(v))).toBeCloseTo(v, 2)
    }
  })

  it('parseCurrency: milhar e decimal no formato brasileiro', () => {
    expect(parseCurrency('1.250,00')).toBe(1250)
    expect(parseCurrency('48,00')).toBe(48)
    expect(parseCurrency('  ')).toBeNaN()
  })

  it('toCurrencyInput aceita o texto "48.00" que vem da API', () => {
    expect(toCurrencyInput('48.00')).toBe('48,00')
    expect(toCurrencyInput('abc')).toBe('')
  })
})

describe('brl e timeAgo', () => {
  it('formata em reais', () => {
    expect(norm(brl(1250.5))).toBe('R$ 1.250,50')
    expect(norm(brl('74.8'))).toBe('R$ 74,80')
  })

  it('tempo curto desde um horário', () => {
    const ago = (ms: number) => new Date(Date.now() - ms).toISOString()
    expect(timeAgo(ago(10_000))).toBe('agora')
    expect(timeAgo(ago(5 * 60_000))).toBe('5min')
    expect(timeAgo(ago(3 * 3_600_000))).toBe('3h')
    expect(timeAgo(ago(2 * 86_400_000))).toBe('2d')
  })
})
