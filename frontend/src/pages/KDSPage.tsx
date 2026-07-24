import { useState, useEffect, useCallback } from 'react'
import {
  type KitchenQueueTicket, type KitchenItemStatus,
  fetchKitchenQueue, updateKitchenItemStatus,
} from '../lib/api'
import { ErrorBanner, Spinner } from '../components/ui'

const NEXT_STATUS: Record<KitchenItemStatus, KitchenItemStatus | null> = {
  sent: 'preparing',
  preparing: 'ready',
  ready: null,
}

const STATUS_CFG: Record<KitchenItemStatus, { label: string; actionLabel: string; color: string; bg: string; border: string }> = {
  sent:      { label: 'Novo',       actionLabel: 'Iniciar preparo', color: 'text-blue-400',   bg: 'bg-blue-500/10',   border: 'border-blue-500/25' },
  preparing: { label: 'Preparando', actionLabel: 'Marcar pronto',   color: 'text-amber-400',  bg: 'bg-amber-500/10',  border: 'border-amber-500/25' },
  ready:     { label: 'Pronto',     actionLabel: '',                color: 'text-green-400',  bg: 'bg-green-500/10',  border: 'border-green-500/25' },
}

function minutesAgo(iso: string): number {
  return Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 60000))
}

function TicketItemRow({ orderId, item, onAdvance }: {
  orderId: string
  item: KitchenQueueTicket['items'][number]
  onAdvance: () => void
}) {
  const [loading, setLoading] = useState(false)
  const cfg = STATUS_CFG[item.status]
  const next = NEXT_STATUS[item.status]

  async function handleAdvance() {
    if (!next || loading) return
    setLoading(true)
    try {
      await updateKitchenItemStatus(orderId, item.id, next)
      onAdvance()
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex items-center justify-between gap-3 px-3 py-2.5 rounded-xl" style={{ background: 'var(--color-app-bg)' }}>
      <div className="min-w-0">
        <p className="text-stone-100 text-sm font-semibold truncate">{item.quantity}× {item.item_name}</p>
        {item.notes && <p className="text-stone-500 text-xs mt-0.5 italic truncate">{item.notes}</p>}
        <span className={['inline-block mt-1 text-[9px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded-full border', cfg.color, cfg.bg, cfg.border].join(' ')}>
          {cfg.label}
        </span>
      </div>
      {next && (
        <button onClick={handleAdvance} disabled={loading}
          className="shrink-0 px-3 py-2 rounded-xl text-xs font-semibold bg-amber-500 hover:bg-amber-400
                     text-stone-900 disabled:opacity-40 transition-colors">
          {loading ? '…' : cfg.actionLabel}
        </button>
      )}
    </div>
  )
}

function TicketCard({ ticket, onRefresh }: { ticket: KitchenQueueTicket; onRefresh: () => void }) {
  const age = minutesAgo(ticket.items[0]?.created_at ?? ticket.opened_at)
  const urgent = age >= 15

  return (
    <div className={['rounded-2xl border p-4', urgent ? 'border-red-500/40' : 'border-stone-800/60'].join(' ')}
         style={{ background: 'var(--color-app-surface)' }}>
      <div className="flex items-center justify-between gap-2 mb-3">
        <div>
          <p className="text-stone-100 text-sm font-bold leading-tight">
            {ticket.table_label ?? ticket.customer_name ?? 'Balcão'}
          </p>
          <p className="text-stone-600 text-xs mt-0.5">{ticket.guest_count} {ticket.guest_count === 1 ? 'pessoa' : 'pessoas'}</p>
        </div>
        <span className={['text-xs font-bold tabular-nums', urgent ? 'text-red-400' : 'text-stone-500'].join(' ')}>
          {age}min
        </span>
      </div>
      <div className="space-y-1.5">
        {ticket.items.map(item => (
          <TicketItemRow key={item.id} orderId={ticket.order_id} item={item} onAdvance={onRefresh} />
        ))}
      </div>
    </div>
  )
}

export default function KDSPage() {
  const [tickets, setTickets] = useState<KitchenQueueTicket[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      setError(null)
      setTickets(await fetchKitchenQueue())
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro ao carregar a fila')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  // Cozinha precisa de resposta rápida — polling mais curto que o resto do sistema (30s).
  useEffect(() => {
    const id = setInterval(load, 8_000)
    return () => clearInterval(id)
  }, [load])

  return (
    <div className="h-full overflow-y-auto">
      <div className="max-w-6xl mx-auto px-4 sm:px-6 py-6">
        <div className="flex items-center justify-between gap-3 mb-5">
          <div>
            <h1 className="text-stone-100 text-xl font-bold leading-tight">Cozinha</h1>
            <p className="text-stone-500 text-sm mt-1">
              {tickets.reduce((n, t) => n + t.items.length, 0)} itens em preparo
            </p>
          </div>
        </div>

        {error && <ErrorBanner message={error} onRetry={load} />}

        {loading ? (
          <Spinner />
        ) : tickets.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-20 text-center">
            <div className="w-12 h-12 rounded-2xl bg-stone-800/60 flex items-center justify-center mb-3 text-2xl">🍳</div>
            <p className="text-stone-400 text-sm font-medium">Fila vazia</p>
            <p className="text-stone-600 text-xs mt-1">Novos pedidos aparecem aqui automaticamente</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
            {tickets.map(ticket => (
              <TicketCard key={ticket.order_id} ticket={ticket} onRefresh={load} />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
