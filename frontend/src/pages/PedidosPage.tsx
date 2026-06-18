import { useState, useEffect, useCallback } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  type Order, type OrderItem, type Table, type Category, type MenuItem,
  type Payment, type PaymentMethod,
  fetchOpenOrders, fetchTables, fetchCategories, fetchMenuItems,
  createOrder, addOrderItem, cancelOrderItem, closeOrder, updateTableStatus,
  fetchOrderPayments, registerPayment, finishOrder,
} from '../lib/api'
import { maskCurrency, parseCurrency, toCurrencyInput } from '../lib/format'

// ── Helpers ───────────────────────────────────────────────────────────────────

function timeAgo(iso: string) {
  const diff = Date.now() - new Date(iso).getTime()
  const m = Math.floor(diff / 60000)
  if (m < 1) return 'agora'
  if (m < 60) return `${m}min`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h}h`
  return `${Math.floor(h / 24)}d`
}

function brl(v: string | number) {
  return Number(v).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })
}

const ORDER_STATUS = {
  open:            { label: 'Aberta',  color: 'text-green-400',  bg: 'bg-green-500/10',  border: 'border-green-500/25' },
  bill_requested:  { label: 'Conta',   color: 'text-orange-400', bg: 'bg-orange-500/10', border: 'border-orange-500/25' },
  closed:          { label: 'Fechada', color: 'text-stone-500',  bg: 'bg-stone-800/40',  border: 'border-stone-700/40' },
  finalized:       { label: 'Final.',  color: 'text-stone-500',  bg: 'bg-stone-800/40',  border: 'border-stone-700/40' },
} as Record<string, { label: string; color: string; bg: string; border: string }>

const inputCls = `w-full rounded-xl px-3.5 py-2.5 text-sm border border-stone-800/80
  text-stone-100 placeholder-stone-700 focus:outline-none transition-all
  focus:border-amber-500/40 focus:ring-1 focus:ring-amber-500/20`.replace(/\s+/g, ' ')

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

function ModalOverlay({ children, onClose }: { children: React.ReactNode; onClose: () => void }) {
  useEffect(() => {
    const h = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', h)
    return () => document.removeEventListener('keydown', h)
  }, [onClose])
  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-4"
         style={{ background: 'rgba(0,0,0,0.75)', backdropFilter: 'blur(4px)' }}
         onClick={onClose}>
      <div className="w-full max-w-md rounded-3xl border border-stone-800/70 p-5"
           style={{ background: '#161210' }}
           onClick={e => e.stopPropagation()}>
        {children}
      </div>
    </div>
  )
}

// ── Card de comanda (lista) ───────────────────────────────────────────────────

function OrderCard({
  order, table, selected, onClick,
}: {
  order: Order
  table: Table | undefined
  selected: boolean
  onClick: () => void
}) {
  const cfg = ORDER_STATUS[order.status] ?? ORDER_STATUS.open
  const activeItems = order.items.filter(i => i.status !== 'cancelled').length

  return (
    <button
      onClick={onClick}
      className={[
        'w-full text-left px-4 py-3.5 border-b border-stone-800/40 transition-all duration-100',
        selected ? 'bg-amber-500/8' : 'hover:bg-stone-800/30',
      ].join(' ')}
    >
      <div className="flex items-start justify-between gap-2 mb-1">
        <div className="flex items-center gap-2.5 min-w-0">
          {/* Número da mesa */}
          <span className="text-xl font-black text-stone-100 leading-none shrink-0">
            {table?.number ?? '—'}
          </span>
          <div className="min-w-0">
            <p className="text-stone-200 text-sm font-medium leading-tight truncate">
              {order.customer_name ?? table?.label ?? 'Comanda'}
            </p>
            <p className="text-stone-600 text-xs mt-0.5">
              {order.guest_count} {order.guest_count === 1 ? 'pessoa' : 'pessoas'} · {timeAgo(order.created_at)}
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

      <div className="flex items-center justify-between mt-2 pl-9">
        <span className="text-stone-600 text-xs">{activeItems} {activeItems === 1 ? 'item' : 'itens'}</span>
        <span className="text-amber-400 text-sm font-bold">{brl(order.total)}</span>
      </div>

      {/* Indicador de selecionado */}
      {selected && (
        <div className="absolute left-0 top-0 bottom-0 w-0.5 bg-amber-500 rounded-r-full" />
      )}
    </button>
  )
}

// ── Linha de item da comanda ──────────────────────────────────────────────────

function OrderItemRow({
  item, canCancel, onCancelled,
}: {
  item: OrderItem
  canCancel: boolean
  onCancelled: (updated: Order) => void
}) {
  const [cancelling, setCancelling] = useState(false)
  const [reason, setReason] = useState('')
  const [loading, setLoading] = useState(false)

  const isCancelled = item.status === 'cancelled'

  async function confirmCancel() {
    setLoading(true)
    try {
      const updated = await cancelOrderItem(
        item.order_id,
        item.id,
        reason.trim() || undefined,
      )
      onCancelled(updated)
    } finally {
      setLoading(false)
      setCancelling(false)
      setReason('')
    }
  }

  return (
    <div className={['px-4 py-3 border-b border-stone-800/30 transition-opacity', isCancelled ? 'opacity-40' : ''].join(' ')}>
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-baseline gap-2">
            <span className="text-stone-500 text-xs font-bold">{item.quantity}×</span>
            <span className={['text-stone-200 text-sm leading-tight', isCancelled ? 'line-through' : ''].join(' ')}>
              {item.item_name}
            </span>
          </div>
          {item.notes && (
            <p className="text-stone-600 text-xs mt-0.5 pl-5 italic">{item.notes}</p>
          )}
          {isCancelled && item.cancelled_reason && (
            <p className="text-stone-700 text-xs mt-0.5 pl-5">Motivo: {item.cancelled_reason}</p>
          )}
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <span className={['text-sm font-semibold', isCancelled ? 'text-stone-600' : 'text-stone-300'].join(' ')}>
            {brl(item.subtotal)}
          </span>
          {canCancel && !isCancelled && item.status !== 'served' && (
            <button
              onClick={() => setCancelling(v => !v)}
              className="w-6 h-6 flex items-center justify-center rounded-lg
                         text-stone-700 hover:text-red-400 hover:bg-red-500/10 transition-all"
            >
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          )}
        </div>
      </div>

      {/* Inline cancel form */}
      {cancelling && (
        <div className="mt-2.5 pl-5 space-y-2">
          <input
            type="text" value={reason} onChange={e => setReason(e.target.value)}
            placeholder="Motivo (opcional)"
            className="w-full rounded-lg px-3 py-1.5 text-xs border border-stone-700/60
                       text-stone-300 placeholder-stone-700 bg-stone-900/60
                       focus:outline-none focus:border-red-500/40"
          />
          <div className="flex gap-2">
            <button onClick={() => { setCancelling(false); setReason('') }}
              className="flex-1 py-1.5 rounded-lg text-xs text-stone-500 border border-stone-700/50
                         hover:bg-stone-800/50 transition-colors">
              Voltar
            </button>
            <button onClick={confirmCancel} disabled={loading}
              className="flex-1 py-1.5 rounded-lg text-xs font-semibold
                         bg-red-500/15 text-red-400 border border-red-500/20
                         hover:bg-red-500/25 disabled:opacity-40 transition-colors">
              {loading ? 'Cancelando…' : 'Cancelar item'}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

// ── Modal: Adicionar item ─────────────────────────────────────────────────────

function AddItemModal({
  order, onClose, onAdded,
}: {
  order: Order
  onClose: () => void
  onAdded: (updated: Order) => void
}) {
  const [categories, setCategories] = useState<Category[]>([])
  const [items, setItems] = useState<MenuItem[]>([])
  const [loadingMenu, setLoadingMenu] = useState(true)
  const [selectedCat, setSelectedCat] = useState<string>('all')
  const [search, setSearch] = useState('')
  const [tab, setTab] = useState<'menu' | 'half' | 'manual'>('menu')

  // Estado do item selecionado do cardápio
  const [picking, setPicking] = useState<MenuItem | null>(null)
  const [qty, setQty] = useState('1')
  const [notes, setNotes] = useState('')
  const [adding, setAdding] = useState(false)
  const [addError, setAddError] = useState<string | null>(null)

  // Estado do item manual
  const [manName, setManName] = useState('')
  const [manPrice, setManPrice] = useState('')
  const [manQty, setManQty] = useState('1')
  const [manNotes, setManNotes] = useState('')

  // Estado da pizza meia a meia
  const [halfCat, setHalfCat] = useState<string>('all')
  const [half1, setHalf1] = useState('')
  const [half2, setHalf2] = useState('')
  const [halfQty, setHalfQty] = useState('1')
  const [halfNotes, setHalfNotes] = useState('')

  useEffect(() => {
    Promise.all([fetchCategories(), fetchMenuItems()])
      .then(([cats, its]) => {
        setCategories(cats.filter(c => c.is_active))
        setItems(its.filter(i => i.is_active && i.is_available))
      })
      .finally(() => setLoadingMenu(false))
  }, [])

  const visible = items.filter(i => {
    if (selectedCat !== 'all' && i.category_id !== selectedCat) return false
    if (search) return i.name.toLowerCase().includes(search.toLowerCase())
    return true
  })

  async function addFromMenu() {
    if (!picking) return
    setAddError(null)
    setAdding(true)
    try {
      const updated = await addOrderItem(order.id, {
        menu_item_id: picking.id,
        quantity: Number(qty),
        notes: notes.trim() || null,
      })
      onAdded(updated)
      setPicking(null); setQty('1'); setNotes('')
    } catch (err) {
      setAddError(err instanceof Error ? err.message : 'Erro ao adicionar')
    } finally {
      setAdding(false)
    }
  }

  async function addManual(e: React.FormEvent) {
    e.preventDefault()
    setAddError(null)
    setAdding(true)
    try {
      const updated = await addOrderItem(order.id, {
        item_name: manName.trim(),
        unit_price: parseCurrency(manPrice),
        quantity: Number(manQty),
        notes: manNotes.trim() || null,
      })
      onAdded(updated)
      setManName(''); setManPrice(''); setManQty('1'); setManNotes('')
    } catch (err) {
      setAddError(err instanceof Error ? err.message : 'Erro ao adicionar')
    } finally {
      setAdding(false)
    }
  }

  // Pizza meia a meia: nome composto + preço da metade mais cara
  const halfItem1 = items.find(i => i.id === half1)
  const halfItem2 = items.find(i => i.id === half2)
  const halfPrice =
    halfItem1 && halfItem2
      ? Math.max(Number(halfItem1.price), Number(halfItem2.price))
      : 0

  async function addHalf(e: React.FormEvent) {
    e.preventDefault()
    if (!halfItem1 || !halfItem2) { setAddError('Escolha os dois sabores'); return }
    setAddError(null)
    setAdding(true)
    try {
      const updated = await addOrderItem(order.id, {
        item_name: `½ ${halfItem1.name} / ½ ${halfItem2.name}`,
        unit_price: halfPrice,
        quantity: Number(halfQty),
        notes: halfNotes.trim() || null,
      })
      onAdded(updated)
      setHalf1(''); setHalf2(''); setHalfQty('1'); setHalfNotes('')
    } catch (err) {
      setAddError(err instanceof Error ? err.message : 'Erro ao adicionar')
    } finally {
      setAdding(false)
    }
  }

  const halfOptions = items.filter(i => halfCat === 'all' || i.category_id === halfCat)

  return (
    <ModalOverlay onClose={onClose}>
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-stone-100 text-base font-bold">Adicionar item</h2>
        <button onClick={onClose} className="text-stone-600 hover:text-stone-400 transition-colors">
          <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      {/* Abas */}
      <div className="flex gap-1 p-1 rounded-xl mb-4" style={{ background: '#0d0b08' }}>
        {(['menu', 'half', 'manual'] as const).map(t => (
          <button key={t} onClick={() => setTab(t)}
            className={[
              'flex-1 py-2 rounded-lg text-xs font-semibold transition-all',
              tab === t ? 'bg-amber-500/15 text-amber-400' : 'text-stone-500 hover:text-stone-300',
            ].join(' ')}>
            {t === 'menu' ? 'Do cardápio' : t === 'half' ? '½ Meia' : 'Manual'}
          </button>
        ))}
      </div>

      {addError && (
        <p className="text-red-400 text-xs bg-red-500/10 border border-red-500/20
                       rounded-xl px-3 py-2 mb-3">{addError}</p>
      )}

      {tab === 'menu' ? (
        <div className="space-y-3">
          {loadingMenu ? (
            <div className="text-center py-8 text-stone-600 text-sm">Carregando cardápio…</div>
          ) : picking ? (
            /* Confirmação do item selecionado */
            <div className="space-y-3">
              <div className="flex items-center gap-3 p-3 rounded-xl" style={{ background: '#0d0b08' }}>
                <div className="flex-1 min-w-0">
                  <p className="text-stone-200 text-sm font-semibold truncate">{picking.name}</p>
                  <p className="text-amber-400 text-xs mt-0.5">{brl(picking.price)}</p>
                </div>
                <button onClick={() => setPicking(null)} className="text-stone-600 hover:text-stone-400">
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <Field label="Quantidade">
                  <input type="number" min={1} max={99} value={qty}
                    onChange={e => setQty(e.target.value)}
                    className={inputCls} style={{ background: '#0d0b08' }} />
                </Field>
                <div />
              </div>
              <Field label="Observações (opcional)">
                <input type="text" value={notes} onChange={e => setNotes(e.target.value)}
                  placeholder="ex: sem cebola, ao ponto"
                  className={inputCls} style={{ background: '#0d0b08' }} />
              </Field>
              <div className="flex gap-2">
                <button onClick={() => setPicking(null)}
                  className="flex-1 py-2.5 rounded-xl text-sm font-semibold
                             text-stone-400 border border-stone-700/60 hover:bg-stone-800/50 transition-colors">
                  Voltar
                </button>
                <button onClick={addFromMenu} disabled={adding}
                  className="flex-1 py-2.5 rounded-xl text-sm font-semibold
                             bg-amber-500 hover:bg-amber-400 text-stone-900
                             disabled:opacity-40 transition-colors">
                  {adding ? 'Adicionando…' : 'Adicionar'}
                </button>
              </div>
            </div>
          ) : items.length === 0 ? (
            <div className="text-center py-8">
              <p className="text-stone-500 text-sm">Cardápio vazio</p>
              <p className="text-stone-700 text-xs mt-1">Cadastre itens na aba Cardápio</p>
            </div>
          ) : (
            <>
              {/* Busca */}
              <div className="relative">
                <svg className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-stone-600 pointer-events-none"
                     fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-4.35-4.35M17 11A6 6 0 105 11a6 6 0 0012 0z" />
                </svg>
                <input type="text" value={search} onChange={e => setSearch(e.target.value)}
                  placeholder="Buscar item…"
                  className="w-full pl-8 pr-3 py-2 rounded-xl text-sm border border-stone-800/60
                             text-stone-200 placeholder-stone-700 focus:outline-none
                             focus:border-amber-500/40 transition-all"
                  style={{ background: '#0d0b08' }} />
              </div>

              {/* Categorias */}
              {categories.length > 0 && (
                <div className="flex gap-1.5 overflow-x-auto pb-0.5 scrollbar-none">
                  <button onClick={() => setSelectedCat('all')}
                    className={['shrink-0 px-3 py-1 rounded-lg text-xs font-semibold transition-all',
                      selectedCat === 'all' ? 'bg-amber-500/15 text-amber-400 border border-amber-500/30' : 'text-stone-500 border border-stone-800/60 hover:text-stone-300'].join(' ')}>
                    Todas
                  </button>
                  {categories.map(c => (
                    <button key={c.id} onClick={() => setSelectedCat(c.id)}
                      className={['shrink-0 px-3 py-1 rounded-lg text-xs font-semibold transition-all',
                        selectedCat === c.id ? 'bg-amber-500/15 text-amber-400 border border-amber-500/30' : 'text-stone-500 border border-stone-800/60 hover:text-stone-300'].join(' ')}>
                      {c.name}
                    </button>
                  ))}
                </div>
              )}

              {/* Lista de itens */}
              <div className="max-h-52 overflow-y-auto space-y-1 -mx-1 px-1">
                {visible.length === 0 ? (
                  <p className="text-stone-600 text-xs text-center py-4">Nenhum item encontrado</p>
                ) : visible.map(item => (
                  <button key={item.id} onClick={() => { setPicking(item); setQty('1'); setNotes('') }}
                    className="w-full flex items-center justify-between gap-3 px-3 py-2.5 rounded-xl
                               text-left hover:bg-stone-800/50 transition-colors group">
                    <div className="min-w-0">
                      <p className="text-stone-200 text-sm font-medium truncate group-hover:text-stone-100">{item.name}</p>
                      {item.description && (
                        <p className="text-stone-600 text-xs truncate">{item.description}</p>
                      )}
                    </div>
                    <span className="text-amber-400 text-sm font-semibold shrink-0">{brl(item.price)}</span>
                  </button>
                ))}
              </div>
            </>
          )}
        </div>
      ) : tab === 'half' ? (
        /* Tab meia a meia */
        loadingMenu ? (
          <div className="text-center py-8 text-stone-600 text-sm">Carregando cardápio…</div>
        ) : items.length === 0 ? (
          <div className="text-center py-8">
            <p className="text-stone-500 text-sm">Cardápio vazio</p>
            <p className="text-stone-700 text-xs mt-1">Cadastre as pizzas na aba Cardápio</p>
          </div>
        ) : (
          <form onSubmit={addHalf} className="space-y-3">
            {categories.length > 0 && (
              <Field label="Categoria">
                <select value={halfCat} onChange={e => { setHalfCat(e.target.value); setHalf1(''); setHalf2('') }}
                  className={inputCls + ' appearance-none'} style={{ background: '#0d0b08' }}>
                  <option value="all">Todas as categorias</option>
                  {categories.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
                </select>
              </Field>
            )}
            <Field label="Primeira metade (½)">
              <select value={half1} onChange={e => setHalf1(e.target.value)}
                className={inputCls + ' appearance-none'} style={{ background: '#0d0b08' }}>
                <option value="">Escolha o sabor…</option>
                {halfOptions.map(i => (
                  <option key={i.id} value={i.id}>{i.name} — {brl(i.price)}</option>
                ))}
              </select>
            </Field>
            <Field label="Segunda metade (½)">
              <select value={half2} onChange={e => setHalf2(e.target.value)}
                className={inputCls + ' appearance-none'} style={{ background: '#0d0b08' }}>
                <option value="">Escolha o sabor…</option>
                {halfOptions.map(i => (
                  <option key={i.id} value={i.id}>{i.name} — {brl(i.price)}</option>
                ))}
              </select>
            </Field>

            {/* Preço calculado = metade mais cara */}
            {halfItem1 && halfItem2 && (
              <div className="flex items-center justify-between rounded-xl px-3.5 py-2.5"
                   style={{ background: '#0d0b08' }}>
                <span className="text-stone-500 text-xs">Preço (metade mais cara)</span>
                <span className="text-amber-400 text-sm font-bold">{brl(halfPrice)}</span>
              </div>
            )}

            <Field label="Quantidade">
              <input type="number" min={1} max={99} value={halfQty}
                onChange={e => setHalfQty(e.target.value)}
                className={inputCls} style={{ background: '#0d0b08' }} />
            </Field>
            <Field label="Observações (opcional)">
              <input type="text" value={halfNotes} onChange={e => setHalfNotes(e.target.value)}
                placeholder="ex: borda recheada, sem cebola"
                className={inputCls} style={{ background: '#0d0b08' }} />
            </Field>
            <button type="submit" disabled={adding || !halfItem1 || !halfItem2}
              className="w-full py-2.5 rounded-xl text-sm font-semibold
                         bg-amber-500 hover:bg-amber-400 text-stone-900
                         disabled:opacity-40 transition-colors mt-1">
              {adding ? 'Adicionando…' : 'Adicionar meia a meia'}
            </button>
          </form>
        )
      ) : (
        /* Tab manual */
        <form onSubmit={addManual} className="space-y-3">
          <Field label="Nome do item">
            <input type="text" required value={manName} onChange={e => setManName(e.target.value)}
              placeholder="ex: Cerveja especial" className={inputCls} style={{ background: '#0d0b08' }} />
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Preço (R$)">
              <input type="text" inputMode="numeric" required value={manPrice}
                onChange={e => setManPrice(maskCurrency(e.target.value))}
                placeholder="0,00" className={inputCls} style={{ background: '#0d0b08' }} />
            </Field>
            <Field label="Quantidade">
              <input type="number" min={1} max={99} required value={manQty}
                onChange={e => setManQty(e.target.value)}
                className={inputCls} style={{ background: '#0d0b08' }} />
            </Field>
          </div>
          <Field label="Observações (opcional)">
            <input type="text" value={manNotes} onChange={e => setManNotes(e.target.value)}
              placeholder="ex: sem gelo" className={inputCls} style={{ background: '#0d0b08' }} />
          </Field>
          <button type="submit" disabled={adding}
            className="w-full py-2.5 rounded-xl text-sm font-semibold
                       bg-amber-500 hover:bg-amber-400 text-stone-900
                       disabled:opacity-40 transition-colors mt-1">
            {adding ? 'Adicionando…' : 'Adicionar item'}
          </button>
        </form>
      )}
    </ModalOverlay>
  )
}

// ── Modal: Novo pedido ────────────────────────────────────────────────────────

function NewOrderModal({
  onClose, onCreated,
}: {
  onClose: () => void
  onCreated: (o: Order) => void
}) {
  const [tables, setTables] = useState<Table[]>([])
  const [loading, setLoading] = useState(true)
  const [tableId, setTableId] = useState('')
  const [guestCount, setGuestCount] = useState('1')
  const [customerName, setCustomerName] = useState('')
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchTables()
      .then(ts => {
        const free = ts.filter(t => t.status === 'free' || t.status === 'reserved')
        setTables(free)
        if (free.length > 0) setTableId(free[0].id)
      })
      .finally(() => setLoading(false))
  }, [])

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setCreating(true)
    try {
      const order = await createOrder({
        table_id: tableId,
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
      <h2 className="text-stone-100 text-base font-bold mb-5">Novo pedido</h2>

      {error && (
        <p className="text-red-400 text-xs bg-red-500/10 border border-red-500/20
                       rounded-xl px-3 py-2.5 mb-4">{error}</p>
      )}

      {loading ? (
        <div className="text-center py-6 text-stone-600 text-sm">Carregando mesas…</div>
      ) : tables.length === 0 ? (
        <div className="text-center py-6">
          <p className="text-stone-500 text-sm">Nenhuma mesa disponível</p>
          <p className="text-stone-700 text-xs mt-1">Todas as mesas estão ocupadas</p>
        </div>
      ) : (
        <form onSubmit={handleSubmit} className="space-y-3.5">
          <Field label="Mesa">
            <select value={tableId} onChange={e => setTableId(e.target.value)}
              className={inputCls + ' appearance-none'} style={{ background: '#0d0b08' }}>
              {tables.map(t => (
                <option key={t.id} value={t.id}>
                  Mesa {t.number} — {t.label}{t.section ? ` (${t.section})` : ''}
                </option>
              ))}
            </select>
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Pessoas">
              <input type="number" min={1} max={200} required value={guestCount}
                onChange={e => setGuestCount(e.target.value)}
                className={inputCls} style={{ background: '#0d0b08' }} />
            </Field>
            <div />
          </div>
          <Field label="Cliente (opcional)">
            <input type="text" value={customerName} onChange={e => setCustomerName(e.target.value)}
              placeholder="ex: João Silva"
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

// ── Modal: Receber pagamento ──────────────────────────────────────────────────

const PAYMENT_METHODS: { value: PaymentMethod; label: string; icon: string }[] = [
  { value: 'cash',        label: 'Dinheiro', icon: '💵' },
  { value: 'credit_card', label: 'Crédito',  icon: '💳' },
  { value: 'debit_card',  label: 'Débito',   icon: '💳' },
  { value: 'pix',         label: 'Pix',      icon: '⚡' },
  { value: 'voucher',     label: 'Voucher',  icon: '🎟️' },
]

const METHOD_LABEL: Record<string, string> = Object.fromEntries(
  PAYMENT_METHODS.map(m => [m.value, m.label]),
)

function PaymentModal({
  order, onClose, onFinished,
}: {
  order: Order
  onClose: () => void
  onFinished: (orderId: string) => void
}) {
  const [payments, setPayments] = useState<Payment[]>([])
  const [loading, setLoading] = useState(true)
  const [method, setMethod] = useState<PaymentMethod>('cash')
  const [amount, setAmount] = useState('')
  const [tendered, setTendered] = useState('')
  const [reference, setReference] = useState('')
  const [saving, setSaving] = useState(false)
  const [finishing, setFinishing] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const total = Number(order.total)
  const paid = payments
    .filter(p => p.status === 'confirmed')
    .reduce((sum, p) => sum + Number(p.amount), 0)
  const remaining = Math.max(0, Math.round((total - paid) * 100) / 100)
  const fullyPaid = remaining <= 0

  // Troco previsto para dinheiro
  const tenderedNum = parseCurrency(tendered)
  const amountNum = parseCurrency(amount)
  const change =
    method === 'cash' && !isNaN(tenderedNum) && !isNaN(amountNum) && tenderedNum > amountNum
      ? tenderedNum - amountNum
      : 0

  const refreshPayments = useCallback(async () => {
    const ps = await fetchOrderPayments(order.id)
    setPayments(ps)
    return ps
  }, [order.id])

  useEffect(() => {
    refreshPayments().finally(() => setLoading(false))
  }, [refreshPayments])

  // Ao mudar o saldo devedor, pré-preenche o valor com o restante
  useEffect(() => {
    if (!loading) setAmount(remaining > 0 ? toCurrencyInput(remaining) : '')
  }, [remaining, loading])

  async function handleAddPayment(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    const value = parseCurrency(amount)
    if (isNaN(value) || value <= 0) { setError('Informe um valor válido'); return }

    setSaving(true)
    try {
      await registerPayment({
        order_id: order.id,
        method,
        amount: value.toFixed(2),
        amount_tendered:
          method === 'cash' && !isNaN(tenderedNum) ? tenderedNum.toFixed(2) : null,
        reference: reference.trim() || null,
      })
      await refreshPayments()
      setTendered('')
      setReference('')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro ao registrar pagamento')
    } finally {
      setSaving(false)
    }
  }

  async function handleFinish() {
    setError(null)
    setFinishing(true)
    try {
      await finishOrder(order.id, order.version)
      onFinished(order.id)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro ao finalizar comanda')
    } finally {
      setFinishing(false)
    }
  }

  return (
    <ModalOverlay onClose={onClose}>
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-stone-100 text-base font-bold">Receber pagamento</h2>
        <button onClick={onClose} className="text-stone-600 hover:text-stone-400 transition-colors">
          <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      {/* Resumo financeiro */}
      <div className="rounded-2xl p-4 mb-4 space-y-1.5" style={{ background: '#0d0b08' }}>
        <div className="flex justify-between text-sm">
          <span className="text-stone-500">Total da conta</span>
          <span className="text-stone-200 font-semibold">{brl(total)}</span>
        </div>
        <div className="flex justify-between text-sm">
          <span className="text-stone-500">Pago</span>
          <span className="text-green-400 font-semibold">{brl(paid)}</span>
        </div>
        <div className="flex justify-between pt-1.5 border-t border-stone-800/60">
          <span className="text-stone-300 text-sm font-bold">{fullyPaid ? 'Quitada' : 'Falta'}</span>
          <span className={['text-base font-black', fullyPaid ? 'text-green-400' : 'text-amber-400'].join(' ')}>
            {brl(remaining)}
          </span>
        </div>
      </div>

      {error && (
        <p className="text-red-400 text-xs bg-red-500/10 border border-red-500/20
                       rounded-xl px-3 py-2 mb-3">{error}</p>
      )}

      {/* Pagamentos já registrados */}
      {payments.length > 0 && (
        <div className="space-y-1 mb-4">
          {payments.map(p => (
            <div key={p.id} className="flex items-center justify-between text-xs px-3 py-2 rounded-lg"
                 style={{ background: '#0d0b08' }}>
              <span className="text-stone-400">{METHOD_LABEL[p.method] ?? p.method}</span>
              <div className="flex items-center gap-2">
                {p.change_given && Number(p.change_given) > 0 && (
                  <span className="text-stone-600">troco {brl(p.change_given)}</span>
                )}
                <span className="text-stone-300 font-semibold">{brl(p.amount)}</span>
              </div>
            </div>
          ))}
        </div>
      )}

      {loading ? (
        <div className="text-center py-6 text-stone-600 text-sm">Carregando pagamentos…</div>
      ) : !fullyPaid ? (
        <form onSubmit={handleAddPayment} className="space-y-3">
          {/* Forma de pagamento */}
          <div className="grid grid-cols-5 gap-1.5">
            {PAYMENT_METHODS.map(m => (
              <button key={m.value} type="button" onClick={() => setMethod(m.value)}
                className={[
                  'flex flex-col items-center gap-1 py-2 rounded-xl text-[10px] font-semibold transition-all border',
                  method === m.value
                    ? 'bg-amber-500/15 text-amber-400 border-amber-500/30'
                    : 'text-stone-500 border-stone-800/60 hover:text-stone-300',
                ].join(' ')}>
                <span className="text-base leading-none">{m.icon}</span>
                {m.label}
              </button>
            ))}
          </div>

          <div className={method === 'cash' ? 'grid grid-cols-2 gap-3' : ''}>
            <Field label="Valor (R$)">
              <input type="text" inputMode="numeric" value={amount}
                onChange={e => setAmount(maskCurrency(e.target.value))}
                placeholder="0,00" className={inputCls} style={{ background: '#0d0b08' }} />
            </Field>
            {method === 'cash' && (
              <Field label="Recebido (R$)">
                <input type="text" inputMode="numeric" value={tendered}
                  onChange={e => setTendered(maskCurrency(e.target.value))}
                  placeholder="0,00" className={inputCls} style={{ background: '#0d0b08' }} />
              </Field>
            )}
          </div>

          {method === 'cash' && change > 0 && (
            <div className="flex justify-between text-xs px-1">
              <span className="text-stone-500">Troco</span>
              <span className="text-amber-400 font-bold">{brl(change)}</span>
            </div>
          )}

          {method !== 'cash' && (
            <Field label="Referência (opcional)">
              <input type="text" value={reference} onChange={e => setReference(e.target.value)}
                placeholder="NSU, txid do Pix…" className={inputCls} style={{ background: '#0d0b08' }} />
            </Field>
          )}

          <button type="submit" disabled={saving}
            className="w-full py-2.5 rounded-xl text-sm font-semibold
                       bg-amber-500 hover:bg-amber-400 text-stone-900
                       disabled:opacity-40 transition-colors">
            {saving ? 'Registrando…' : 'Registrar pagamento'}
          </button>
        </form>
      ) : (
        <button onClick={handleFinish} disabled={finishing}
          className="w-full py-3 rounded-xl text-sm font-bold
                     bg-green-500 hover:bg-green-400 text-stone-900
                     disabled:opacity-40 transition-colors">
          {finishing ? 'Finalizando…' : 'Finalizar comanda e liberar mesa'}
        </button>
      )}
    </ModalOverlay>
  )
}

// ── Detalhe da comanda ────────────────────────────────────────────────────────

function OrderDetail({
  order, table, onUpdated, onClosed, onBack,
}: {
  order: Order
  table: Table | undefined
  onUpdated: (o: Order) => void
  onClosed: (orderId: string) => void
  onBack?: () => void
}) {
  const [showAddItem, setShowAddItem] = useState(false)
  const [showPayment, setShowPayment] = useState(false)
  const [closing, setClosing] = useState(false)
  const [requestingBill, setRequestingBill] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)

  const cfg = ORDER_STATUS[order.status] ?? ORDER_STATUS.open
  const canEdit = order.status === 'open' || order.status === 'bill_requested'
  const canAddItem = order.status === 'open'
  const canRequestBill = order.status === 'open' && table
  const canClose = order.status === 'open' || order.status === 'bill_requested'

  const activeItems = order.items.filter(i => i.status !== 'cancelled')
  const cancelledItems = order.items.filter(i => i.status === 'cancelled')

  async function handleRequestBill() {
    if (!table) return
    setActionError(null)
    setRequestingBill(true)
    try {
      await updateTableStatus(table.id, 'bill_requested', table.version)
      // Reload the order to reflect new state
      onUpdated({ ...order, status: 'bill_requested' })
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Erro')
    } finally {
      setRequestingBill(false)
    }
  }

  async function handleClose() {
    setActionError(null)
    setClosing(true)
    try {
      await closeOrder(order.id, order.version)
      onClosed(order.id)
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Erro ao fechar comanda')
    } finally {
      setClosing(false)
    }
  }

  return (
    <div className="flex flex-col h-full">

      {/* Header do detalhe */}
      <div className="px-5 py-4 border-b border-stone-800/50 shrink-0"
           style={{ background: '#0f0d0a' }}>
        <div className="flex items-start gap-3">
          {/* Botão voltar (mobile) */}
          {onBack && (
            <button onClick={onBack} className="mt-0.5 text-stone-500 hover:text-stone-300 transition-colors mr-1">
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
              </svg>
            </button>
          )}

          <div className="w-10 h-10 rounded-xl bg-stone-800 border border-stone-700/50
                          flex items-center justify-center shrink-0">
            <span className="text-lg font-black text-stone-100">{table?.number ?? '?'}</span>
          </div>

          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <h2 className="text-stone-100 font-bold text-base leading-tight">
                {order.customer_name ?? table?.label ?? 'Comanda'}
              </h2>
              <span className={['text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full border', cfg.color, cfg.bg, cfg.border].join(' ')}>
                {cfg.label}
              </span>
            </div>
            <p className="text-stone-500 text-xs mt-0.5">
              {order.guest_count} {order.guest_count === 1 ? 'pessoa' : 'pessoas'} · aberta há {timeAgo(order.created_at)}
            </p>
          </div>
        </div>

        {actionError && (
          <p className="text-red-400 text-xs bg-red-500/10 border border-red-500/20
                         rounded-xl px-3 py-2 mt-3">{actionError}</p>
        )}
      </div>

      {/* Itens */}
      <div className="flex-1 overflow-y-auto">
        {order.items.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-center px-4">
            <div className="w-10 h-10 rounded-2xl bg-stone-800/60 flex items-center justify-center mb-3 text-xl">
              📋
            </div>
            <p className="text-stone-500 text-sm">Comanda vazia</p>
            <p className="text-stone-700 text-xs mt-1">Adicione itens do cardápio</p>
          </div>
        ) : (
          <>
            {/* Itens ativos */}
            {activeItems.map(item => (
              <OrderItemRow
                key={item.id}
                item={item}
                canCancel={canEdit}
                onCancelled={onUpdated}
              />
            ))}

            {/* Itens cancelados */}
            {cancelledItems.length > 0 && (
              <>
                <div className="px-4 py-2 bg-stone-900/30">
                  <p className="text-stone-600 text-[10px] font-bold uppercase tracking-wider">
                    Cancelados ({cancelledItems.length})
                  </p>
                </div>
                {cancelledItems.map(item => (
                  <OrderItemRow key={item.id} item={item} canCancel={false} onCancelled={onUpdated} />
                ))}
              </>
            )}
          </>
        )}
      </div>

      {/* Totais + ações */}
      <div className="border-t border-stone-800/50 shrink-0 p-4 space-y-3"
           style={{ background: '#0f0d0a' }}>

        {/* Totais */}
        <div className="space-y-1">
          {Number(order.service_fee) > 0 && (
            <div className="flex justify-between text-xs text-stone-500">
              <span>Subtotal</span><span>{brl(order.subtotal)}</span>
            </div>
          )}
          {Number(order.service_fee) > 0 && (
            <div className="flex justify-between text-xs text-stone-500">
              <span>Taxa de serviço</span><span>{brl(order.service_fee)}</span>
            </div>
          )}
          {Number(order.discount) > 0 && (
            <div className="flex justify-between text-xs text-green-400">
              <span>Desconto</span><span>−{brl(order.discount)}</span>
            </div>
          )}
          <div className="flex justify-between pt-1 border-t border-stone-800/50">
            <span className="text-stone-200 text-sm font-bold">Total</span>
            <span className="text-amber-400 text-base font-black">{brl(order.total)}</span>
          </div>
        </div>

        {/* Botões de ação */}
        {canClose && (
          <div className="space-y-2">
            <div className="flex gap-2">
              {canAddItem && (
                <button onClick={() => setShowAddItem(true)}
                  className="flex items-center gap-1.5 px-3 py-2.5 rounded-xl text-sm font-semibold
                             text-stone-300 border border-stone-700/60 hover:bg-stone-800/50 transition-colors">
                  <span className="text-base leading-none">+</span>
                  Item
                </button>
              )}
              {canRequestBill && (
                <button onClick={handleRequestBill} disabled={requestingBill}
                  className="flex-1 py-2.5 rounded-xl text-sm font-semibold
                             text-orange-400 border border-orange-500/30 bg-orange-500/8
                             hover:bg-orange-500/15 disabled:opacity-40 transition-colors">
                  {requestingBill ? '…' : 'Solicitar conta'}
                </button>
              )}
              <button onClick={() => setShowPayment(true)}
                className="flex-1 py-2.5 rounded-xl text-sm font-semibold
                           bg-amber-500 hover:bg-amber-400 text-stone-900 transition-colors">
                Receber {brl(order.total)}
              </button>
            </div>
            {/* Override do gerente: fechar sem checar pagamento */}
            <button onClick={handleClose} disabled={closing}
              className="w-full text-center text-[11px] text-stone-600 hover:text-stone-400
                         disabled:opacity-40 transition-colors py-1">
              {closing ? 'Fechando…' : 'Fechar sem pagamento (override)'}
            </button>
          </div>
        )}
      </div>

      {showAddItem && (
        <AddItemModal
          order={order}
          onClose={() => setShowAddItem(false)}
          onAdded={updated => { onUpdated(updated); setShowAddItem(false) }}
        />
      )}

      {showPayment && (
        <PaymentModal
          order={order}
          onClose={() => setShowPayment(false)}
          onFinished={id => { setShowPayment(false); onClosed(id) }}
        />
      )}
    </div>
  )
}

// ── Placeholder (nenhuma comanda selecionada) ─────────────────────────────────

function EmptyDetail() {
  return (
    <div className="flex flex-col items-center justify-center h-full text-center p-8">
      <div className="w-14 h-14 rounded-2xl bg-stone-800/40 flex items-center justify-center mb-4 text-3xl">
        📋
      </div>
      <p className="text-stone-500 text-sm font-medium">Selecione uma comanda</p>
      <p className="text-stone-700 text-xs mt-1">Clique em uma comanda para ver os detalhes</p>
    </div>
  )
}

// ── Página principal ──────────────────────────────────────────────────────────

export default function PedidosPage() {
  const [orders, setOrders] = useState<Order[]>([])
  const [tables, setTables] = useState<Table[]>([])
  const [selected, setSelected] = useState<Order | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [showNewOrder, setShowNewOrder] = useState(false)
  const [mobileDetail, setMobileDetail] = useState(false)
  const [searchParams, setSearchParams] = useSearchParams()
  const tableParam = searchParams.get('table')

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [os, ts] = await Promise.all([fetchOpenOrders(), fetchTables()])
      setOrders(os)
      setTables(ts)
      // Atualiza a comanda selecionada se ainda existe
      if (selected) {
        const fresh = os.find(o => o.id === selected.id)
        setSelected(fresh ?? null)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro ao carregar')
    } finally {
      setLoading(false)
    }
  }, [selected])

  useEffect(() => { load() }, []) // eslint-disable-line

  // Veio de Mesas com ?table=<id> → abre direto a comanda dessa mesa
  useEffect(() => {
    if (!tableParam || orders.length === 0) return
    const match = orders.find(o => o.table_id === tableParam)
    if (match) {
      setSelected(match)
      setMobileDetail(true)
    }
    setSearchParams({}, { replace: true })
  }, [tableParam, orders, setSearchParams])

  function handleSelect(order: Order) {
    setSelected(order)
    setMobileDetail(true)
  }

  function handleUpdated(updated: Order) {
    setOrders(prev => prev.map(o => o.id === updated.id ? updated : o))
    setSelected(updated)
  }

  function handleClosed(orderId: string) {
    setOrders(prev => prev.filter(o => o.id !== orderId))
    setSelected(null)
    setMobileDetail(false)
  }

  const visible = orders.filter(o => {
    if (!search) return true
    const q = search.toLowerCase()
    const table = tables.find(t => t.id === o.table_id)
    return (
      o.customer_name?.toLowerCase().includes(q) ||
      table?.label.toLowerCase().includes(q) ||
      String(table?.number).includes(q)
    )
  })

  return (
    <div className="h-full flex">

      {/* Painel esquerdo — lista de comandas */}
      <div className={[
        'flex flex-col border-r border-stone-800/50 shrink-0',
        'w-full md:w-80',
        mobileDetail ? 'hidden md:flex' : 'flex',
      ].join(' ')}>

        {/* Cabeçalho da lista */}
        <div className="px-4 pt-5 pb-4 border-b border-stone-800/50 shrink-0"
             style={{ background: '#0f0d0a' }}>
          <div className="flex items-center justify-between mb-4">
            <div>
              <h1 className="text-stone-100 text-lg font-bold leading-tight">Pedidos</h1>
              {!loading && (
                <p className="text-stone-500 text-xs mt-0.5">{orders.length} {orders.length === 1 ? 'comanda aberta' : 'comandas abertas'}</p>
              )}
            </div>
            <div className="flex gap-2">
              <button onClick={load} disabled={loading}
                className="flex items-center justify-center w-9 h-9 rounded-xl
                           border border-stone-800/60 text-stone-500 hover:text-stone-300
                           hover:border-stone-700/60 disabled:opacity-40 transition-all"
                style={{ background: '#161210' }}>
                <svg className={['w-4 h-4', loading ? 'animate-spin' : ''].join(' ')}
                     fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round"
                        d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                </svg>
              </button>
              <button onClick={() => setShowNewOrder(true)}
                className="flex items-center gap-1.5 px-3 py-2 rounded-xl text-sm font-semibold
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
              placeholder="Buscar mesa ou cliente…"
              className="w-full pl-9 pr-4 py-2.5 rounded-xl text-sm border border-stone-800/60
                         text-stone-200 placeholder-stone-600 focus:outline-none
                         focus:border-amber-500/40 focus:ring-1 focus:ring-amber-500/20 transition-all"
              style={{ background: '#161210' }} />
          </div>
        </div>

        {/* Lista */}
        <div className="flex-1 overflow-y-auto relative">
          {error && (
            <div className="m-4 flex items-center gap-3 bg-red-500/10 border border-red-500/20
                            text-red-400 text-sm rounded-2xl px-4 py-3">
              {error}
              <button onClick={load} className="ml-auto text-xs underline underline-offset-2">
                Tentar
              </button>
            </div>
          )}

          {loading ? (
            <div className="space-y-px">
              {Array.from({ length: 4 }).map((_, i) => (
                <div key={i} className="px-4 py-4 border-b border-stone-800/40 animate-pulse">
                  <div className="flex gap-3">
                    <div className="w-7 h-6 bg-stone-800 rounded" />
                    <div className="flex-1 space-y-2">
                      <div className="w-32 h-4 bg-stone-800 rounded" />
                      <div className="w-20 h-3 bg-stone-800 rounded" />
                    </div>
                    <div className="w-14 h-5 bg-stone-800 rounded-full" />
                  </div>
                </div>
              ))}
            </div>
          ) : visible.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-20 text-center px-4">
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
            visible.map(order => (
              <div key={order.id} className="relative">
                <OrderCard
                  order={order}
                  table={tables.find(t => t.id === order.table_id)}
                  selected={selected?.id === order.id}
                  onClick={() => handleSelect(order)}
                />
              </div>
            ))
          )}
        </div>
      </div>

      {/* Painel direito — detalhe */}
      <div className={[
        'flex-1 overflow-hidden',
        mobileDetail ? 'flex flex-col' : 'hidden md:flex md:flex-col',
      ].join(' ')}>
        {selected ? (
          <OrderDetail
            order={selected}
            table={tables.find(t => t.id === selected.table_id)}
            onUpdated={handleUpdated}
            onClosed={handleClosed}
            onBack={mobileDetail ? () => setMobileDetail(false) : undefined}
          />
        ) : (
          <EmptyDetail />
        )}
      </div>

      {/* Modal: novo pedido */}
      {showNewOrder && (
        <NewOrderModal
          onClose={() => setShowNewOrder(false)}
          onCreated={order => {
            setOrders(prev => [order, ...prev])
            setSelected(order)
            setMobileDetail(true)
            setShowNewOrder(false)
          }}
        />
      )}
    </div>
  )
}
