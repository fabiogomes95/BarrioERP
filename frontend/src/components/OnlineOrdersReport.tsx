import { useEffect, useState } from 'react'
import { type OnlineOrdersReport as Report, fetchOnlineOrdersReport } from '../lib/api'
import { brl } from './OrderDetailView'

/**
 * Bloco "Pedidos online" da tela de Caixa — segue o mesmo intervalo do
 * relatório escolhido (dia, período ou turno). start/end no formato do
 * <input type="datetime-local">, end exclusivo.
 */
export default function OnlineOrdersReport({ start, end }: { start: string; end: string }) {
  const [report, setReport] = useState<Report | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let alive = true
    setError(null)
    fetchOnlineOrdersReport(start, end)
      .then(r => { if (alive) setReport(r) })
      .catch(err => { if (alive) setError(err instanceof Error ? err.message : 'Erro ao carregar') })
    return () => { alive = false }
  }, [start, end])

  if (error) return <p className="text-red-400 text-xs mt-6">Pedidos online: {error}</p>
  if (!report) return null

  const acceptRate = report.received > 0 ? Math.round((report.accepted / report.received) * 100) : 0

  return (
    <section className="mt-8">
      <h2 className="text-stone-200 text-sm font-bold mb-3 flex items-center gap-2">
        <span className="w-2 h-2 rounded-full bg-emerald-500" />
        Pedidos online (cardápio)
      </h2>

      {report.received === 0 ? (
        <p className="text-stone-600 text-sm rounded-2xl border border-stone-800/60 px-4 py-6 text-center"
           style={{ background: 'var(--color-app-surface)' }}>
          Nenhum pedido pelo cardápio nesse intervalo.
        </p>
      ) : (
        <>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-3">
            <Tile label="Recebidos" value={String(report.received)}
              hint={report.pending > 0 ? `${report.pending} aguardando` : undefined} />
            <Tile label="Aceitos" value={String(report.accepted)}
              hint={`${acceptRate}%${report.rejected ? ` · ${report.rejected} recusados` : ''}`} accent="green" />
            <Tile label="Valor aceito" value={brl(report.accepted_total)} accent="amber" />
            <Tile label="Ticket médio" value={brl(report.average_ticket)}
              hint={`${report.delivery} entrega · ${report.pickup} retirada`} />
          </div>

          {report.top_items.length > 0 && (
            <div className="rounded-2xl border border-stone-800/60 p-4" style={{ background: 'var(--color-app-surface)' }}>
              <p className="text-stone-500 text-[11px] font-semibold uppercase tracking-wider mb-2">Mais pedidos online</p>
              {report.top_items.map(it => (
                <div key={it.name} className="flex items-center justify-between py-1.5 border-b border-stone-800/40 last:border-0">
                  <span className="text-stone-300 text-sm truncate mr-3">{it.name}</span>
                  <span className="flex items-center gap-3 shrink-0">
                    <span className="text-amber-400 text-sm font-bold">{it.quantity}×</span>
                    <span className="text-stone-500 text-xs w-20 text-right">{brl(it.total)}</span>
                  </span>
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </section>
  )
}

function Tile({ label, value, hint, accent = 'stone' }: {
  label: string; value: string; hint?: string; accent?: 'amber' | 'green' | 'stone'
}) {
  const c = { amber: 'text-amber-400', green: 'text-green-400', stone: 'text-stone-200' }[accent]
  return (
    <div className="rounded-2xl p-4 border border-stone-800/60" style={{ background: 'var(--color-app-surface)' }}>
      <p className="text-stone-500 text-[11px] font-semibold uppercase tracking-wider">{label}</p>
      <p className={['text-xl font-black mt-1.5 leading-none', c].join(' ')}>{value}</p>
      {hint && <p className="text-stone-600 text-xs mt-1.5">{hint}</p>}
    </div>
  )
}
