import { describe, expect, it } from 'vitest'
import { csvField } from './reportExport'

describe('csvField', () => {
  it('neutraliza fórmula vinda de nome de cliente', () => {
    expect(csvField('=HYPERLINK("http://x","clique")')).toBe(`"'=HYPERLINK(""http://x"",""clique"")"`)
    expect(csvField('+5511999')).toBe("'+5511999")
    expect(csvField('@SUM(A1)')).toBe("'@SUM(A1)")
  })
  it('texto e números comuns passam iguais', () => {
    expect(csvField('Mesa 3')).toBe('Mesa 3')
    expect(csvField(42)).toBe('42')
  })
  it('valor negativo vira texto, não fórmula', () => {
    expect(csvField('-10')).toBe("'-10")
  })
})

describe('csvField com número', () => {
  it('número negativo continua número', () => {
    expect(csvField(-3)).toBe('-3')
  })
})
