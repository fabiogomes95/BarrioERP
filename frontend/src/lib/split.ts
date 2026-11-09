// Divisão da conta entre pessoas — exata em centavos (a soma das partes
// sempre fecha com o total, sem sobrar nem faltar 1 centavo).

/** Divide `total` (R$) em `count` partes exatas em centavos (sem perda de precisão). */
export function splitAmounts(total: number, count: number): number[] {
  const totalCents = Math.round(total * 100)
  const base = Math.floor(totalCents / count)
  const remainder = totalCents - base * count
  return Array.from({ length: count }, (_, i) => (base + (i < remainder ? 1 : 0)) / 100)
}

/** Distribui `total` (R$) proporcionalmente aos subtotais de cada pessoa, exato em centavos. */
export function splitByShares(total: number, shares: number[]): number[] {
  const totalCents = Math.round(total * 100)
  const shareSum = shares.reduce((a, b) => a + b, 0)
  if (shareSum <= 0) return shares.map(() => 0)

  const raw = shares.map(s => (s / shareSum) * totalCents)
  const cents = raw.map(v => Math.floor(v))
  const remainder = totalCents - cents.reduce((a, b) => a + b, 0)

  // Método dos maiores restos: sobra de centavos vai pra quem tem a maior fração perdida no floor.
  const order = raw
    .map((v, i) => ({ i, frac: v - Math.floor(v) }))
    .sort((a, b) => b.frac - a.frac)
  for (let k = 0; k < remainder; k++) cents[order[k % order.length].i] += 1

  return cents.map(c => c / 100)
}

/**
 * Quais parcelas já estão pagas: as primeiras N cujo valor acumulado cabe no
 * que já foi pago (tolerância de meio centavo pro arredondamento).
 */
export function paidSlots(amounts: number[], paid: number): boolean[] {
  let acc = 0
  return amounts.map(a => { acc += a; return acc <= paid + 0.005 })
}
