import { useEffect, useState } from 'react'
import { type CustomerEntry, type CustomersReport as Report, fetchCustomersReport } from '../lib/api'
import { brl } from '../lib/format'
import { whatsLink } from '../lib/whatsapp'

function formatPhone(digits: string) {
  const d = digits.length > 11 && digits.startsWith('55') ? digits.slice(2) : digits
  return d.length >= 10 ? `(${d.slice(0, 2)}) ${d.slice(2, -4)}-${d.slice(-4)}` : d
}

function since(days: number) {
  if (days <= 0) return 'hoje'
  if (days === 1) return 'ontem'
  if (days < 60) return `há ${days} dias`
  return `há ${Math.round(days / 30)} meses`
}

function CustomerRow({ c, invite }: { c: CustomerEntry; invite?: boolean }) {
  const first = c.name.split(' ')[0]
  const msg = invite
    ? `Oi ${first}! Aqui é do Recanto da Barra. Faz um tempinho que você não pede. ` +
      `${c.favorite_item ? `Bateu saudade de ${c.favorite_item}? ` : ''}` +
      `O cardápio está em recantodabarra.github.io`
    : undefined
  return (
    <div className="flex items-center gap-3 py-2.5 border-b border-stone-800/50 last:border-0">
      <div className="flex-1 min-w-0">
        <p className="text-stone-200 text-sm font-semibold truncate">
          {c.name} <span className="text-stone-600 font-normal text-xs">{formatPhone(c.phone)}</span>
        </p>
        <p className="text-stone-500 text-xs truncate">
          {c.orders_count} {c.orders_count === 1 ? 'pedido' : 'pedidos'} · {brl(c.total)}
          {' · '}último {since(c.days_since_last)}
          {c.favorite_item && <> · gosta de <span className="text-stone-400">{c.favorite_item}</span></>}
        </p>
      </div>
      <a href={whatsLink(c.phone, msg)}
         className={['shrink-0 px-2.5 py-1.5 rounded-lg text-xs font-bold',
           invite ? 'bg-emerald-500 hover:bg-emerald-400 text-stone-900'
                  : 'text-emerald-400 hover:bg-emerald-500/10'].join(' ')}>
        {invite ? 'Chamar' : 'WhatsApp'}
      </a>
    </div>
  )
}

/**
 * Caixa → Período: "Clientes do delivery". Pedidos online aceitos dos
 * últimos 12 meses (só eles têm telefone), agrupados por telefone —
 * não segue o período escolhido. "Sumiu" = pediu 2+ vezes e não pede há
 * mais de 30 dias; o botão abre o WhatsApp com um convite pronto.
 */
export default function CustomersReport() {
  const [report, setReport] = useState<Report | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [showAll, setShowAll] = useState(false)

  useEffect(() => {
    let alive = true
    fetchCustomersReport()
      .then(r => { if (alive) setReport(r) })
      .catch(err => { if (alive) setError(err instanceof Error ? err.message : 'Erro ao carregar') })
    return () => { alive = false }
  }, [])

  if (error) return <p className="text-red-400 text-xs mt-6">Clientes: {error}</p>
  if (!report || report.customers_count === 0) return null

  const top = showAll ? report.top : report.top.slice(0, 8)

  return (
    <section className="mt-8">
      <h2 className="text-stone-200 text-sm font-bold mb-1">Clientes do delivery</h2>
      <p className="text-stone-500 text-xs mb-3">
        Últimos 12 meses · {report.customers_count} {report.customers_count === 1 ? 'cliente' : 'clientes'}
        {' · '}{report.returning_count} voltaram a pedir
      </p>

      {report.lapsed.length > 0 && (
        <div className="rounded-2xl border border-amber-500/30 bg-amber-500/5 px-4 py-2 mb-3">
          <p className="text-amber-400 text-xs font-bold pt-1.5 pb-1">
            Sumiram ({report.lapsed.length}): pediam e pararam há mais de 30 dias
          </p>
          {report.lapsed.slice(0, 10).map(c => <CustomerRow key={c.phone} c={c} invite />)}
        </div>
      )}

      <div className="rounded-2xl border border-stone-800/60 px-4 py-1" style={{ background: 'var(--color-app-surface)' }}>
        <p className="text-stone-400 text-xs font-semibold pt-2.5 pb-1">Quem mais pede</p>
        {top.map(c => <CustomerRow key={c.phone} c={c} />)}
        {report.top.length > 8 && (
          <button onClick={() => setShowAll(v => !v)}
            className="w-full py-2 text-xs font-semibold text-stone-500 hover:text-amber-400">
            {showAll ? 'Mostrar menos' : `Ver todos (${report.top.length})`}
          </button>
        )}
      </div>
    </section>
  )
}
