import { useEffect, useState } from 'react'
import { type MovementReport as Report, fetchMovementReport } from '../lib/api'
import { brl } from '../lib/format'

const DAY = ['Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta', 'Sábado', 'Domingo']
const DAY_SHORT = ['Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb', 'Dom']

/**
 * Caixa → Período: "Movimento por dia e horário".
 * Média por NOITE de cada dia da semana (sábado 1h conta como sexta), mapa
 * de horário de pico (hora em que a comanda abriu) e o que mais sai em cada
 * dia — pra escalar equipe e planejar compra. start/end = YYYY-MM-DD.
 */
export default function MovementReport({ start, end }: { start: string; end: string }) {
  const [report, setReport] = useState<Report | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let alive = true
    setError(null)
    fetchMovementReport(start, end)
      .then(r => { if (alive) setReport(r) })
      .catch(err => { if (alive) setError(err instanceof Error ? err.message : 'Erro ao carregar') })
    return () => { alive = false }
  }, [start, end])

  if (error) return <p className="text-red-400 text-xs mt-6">Movimento: {error}</p>
  if (!report) return null

  const open = report.weekdays.filter(w => w.nights > 0)
  if (open.length === 0) return null

  const maxRevenue = Math.max(...open.map(w => Number(w.revenue_per_night)))
  const best = open.reduce((a, b) => (Number(b.revenue_per_night) > Number(a.revenue_per_night) ? b : a))

  // Mapa de calor: só os dias e as horas que tiveram movimento, na ordem da
  // noite (16h → 23h → 0h → 5h), não do relógio
  const nightOrder = (h: number) => (h + 24 - 6) % 24
  const hours = [...new Set(report.heatmap.map(c => c.hour))].sort((a, b) => nightOrder(a) - nightOrder(b))
  const cell = new Map(report.heatmap.map(c => [`${c.weekday}-${c.hour}`, c.orders_count]))
  const maxCell = Math.max(1, ...report.heatmap.map(c => c.orders_count))
  const peak = report.heatmap.reduce((a, b) => (b.orders_count > a.orders_count ? b : a), report.heatmap[0])

  return (
    <section className="mt-8">
      <h2 className="text-stone-200 text-sm font-bold mb-1">Movimento por dia e horário</h2>
      <p className="text-stone-500 text-xs mb-3">
        Melhor noite: <span className="text-amber-400 font-semibold">{DAY[best.weekday]}</span>
        {' '}({brl(best.revenue_per_night)} em média)
        {peak && <> · Pico: <span className="text-amber-400 font-semibold">{DAY_SHORT[peak.weekday]} {peak.hour}h</span></>}
      </p>

      {/* Média por noite de cada dia */}
      <div className="rounded-2xl border border-stone-800/60 p-4 space-y-3" style={{ background: 'var(--color-app-surface)' }}>
        {open.map(w => (
          <div key={w.weekday}>
            <div className="flex items-baseline justify-between gap-3 text-sm">
              <span className="text-stone-200 font-semibold w-20 shrink-0">{DAY[w.weekday]}</span>
              <span className="flex-1 text-stone-500 text-xs truncate">
                {w.orders_per_night} comandas/noite · {w.nights} {w.nights === 1 ? 'noite' : 'noites'}
              </span>
              <span className="text-stone-200 font-bold shrink-0">{brl(w.revenue_per_night)}</span>
            </div>
            <div className="h-1.5 rounded-full bg-stone-800/60 mt-1.5 overflow-hidden">
              <div className="h-full rounded-full bg-amber-500/70"
                   style={{ width: `${(Number(w.revenue_per_night) / maxRevenue) * 100}%` }} />
            </div>
            {w.top_items.length > 0 && (
              <p className="text-stone-500 text-[11px] mt-1 truncate">
                Mais saem: {w.top_items.map(t => `${t.name} (${t.quantity})`).join(' · ')}
              </p>
            )}
          </div>
        ))}
      </div>

      {/* Horário de pico */}
      {hours.length > 0 && (
        <div className="rounded-2xl border border-stone-800/60 p-4 mt-3 overflow-x-auto" style={{ background: 'var(--color-app-surface)' }}>
          <p className="text-stone-400 text-xs font-semibold mb-2">Comandas abertas por hora</p>
          <table className="border-separate" style={{ borderSpacing: 3 }}>
            <thead>
              <tr>
                <th />
                {hours.map(h => <th key={h} className="text-stone-600 text-[10px] font-medium w-7">{h}h</th>)}
              </tr>
            </thead>
            <tbody>
              {open.map(w => (
                <tr key={w.weekday}>
                  <td className="text-stone-400 text-[11px] font-semibold pr-1.5">{DAY_SHORT[w.weekday]}</td>
                  {hours.map(h => {
                    const n = cell.get(`${w.weekday}-${h}`) ?? 0
                    return (
                      <td key={h} title={`${DAY[w.weekday]} ${h}h: ${n} comandas`}
                          className="h-6 w-7 rounded text-center text-[10px] font-semibold"
                          style={{
                            background: n ? `rgba(245, 158, 11, ${0.12 + 0.75 * (n / maxCell)})` : 'transparent',
                            color: n / maxCell > 0.55 ? '#1c1917' : 'var(--color-text-muted, #a8a29e)',
                          }}>
                        {n || ''}
                      </td>
                    )
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
