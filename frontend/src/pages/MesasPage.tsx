import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  type Table,
  type TableStatus,
  fetchTables,
  createTable,
  createOrder,
  fetchOpenOrders,
} from '../lib/api'

// ── Config de status ──────────────────────────────────────────────────────────

const STATUS = {
  free:            { label: 'Livre',      color: 'text-green-400',  bg: 'bg-green-500/10',  border: 'border-green-500/25',  accent: '#22c55e' },
  occupied:        { label: 'Ocupada',    color: 'text-amber-400',  bg: 'bg-amber-500/10',  border: 'border-amber-500/25',  accent: '#f59e0b' },
  bill_requested:  { label: 'Conta',      color: 'text-orange-400', bg: 'bg-orange-500/10', border: 'border-orange-500/25', accent: '#f97316' },
  reserved:        { label: 'Reservada',  color: 'text-blue-400',   bg: 'bg-blue-500/10',   border: 'border-blue-500/25',   accent: '#3b82f6' },
  blocked:         { label: 'Bloqueada',  color: 'text-stone-500',  bg: 'bg-stone-800/40',  border: 'border-stone-700/40',  accent: '#57534e' },
} satisfies Record<TableStatus, { label: string; color: string; bg: string; border: string; accent: string }>

const FILTERS: Array<{ value: 'all' | TableStatus; label: string }> = [
  { value: 'all',           label: 'Todas' },
  { value: 'free',          label: 'Livres' },
  { value: 'occupied',      label: 'Ocupadas' },
  { value: 'bill_requested',label: 'Conta' },
  { value: 'reserved',      label: 'Reservadas' },
]

// ── Skeleton ──────────────────────────────────────────────────────────────────

function SkeletonCard() {
  return (
    <div className="rounded-2xl border border-stone-800/50 p-4 animate-pulse"
         style={{ background: '#161210' }}>
      <div className="flex justify-between items-start mb-3">
        <div className="w-9 h-7 bg-stone-800 rounded-lg" />
        <div className="w-14 h-5 bg-stone-800 rounded-full" />
      </div>
      <div className="w-28 h-4 bg-stone-800 rounded mb-2" />
      <div className="w-20 h-3 bg-stone-800 rounded" />
    </div>
  )
}

// ── Card de mesa ──────────────────────────────────────────────────────────────

function TableCard({ table, onClick }: { table: Table; onClick: () => void }) {
  const cfg = STATUS[table.status]
  const isBlocked = table.status === 'blocked'

  return (
    <button
      onClick={isBlocked ? undefined : onClick}
      disabled={isBlocked}
      className={[
        'group w-full text-left rounded-2xl border border-stone-800/50',
        'p-4 transition-all duration-150 relative overflow-hidden',
        isBlocked
          ? 'opacity-40 cursor-not-allowed'
          : 'hover:border-stone-700/70 hover:-translate-y-0.5 hover:shadow-lg hover:shadow-black/40 cursor-pointer active:translate-y-0',
      ].join(' ')}
      style={{ background: '#161210' }}
    >
      {/* Barra de acento lateral */}
      <div
        className="absolute left-0 top-3 bottom-3 w-[3px] rounded-r-full"
        style={{ background: cfg.accent, opacity: 0.7 }}
      />

      {/* Número + status */}
      <div className="flex items-start justify-between gap-2 mb-2.5 pl-3">
        <span className="text-3xl font-black text-stone-100 leading-none">{table.number}</span>
        <span className={[
          'text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full border shrink-0 mt-1',
          cfg.color, cfg.bg, cfg.border,
        ].join(' ')}>
          {cfg.label}
        </span>
      </div>

      {/* Label */}
      <p className="text-stone-300 text-sm font-medium leading-tight pl-3 truncate">{table.label}</p>

      {/* Section + capacidade */}
      <div className="flex items-center gap-1.5 mt-2 pl-3 text-xs text-stone-600">
        {table.section && <span className="truncate max-w-[80px]">{table.section}</span>}
        {table.section && <span>·</span>}
        <span>{table.capacity} lugares</span>
      </div>
    </button>
  )
}

// ── Modal: Nova Mesa ──────────────────────────────────────────────────────────

interface NewTableModalProps {
  onClose: () => void
  onCreated: (t: Table) => void
}

function NewTableModal({ onClose, onCreated }: NewTableModalProps) {
  const [number, setNumber] = useState('')
  const [label, setLabel] = useState('')
  const [capacity, setCapacity] = useState('4')
  const [section, setSection] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      const table = await createTable({
        number: Number(number),
        label: label.trim(),
        capacity: Number(capacity),
        section: section.trim() || null,
      })
      onCreated(table)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro ao criar mesa')
    } finally {
      setLoading(false)
    }
  }

  return (
    <ModalOverlay onClose={onClose}>
      <h2 className="text-stone-100 text-base font-bold mb-5">Nova mesa</h2>

      {error && (
        <p className="text-red-400 text-xs bg-red-500/10 border border-red-500/20
                       rounded-xl px-3 py-2.5 mb-4">{error}</p>
      )}

      <form onSubmit={handleSubmit} className="space-y-3.5">
        <div className="grid grid-cols-2 gap-3">
          <Field label="Número">
            <input type="number" min={1} required value={number}
              onChange={e => setNumber(e.target.value)}
              placeholder="1" className={inputCls} />
          </Field>
          <Field label="Capacidade">
            <input type="number" min={1} max={50} required value={capacity}
              onChange={e => setCapacity(e.target.value)}
              placeholder="4" className={inputCls} />
          </Field>
        </div>

        <Field label="Nome / Label">
          <input type="text" required value={label}
            onChange={e => setLabel(e.target.value)}
            placeholder="ex: Mesa 1, Balcão, VIP" className={inputCls} />
        </Field>

        <Field label="Seção (opcional)">
          <input type="text" value={section}
            onChange={e => setSection(e.target.value)}
            placeholder="ex: Área externa, Salão" className={inputCls} />
        </Field>

        <div className="flex gap-2 pt-1">
          <button type="button" onClick={onClose}
            className="flex-1 py-2.5 rounded-xl text-sm font-semibold
                       text-stone-400 border border-stone-700/60 hover:bg-stone-800/50
                       transition-colors">
            Cancelar
          </button>
          <button type="submit" disabled={loading}
            className="flex-1 py-2.5 rounded-xl text-sm font-semibold
                       bg-amber-500 hover:bg-amber-400 text-stone-900
                       disabled:opacity-40 transition-colors">
            {loading ? 'Criando…' : 'Criar mesa'}
          </button>
        </div>
      </form>
    </ModalOverlay>
  )
}

// ── Modal: Abrir comanda ──────────────────────────────────────────────────────

interface OpenOrderModalProps {
  table: Table
  onClose: () => void
  onOpened: (orderId: string) => void
}

function OpenOrderModal({ table, onClose, onOpened }: OpenOrderModalProps) {
  const [guestCount, setGuestCount] = useState('1')
  const [customerName, setCustomerName] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      const order = await createOrder({
        table_id: table.id,
        guest_count: Number(guestCount),
        customer_name: customerName.trim() || null,
      })
      onOpened(order.id)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro ao abrir comanda')
    } finally {
      setLoading(false)
    }
  }

  return (
    <ModalOverlay onClose={onClose}>
      <div className="flex items-center gap-3 mb-5">
        <div className="w-10 h-10 rounded-xl bg-amber-500/10 border border-amber-500/20
                        flex items-center justify-center">
          <span className="text-lg font-black text-amber-400">{table.number}</span>
        </div>
        <div>
          <h2 className="text-stone-100 text-base font-bold leading-tight">{table.label}</h2>
          <p className="text-stone-500 text-xs mt-0.5">Abrir nova comanda</p>
        </div>
      </div>

      {error && (
        <p className="text-red-400 text-xs bg-red-500/10 border border-red-500/20
                       rounded-xl px-3 py-2.5 mb-4">{error}</p>
      )}

      <form onSubmit={handleSubmit} className="space-y-3.5">
        <Field label="Número de pessoas">
          <input type="number" min={1} max={200} required value={guestCount}
            onChange={e => setGuestCount(e.target.value)}
            className={inputCls} />
        </Field>

        <Field label="Nome do cliente (opcional)">
          <input type="text" value={customerName}
            onChange={e => setCustomerName(e.target.value)}
            placeholder="ex: João Silva" className={inputCls} />
        </Field>

        <div className="flex gap-2 pt-1">
          <button type="button" onClick={onClose}
            className="flex-1 py-2.5 rounded-xl text-sm font-semibold
                       text-stone-400 border border-stone-700/60 hover:bg-stone-800/50
                       transition-colors">
            Cancelar
          </button>
          <button type="submit" disabled={loading}
            className="flex-1 py-2.5 rounded-xl text-sm font-semibold
                       bg-amber-500 hover:bg-amber-400 text-stone-900
                       disabled:opacity-40 transition-colors">
            {loading ? 'Abrindo…' : 'Abrir comanda'}
          </button>
        </div>
      </form>
    </ModalOverlay>
  )
}

// ── Overlay genérico ──────────────────────────────────────────────────────────

function ModalOverlay({ children, onClose }: { children: React.ReactNode; onClose: () => void }) {
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [onClose])

  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-4"
         style={{ background: 'rgba(0,0,0,0.7)', backdropFilter: 'blur(4px)' }}>
      <div
        className="w-full max-w-sm rounded-3xl border border-stone-800/70 p-5"
        style={{ background: '#161210' }}
        onClick={e => e.stopPropagation()}
      >
        {children}
      </div>
    </div>
  )
}

// ── Helpers ───────────────────────────────────────────────────────────────────

const inputCls = `w-full rounded-xl px-3.5 py-2.5 text-sm border border-stone-800/80
  text-stone-100 placeholder-stone-700 focus:outline-none
  focus:border-amber-500/40 focus:ring-1 focus:ring-amber-500/20 transition-all`
  .replace(/\s+/g, ' ')

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="block text-[11px] font-semibold text-stone-500 uppercase tracking-wider mb-1.5">
        {label}
      </label>
      {children}
    </div>
  )
}

// ── Página ────────────────────────────────────────────────────────────────────

type Modal =
  | { type: 'new-table' }
  | { type: 'open-order'; table: Table }

export default function MesasPage() {
  const navigate = useNavigate()
  const [tables, setTables] = useState<Table[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [filter, setFilter] = useState<'all' | TableStatus>('all')
  const [search, setSearch] = useState('')
  const [modal, setModal] = useState<Modal | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      setTables(await fetchTables())
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro ao carregar mesas')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  // Auto-refresh silencioso a cada 30s
  useEffect(() => {
    const id = setInterval(async () => {
      try { setTables(await fetchTables()) } catch {}
    }, 30_000)
    return () => clearInterval(id)
  }, [])

  async function handleTableClick(table: Table) {
    if (table.status === 'free' || table.status === 'reserved') {
      setModal({ type: 'open-order', table })
      return
    }
    // Ocupada / conta → abre direto a comanda dessa mesa em tela cheia
    try {
      const open = await fetchOpenOrders(table.id)
      if (open.length > 0) {
        navigate(`/comanda/${open[0].id}`)
      } else {
        // Sem comanda aberta (estado inconsistente) → permite abrir uma nova
        setModal({ type: 'open-order', table })
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro ao abrir a comanda da mesa')
    }
  }

  const visible = tables.filter(t => {
    if (filter !== 'all' && t.status !== filter) return false
    if (search) {
      const q = search.toLowerCase()
      return (
        t.label.toLowerCase().includes(q) ||
        t.section?.toLowerCase().includes(q) ||
        String(t.number).includes(q)
      )
    }
    return true
  })

  const counts = {
    free: tables.filter(t => t.status === 'free').length,
    occupied: tables.filter(t => t.status === 'occupied' || t.status === 'bill_requested').length,
  }

  return (
    <div className="h-full flex flex-col">

      {/* Cabeçalho */}
      <div className="px-5 pt-5 pb-4 border-b border-stone-800/50"
           style={{ background: '#0f0d0a' }}>
        <div className="flex items-start justify-between gap-4 mb-4">
          <div>
            <h1 className="text-stone-100 text-lg font-bold leading-tight">Mesas</h1>
            {!loading && (
              <p className="text-stone-500 text-xs mt-0.5">
                {counts.free} livres · {counts.occupied} ocupadas · {tables.length} total
              </p>
            )}
          </div>
          <div className="flex items-center gap-2">
            {/* Refresh */}
            <button
              onClick={load}
              disabled={loading}
              className="flex items-center justify-center w-9 h-9 rounded-xl
                         border border-stone-800/60 text-stone-500 hover:text-stone-300
                         hover:border-stone-700/60 disabled:opacity-40 transition-all"
              style={{ background: '#161210' }}
              title="Atualizar"
            >
              <svg className={['w-4 h-4', loading ? 'animate-spin' : ''].join(' ')}
                   fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round"
                      d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0
                         0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
              </svg>
            </button>
            {/* Nova mesa */}
            <button
              onClick={() => setModal({ type: 'new-table' })}
              className="flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-semibold
                         bg-amber-500 hover:bg-amber-400 text-stone-900 transition-colors"
            >
              <span className="text-base leading-none">+</span>
              Nova mesa
            </button>
          </div>
        </div>

        {/* Busca */}
        <div className="relative mb-3">
          <svg className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-stone-600 pointer-events-none"
               fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round"
                  d="M21 21l-4.35-4.35M17 11A6 6 0 105 11a6 6 0 0012 0z" />
          </svg>
          <input
            type="text"
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Buscar por número, nome ou seção…"
            className="w-full pl-9 pr-4 py-2.5 rounded-xl text-sm
                       border border-stone-800/60 text-stone-200 placeholder-stone-600
                       focus:outline-none focus:border-amber-500/40 focus:ring-1 focus:ring-amber-500/20
                       transition-all"
            style={{ background: '#161210' }}
          />
          {search && (
            <button onClick={() => setSearch('')}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-stone-600 hover:text-stone-400">
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          )}
        </div>

        {/* Filtros de status */}
        <div className="flex gap-1.5 overflow-x-auto pb-0.5 scrollbar-none">
          {FILTERS.map(f => (
            <button
              key={f.value}
              onClick={() => setFilter(f.value)}
              className={[
                'shrink-0 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all',
                filter === f.value
                  ? 'bg-amber-500/15 text-amber-400 border border-amber-500/30'
                  : 'text-stone-500 border border-stone-800/60 hover:text-stone-300 hover:border-stone-700/60',
              ].join(' ')}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>

      {/* Conteúdo */}
      <div className="flex-1 overflow-auto p-4">

        {error && (
          <div className="flex items-center gap-3 bg-red-500/10 border border-red-500/20
                          text-red-400 text-sm rounded-2xl px-4 py-3 mb-4">
            <svg className="w-4 h-4 shrink-0" fill="none" viewBox="0 0 24 24"
                 stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round"
                    d="M12 9v4m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0
                       001.71-3L13.71 3.86a2 2 0 00-3.42 0z" />
            </svg>
            {error}
            <button onClick={load} className="ml-auto text-xs underline underline-offset-2">
              Tentar novamente
            </button>
          </div>
        )}

        {loading ? (
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-3">
            {Array.from({ length: 8 }).map((_, i) => <SkeletonCard key={i} />)}
          </div>
        ) : visible.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-20 text-center">
            <div className="w-12 h-12 rounded-2xl bg-stone-800/60 flex items-center justify-center mb-3 text-2xl">
              🪑
            </div>
            <p className="text-stone-400 text-sm font-medium">
              {search || filter !== 'all' ? 'Nenhuma mesa encontrada' : 'Nenhuma mesa cadastrada'}
            </p>
            <p className="text-stone-600 text-xs mt-1">
              {search || filter !== 'all'
                ? 'Tente outro filtro ou busca'
                : 'Clique em "Nova mesa" para começar'}
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-3">
            {visible
              .sort((a, b) => a.number - b.number)
              .map(t => (
                <TableCard key={t.id} table={t} onClick={() => handleTableClick(t)} />
              ))}
          </div>
        )}
      </div>

      {/* Modais */}
      {modal?.type === 'new-table' && (
        <NewTableModal
          onClose={() => setModal(null)}
          onCreated={t => { setTables(prev => [...prev, t].sort((a, b) => a.number - b.number)); setModal(null) }}
        />
      )}

      {modal?.type === 'open-order' && (
        <OpenOrderModal
          table={modal.table}
          onClose={() => setModal(null)}
          onOpened={orderId => { setModal(null); navigate(`/comanda/${orderId}`) }}
        />
      )}
    </div>
  )
}
