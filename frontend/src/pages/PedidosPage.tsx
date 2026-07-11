import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { type Order, type Table, type OrderType, fetchOpenOrders, fetchTables, createOrder, getUser } from '../lib/api'
import { brl, timeAgo, ORDER_STATUS } from '../components/OrderDetailView'
import { inputCls, Field, ModalOverlay } from '../components/ui'

const ORDER_TYPE_LABEL: Record<string, string> = {
  counter: 'Balcão',
  delivery: 'Delivery',
  pickup: 'Retirada',
}

// ── Helpers de modal ──────────────────────────────────────────────────────────

// ── Card de comanda (grade) ───────────────────────────────────────────────────

function OrderCard({ order, table, onClick }: {
  order: Order
  table: Table | undefined
  onClick: () => void
}) {
  const cfg = ORDER_STATUS[order.status] ?? ORDER_STATUS.open
  const activeItems = order.items.filter(i => i.status !== 'cancelled').length
  const title = order.customer_name ?? table?.label ?? 'Comanda avulsa'

  return (
    <button onClick={onClick}
      className="group w-full text-left rounded-2xl border border-stone-800/50 p-4
                 transition-all duration-150 relative overflow-hidden
                 hover:border-stone-700/70 hover:-translate-y-0.5 hover:shadow-lg hover:shadow-black/40 active:translate-y-0"
      style={{ background: '#161210' }}>

      {/* Topo: identificação + status */}
      <div className="flex items-start justify-between gap-2 mb-2.5">
        <div className="flex items-center gap-2.5 min-w-0">
          <div className="w-10 h-10 rounded-xl bg-stone-800 border border-stone-700/50
                          flex items-center justify-center shrink-0">
            <span className="text-base font-black text-stone-100">
              {table?.number ?? '•'}
            </span>
          </div>
          <div className="min-w-0">
            <p className="text-stone-100 text-sm font-semibold leading-tight truncate">{title}</p>
            <p className="text-stone-600 text-xs mt-0.5">
              {table ? `Mesa ${table.number}` : (ORDER_TYPE_LABEL[order.order_type] ?? 'Balcão')} · {timeAgo(order.created_at)}
            </p>
          </div>
        </div>
        <span className={[
          'shrink-0 text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full border',
          cfg.color, cfg.bg, cfg.border,
        ].join(' ')}>
          {cfg.label}
        </span>
      </div>

      {/* Base: itens + total (total só pra quem lida com pagamento) */}
      <div className="flex items-center justify-between pt-2.5 border-t border-stone-800/50">
        <span className="text-stone-600 text-xs">{activeItems} {activeItems === 1 ? 'item' : 'itens'}</span>
        {getUser()?.role !== 'waiter' && getUser()?.role !== 'kitchen' && (
          <span className="text-amber-400 text-sm font-bold">{brl(order.total)}</span>
        )}
      </div>
    </button>
  )
}

// ── Modal: Novo pedido (mesa opcional) ────────────────────────────────────────

const ORDER_TYPES: { value: OrderType | 'table'; label: string; icon: string; desc: string }[] = [
  { value: 'table',    label: 'Mesa',     icon: '🪑', desc: 'Selecione a mesa' },
  { value: 'counter',  label: 'Balcão',   icon: '🍺', desc: 'Pedido no balcão' },
  { value: 'delivery', label: 'Delivery', icon: '🛵', desc: 'Entrega no endereço' },
  { value: 'pickup',   label: 'Retirada', icon: '📦', desc: 'Cliente retira' },
]

function NewOrderModal({ onClose, onCreated }: {
  onClose: () => void
  onCreated: (o: Order) => void
}) {
  const [tables, setTables] = useState<Table[]>([])
  const [loading, setLoading] = useState(true)
  const [mode, setMode] = useState<'table' | OrderType>('counter')
  const [tableId, setTableId] = useState('')
  const [guestCount, setGuestCount] = useState('1')
  const [customerName, setCustomerName] = useState('')
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchTables()
      .then(ts => setTables(ts.filter(t => t.status === 'free' || t.status === 'reserved')))
      .finally(() => setLoading(false))
  }, [])

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    if (mode === 'table' && !tableId) { setError('Selecione uma mesa'); return }
    setCreating(true)
    try {
      const order = await createOrder({
        table_id: mode === 'table' ? (tableId || null) : null,
        order_type: mode === 'table' ? 'counter' : mode,
        guest_count: Number(guestCount),
        customer_name: customerName.trim() || null,
      })
      onCreated(order)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro ao criar pedido')
    } finally {
      setCreating(false)
    }
  }

  return (
    <ModalOverlay onClose={onClose}>
      <h2 className="text-stone-100 text-base font-bold mb-4">Novo pedido</h2>

      {/* Seletor de tipo */}
      <div className="grid grid-cols-4 gap-1.5 mb-4">
        {ORDER_TYPES.map(t => (
          <button key={t.value} type="button" onClick={() => setMode(t.value)}
            className={[
              'flex flex-col items-center gap-1 py-2.5 rounded-xl text-[11px] font-semibold transition-all border',
              mode === t.value
                ? 'bg-amber-500/15 text-amber-400 border-amber-500/30'
                : 'text-stone-500 border-stone-800/60 hover:text-stone-300',
            ].join(' ')}>
            <span className="text-lg leading-none">{t.icon}</span>
            {t.label}
          </button>
        ))}
      </div>

      {error && (
        <p className="text-red-400 text-xs bg-red-500/10 border border-red-500/20
                       rounded-xl px-3 py-2.5 mb-4">{error}</p>
      )}

      {loading ? (
        <div className="text-center py-6 text-stone-600 text-sm">Carregando…</div>
      ) : (
        <form onSubmit={handleSubmit} className="space-y-3.5">
          {mode === 'table' && (
            <Field label="Mesa">
              <select value={tableId} onChange={e => setTableId(e.target.value)}
                className={inputCls + ' appearance-none'} style={{ background: '#0d0b08' }}>
                <option value="">Selecione a mesa…</option>
                {tables.map(t => (
                  <option key={t.id} value={t.id}>
                    Mesa {t.number} — {t.label}{t.section ? ` (${t.section})` : ''}
                  </option>
                ))}
              </select>
            </Field>
          )}
          {mode === 'table' && (
            <div className="grid grid-cols-2 gap-3">
              <Field label="Pessoas">
                <input type="number" min={1} max={200} required value={guestCount}
                  onChange={e => setGuestCount(e.target.value)}
                  className={inputCls} style={{ background: '#0d0b08' }} />
              </Field>
              <div />
            </div>
          )}
          <Field label="Cliente (opcional)">
            <input type="text" value={customerName} onChange={e => setCustomerName(e.target.value)}
              placeholder="Deixe vazio para numerar automaticamente"
              className={inputCls} style={{ background: '#0d0b08' }} />
          </Field>
          <div className="flex gap-2 pt-1">
            <button type="button" onClick={onClose}
              className="flex-1 py-2.5 rounded-xl text-sm font-semibold
                         text-stone-400 border border-stone-700/60 hover:bg-stone-800/50 transition-colors">
              Cancelar
            </button>
            <button type="submit" disabled={creating}
              className="flex-1 py-2.5 rounded-xl text-sm font-semibold
                         bg-amber-500 hover:bg-amber-400 text-stone-900
                         disabled:opacity-40 transition-colors">
              {creating ? 'Criando…' : 'Criar pedido'}
            </button>
          </div>
        </form>
      )}
    </ModalOverlay>
  )
}

// ── Página principal ──────────────────────────────────────────────────────────

export default function PedidosPage() {
  const navigate = useNavigate()
  const [orders, setOrders] = useState<Order[]>([])
  const [tables, setTables] = useState<Table[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [showNewOrder, setShowNewOrder] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [os, ts] = await Promise.all([fetchOpenOrders(), fetchTables()])
      setOrders(os)
      setTables(ts)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro ao carregar')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  // Auto-refresh silencioso a cada 30s
  useEffect(() => {
    const id = setInterval(async () => {
      try {
        const [os, ts] = await Promise.all([fetchOpenOrders(), fetchTables()])
        setOrders(os)
        setTables(ts)
      } catch {}
    }, 30_000)
    return () => clearInterval(id)
  }, [])

  const visible = orders.filter(o => {
    if (!search) return true
    const q = search.toLowerCase()
    const table = tables.find(t => t.id === o.table_id)
    const avulsa = !o.table_id && ('balcão balcao avulso avulsa'.includes(q))
    return (
      o.customer_name?.toLowerCase().includes(q) ||
      table?.label.toLowerCase().includes(q) ||
      table?.section?.toLowerCase().includes(q) ||
      String(table?.number ?? '').includes(q) ||
      avulsa
    )
  })

  return (
    <div className="h-full flex flex-col">

      {/* Cabeçalho */}
      <div className="px-5 pt-5 pb-4 border-b border-stone-800/50 shrink-0"
           style={{ background: '#0f0d0a' }}>
        <div className="flex items-start justify-between gap-4 mb-4">
          <div>
            <h1 className="text-stone-100 text-lg font-bold leading-tight">Pedidos</h1>
            {!loading && (
              <p className="text-stone-500 text-xs mt-0.5">
                {orders.length} {orders.length === 1 ? 'comanda aberta' : 'comandas abertas'}
              </p>
            )}
          </div>
          <div className="flex items-center gap-2">
            <button onClick={load} disabled={loading}
              className="flex items-center justify-center w-9 h-9 rounded-xl
                         border border-stone-800/60 text-stone-500 hover:text-stone-300
                         hover:border-stone-700/60 disabled:opacity-40 transition-all"
              style={{ background: '#161210' }} title="Atualizar">
              <svg className={['w-4 h-4', loading ? 'animate-spin' : ''].join(' ')}
                   fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round"
                      d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
              </svg>
            </button>
            <button onClick={() => setShowNewOrder(true)}
              className="flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-semibold
                         bg-amber-500 hover:bg-amber-400 text-stone-900 transition-colors">
              <span className="text-base leading-none">+</span>
              Novo
            </button>
          </div>
        </div>

        {/* Busca */}
        <div className="relative">
          <svg className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-stone-600 pointer-events-none"
               fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-4.35-4.35M17 11A6 6 0 105 11a6 6 0 0012 0z" />
          </svg>
          <input type="text" value={search} onChange={e => setSearch(e.target.value)}
            placeholder="Buscar por mesa, cliente ou comanda avulsa…"
            className="w-full pl-9 pr-4 py-2.5 rounded-xl text-sm border border-stone-800/60
                       text-stone-200 placeholder-stone-600 focus:outline-none
                       focus:border-amber-500/40 focus:ring-1 focus:ring-amber-500/20 transition-all"
            style={{ background: '#161210' }} />
          {search && (
            <button onClick={() => setSearch('')}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-stone-600 hover:text-stone-400">
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          )}
        </div>
      </div>

      {/* Conteúdo */}
      <div className="flex-1 overflow-auto p-4">
        {error && (
          <div className="flex items-center gap-3 bg-red-500/10 border border-red-500/20
                          text-red-400 text-sm rounded-2xl px-4 py-3 mb-4">
            {error}
            <button onClick={load} className="ml-auto text-xs underline underline-offset-2">Tentar novamente</button>
          </div>
        )}

        {loading ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="rounded-2xl border border-stone-800/50 p-4 animate-pulse"
                   style={{ background: '#161210' }}>
                <div className="flex gap-3 mb-3">
                  <div className="w-10 h-10 bg-stone-800 rounded-xl" />
                  <div className="flex-1 space-y-2">
                    <div className="w-28 h-4 bg-stone-800 rounded" />
                    <div className="w-20 h-3 bg-stone-800 rounded" />
                  </div>
                </div>
                <div className="h-5 bg-stone-800 rounded mt-3" />
              </div>
            ))}
          </div>
        ) : visible.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-20 text-center">
            <div className="w-12 h-12 rounded-2xl bg-stone-800/60 flex items-center justify-center mb-3 text-2xl">
              📋
            </div>
            <p className="text-stone-400 text-sm font-medium">
              {search ? 'Nenhuma comanda encontrada' : 'Nenhuma comanda aberta'}
            </p>
            <p className="text-stone-600 text-xs mt-1">
              {search ? 'Tente outro termo de busca' : 'Abra um pedido em Mesas ou clique em Novo'}
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
            {visible.map(order => (
              <OrderCard
                key={order.id}
                order={order}
                table={tables.find(t => t.id === order.table_id)}
                onClick={() => navigate(`/comanda/${order.id}`)}
              />
            ))}
          </div>
        )}
      </div>

      {showNewOrder && (
        <NewOrderModal
          onClose={() => setShowNewOrder(false)}
          onCreated={order => { setShowNewOrder(false); navigate(`/comanda/${order.id}`) }}
        />
      )}
    </div>
  )
}
