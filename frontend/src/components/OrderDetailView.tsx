import { useState, useEffect, useCallback } from 'react'
import {
  type Order, type OrderItem, type Table, type Category, type MenuItem,
  type Payment, type PaymentMethod,
  fetchCategories, fetchMenuItems,
  addOrderItem, cancelOrderItem, closeOrder, updateTableStatus,
  fetchOrderPayments, registerPayment, finishOrder,
} from '../lib/api'
import { maskCurrency, parseCurrency, toCurrencyInput } from '../lib/format'

// ── Helpers ───────────────────────────────────────────────────────────────────

export function brl(v: string | number) {
  return Number(v).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })
}

export function timeAgo(iso: string) {
  const diff = Date.now() - new Date(iso).getTime()
  const m = Math.floor(diff / 60000)
  if (m < 1) return 'agora'
  if (m < 60) return `${m}min`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h}h`
  return `${Math.floor(h / 24)}d`
}

export const ORDER_STATUS = {
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
      const updated = await cancelOrderItem(item.order_id, item.id, reason.trim() || undefined)
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
  const [comp, setComp] = useState('')   // complemento escolhido (corte/sabor)
  const [adding, setAdding] = useState(false)
  const [addError, setAddError] = useState<string | null>(null)

  // Estado do item manual
  const [manName, setManName] = useState('')
  const [manPrice, setManPrice] = useState('')
  const [manQty, setManQty] = useState('1')
  const [manNotes, setManNotes] = useState('')

  // Estado da pizza meia a meia
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
    // Complemento obrigatório quando o item tem opções cadastradas
    if (picking.complementos.length > 0 && !comp) {
      setAddError('Escolha uma opção para este item')
      return
    }
    setAddError(null)
    setAdding(true)
    try {
      const finalNotes = [comp, notes.trim()].filter(Boolean).join(' · ') || null
      const updated = await addOrderItem(order.id, {
        menu_item_id: picking.id,
        quantity: Number(qty),
        notes: finalNotes,
      })
      onAdded(updated)
      setPicking(null); setQty('1'); setNotes(''); setComp('')
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

  // Meia a meia é EXCLUSIVO de Pizza: só itens de categoria cujo nome contém "pizza"
  const pizzaCatIds = new Set(
    categories.filter(c => c.name.toLowerCase().includes('pizza')).map(c => c.id),
  )
  const halfOptions = items.filter(i => pizzaCatIds.has(i.category_id))

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
              {/* Complemento obrigatório (corte do churrasco, sabor do suco, etc.) */}
              {picking.complementos.length > 0 && (
                <Field label="Escolha uma opção (obrigatório)">
                  <div className="flex flex-wrap gap-1.5">
                    {picking.complementos.map(opt => (
                      <button key={opt} type="button" onClick={() => setComp(opt)}
                        className={[
                          'px-3 py-1.5 rounded-lg text-xs font-semibold transition-all border',
                          comp === opt
                            ? 'bg-amber-500/15 text-amber-400 border-amber-500/30'
                            : 'text-stone-400 border-stone-800/60 hover:text-stone-200',
                        ].join(' ')}>
                        {opt}
                      </button>
                    ))}
                  </div>
                </Field>
              )}
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
                  <button key={item.id} onClick={() => { setPicking(item); setQty('1'); setNotes(''); setComp('') }}
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
        /* Tab meia a meia — exclusivo de Pizza */
        loadingMenu ? (
          <div className="text-center py-8 text-stone-600 text-sm">Carregando cardápio…</div>
        ) : halfOptions.length === 0 ? (
          <div className="text-center py-8">
            <p className="text-stone-500 text-sm">Meia a meia é só para Pizza</p>
            <p className="text-stone-700 text-xs mt-1">
              Crie uma categoria com "Pizza" no nome e cadastre os sabores no Cardápio
            </p>
          </div>
        ) : (
          <form onSubmit={addHalf} className="space-y-3">
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

// ── Detalhe da comanda (tela cheia) ───────────────────────────────────────────

export function OrderDetail({
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
          {/* Botão voltar */}
          {onBack && (
            <button onClick={onBack} className="mt-0.5 text-stone-500 hover:text-stone-300 transition-colors mr-1">
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
              </svg>
            </button>
          )}

          <div className="w-10 h-10 rounded-xl bg-stone-800 border border-stone-700/50
                          flex items-center justify-center shrink-0">
            <span className="text-lg font-black text-stone-100">{table?.number ?? '•'}</span>
          </div>

          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <h2 className="text-stone-100 font-bold text-base leading-tight">
                {order.customer_name ?? table?.label ?? 'Comanda avulsa'}
              </h2>
              <span className={['text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full border', cfg.color, cfg.bg, cfg.border].join(' ')}>
                {cfg.label}
              </span>
            </div>
            <p className="text-stone-500 text-xs mt-0.5">
              {table ? `Mesa ${table.number} · ` : 'Balcão · '}
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
            {activeItems.map(item => (
              <OrderItemRow
                key={item.id}
                item={item}
                canCancel={canEdit}
                onCancelled={onUpdated}
              />
            ))}

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
