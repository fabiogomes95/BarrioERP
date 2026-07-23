import { useState, useEffect, useCallback } from 'react'
import {
  type Order, type OrderItem, type Table, type Category, type MenuItem,
  type Payment, type PaymentMethod,
  fetchCategories, fetchMenuItems,
  addOrderItem, cancelOrderItem, cancelOrder, setItemQuantity, setOrderDiscount, setOrderServiceFee, closeOrder, requestBill,
  fetchOrderPayments, registerPayment, finishOrder, updateOrderCustomerName, getUser, requestRemotePrint,
} from '../lib/api'
import { maskCurrency, parseCurrency, toCurrencyInput } from '../lib/format'
import { printComanda, printCozinha, type KitchenItem } from '../lib/print'
import { shareReceiptWhatsApp } from '../lib/receiptImage'
import { isPrintStation } from '../lib/notifications'
import { inputCls, Field, ModalOverlay, QtyStepper } from './ui'

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



// ── Linha de item da comanda ──────────────────────────────────────────────────

function OrderItemRow({
  item, canCancel, onCancelled, kitchenMode, kitchenSelected, onKitchenToggle,
}: {
  item: OrderItem
  canCancel: boolean
  onCancelled: (updated: Order) => void
  kitchenMode?: boolean
  kitchenSelected?: boolean
  onKitchenToggle?: () => void
}) {
  const [cancelling, setCancelling] = useState(false)
  const [reason, setReason] = useState('')
  const [loading, setLoading] = useState(false)
  const [qtyLoading, setQtyLoading] = useState(false)

  const isCancelled = item.status === 'cancelled'
  const editable = canCancel && !isCancelled && item.status !== 'served'

  async function changeQty(delta: number) {
    const next = item.quantity + delta
    if (next < 1 || qtyLoading) return
    setQtyLoading(true)
    try {
      const updated = await setItemQuantity(item.order_id, item.id, next)
      onCancelled(updated)
    } finally {
      setQtyLoading(false)
    }
  }

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
          <div className="flex items-center gap-2">
            {editable ? (
              <div className="flex items-center gap-1.5 shrink-0">
                <button onClick={() => changeQty(-1)} disabled={qtyLoading || item.quantity <= 1}
                  className="w-6 h-6 flex items-center justify-center rounded-lg border border-stone-700/60
                             text-stone-300 hover:bg-stone-800/60 disabled:opacity-30 transition-colors">
                  <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                    <path strokeLinecap="round" d="M5 12h14" />
                  </svg>
                </button>
                <span className="text-stone-200 text-sm font-bold w-5 text-center tabular-nums">{item.quantity}</span>
                <button onClick={() => changeQty(1)} disabled={qtyLoading || item.quantity >= 99}
                  className="w-6 h-6 flex items-center justify-center rounded-lg border border-stone-700/60
                             text-stone-300 hover:bg-stone-800/60 disabled:opacity-30 transition-colors">
                  <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                    <path strokeLinecap="round" d="M12 5v14M5 12h14" />
                  </svg>
                </button>
              </div>
            ) : (
              <span className="text-stone-500 text-xs font-bold">{item.quantity}×</span>
            )}
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
        <div className="flex items-center gap-1.5 shrink-0">
          <span className={['text-sm font-semibold', isCancelled ? 'text-stone-600' : 'text-stone-300'].join(' ')}>
            {brl(item.subtotal)}
          </span>
          {kitchenMode && !isCancelled ? (
            <button onClick={onKitchenToggle}
              className={[
                'w-6 h-6 rounded-full border-2 flex items-center justify-center transition-all',
                kitchenSelected
                  ? 'bg-amber-500 border-amber-500 text-stone-900'
                  : 'border-stone-600 text-transparent hover:border-amber-500/60',
              ].join(' ')}>
              <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
              </svg>
            </button>
          ) : (
            canCancel && !isCancelled && item.status !== 'served' && (
              <button onClick={() => setCancelling(v => !v)}
                className="w-6 h-6 flex items-center justify-center rounded-lg
                           text-stone-700 hover:text-red-400 hover:bg-red-500/10 transition-all">
                <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            )
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
  order, table, onClose, onAdded,
}: {
  order: Order
  table: Table | undefined
  onClose: () => void
  onAdded: (updated: Order) => void
}) {
  const where = table ? `Mesa ${table.number}` : 'Balcão'
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
    const h = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', h)
    return () => document.removeEventListener('keydown', h)
  }, [onClose])

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

  async function addFromMenu(andPrint = false) {
    if (!picking) return
    setAddError(null)
    setAdding(true)
    try {
      const effectiveName = comp ? `${picking.name} - ${comp}` : picking.name
      const updated = comp
        ? await addOrderItem(order.id, {
            item_name: effectiveName,
            unit_price: Number(picking.price),
            quantity: Number(qty),
            notes: notes.trim() || null,
          })
        : await addOrderItem(order.id, {
            menu_item_id: picking.id,
            quantity: Number(qty),
            notes: notes.trim() || null,
          })
      if (andPrint) printCozinha([{ name: effectiveName, qty: Number(qty), notes: notes.trim() || null }], where)
      onAdded(updated)
      setPicking(null); setQty('1'); setNotes(''); setComp('')
    } catch (err) {
      setAddError(err instanceof Error ? err.message : 'Erro ao adicionar')
    } finally {
      setAdding(false)
    }
  }

  async function addManual(andPrint = false) {
    const name = manName.trim()
    if (!name || !manPrice) { setAddError('Preencha nome e preço'); return }
    setAddError(null)
    setAdding(true)
    try {
      const updated = await addOrderItem(order.id, {
        item_name: name,
        unit_price: parseCurrency(manPrice),
        quantity: Number(manQty),
        notes: manNotes.trim() || null,
      })
      if (andPrint) printCozinha([{ name, qty: Number(manQty), notes: manNotes.trim() || null }], where)
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

  async function addHalf(andPrint = false) {
    if (!halfItem1 || !halfItem2) { setAddError('Escolha os dois sabores'); return }
    setAddError(null)
    setAdding(true)
    const words1 = halfItem1.name.split(' ')
    const words2 = halfItem2.name.split(' ')
    const short2 = words1[0] === words2[0] ? words2.slice(1).join(' ') : halfItem2.name
    const name = `${halfItem1.name} / ${short2}`
    try {
      const updated = await addOrderItem(order.id, {
        item_name: name,
        unit_price: halfPrice,
        quantity: Number(halfQty),
        notes: halfNotes.trim() || null,
      })
      if (andPrint) printCozinha([{ name, qty: Number(halfQty), notes: halfNotes.trim() || null }], where)
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
    // No mobile ocupa a tela inteira (em vez de um cartão flutuante) — assim o navegador
    // consegue rolar até o campo focado mesmo com o teclado virtual cobrindo boa parte da tela.
    // A partir de sm, volta a ser o modal centralizado de sempre.
    <div className="fixed inset-0 z-50 flex flex-col sm:items-center sm:justify-center sm:p-4"
         style={{ background: 'rgba(0,0,0,0.75)' }}
         onClick={onClose}>
      <div className="w-full h-[100dvh] sm:h-auto sm:max-w-md sm:max-h-[85dvh] sm:rounded-3xl
                      overflow-y-auto overscroll-contain flex flex-col p-5"
           style={{ background: '#161210' }}
           onClick={e => e.stopPropagation()}>
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
        <div className="flex flex-col flex-1 min-h-0 gap-3">
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
              {/* Complemento opcional (corte do churrasco, sabor do suco, etc.) */}
              {picking.complementos.length > 0 && (
                <Field label="Escolha uma opção (opcional)">
                  <div className="flex flex-wrap gap-1.5">
                    {picking.complementos.map(opt => (
                      <button key={opt} type="button" onClick={() => setComp(c => c === opt ? '' : opt)}
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
              <Field label="Quantidade">
                <QtyStepper value={Number(qty)} onChange={n => setQty(String(n))} />
              </Field>
              <Field label="Observações (opcional)">
                <input type="text" value={notes} onChange={e => setNotes(e.target.value)}
                  placeholder="ex: sem cebola, ao ponto"
                  className={inputCls} style={{ background: '#0d0b08' }} />
              </Field>
              <div className="flex gap-2">
                <button onClick={() => setPicking(null)}
                  className="px-3 py-2.5 rounded-xl text-sm font-semibold
                             text-stone-400 border border-stone-700/60 hover:bg-stone-800/50 transition-colors">
                  Voltar
                </button>
                <button onClick={() => addFromMenu()} disabled={adding}
                  className="flex-1 py-2.5 rounded-xl text-sm font-semibold
                             bg-amber-500 hover:bg-amber-400 text-stone-900
                             disabled:opacity-40 transition-colors">
                  {adding ? 'Adicionando…' : 'Adicionar'}
                </button>
                <button onClick={() => addFromMenu(true)} disabled={adding}
                  title="Adicionar e imprimir na cozinha"
                  className="px-3 py-2.5 rounded-xl border border-stone-700/60 text-stone-400
                             hover:text-amber-400 hover:border-stone-700/80 disabled:opacity-40 transition-all">
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.75}>
                    <path strokeLinecap="round" strokeLinejoin="round"
                      d="M17 17h2a2 2 0 002-2v-4a2 2 0 00-2-2H5a2 2 0 00-2 2v4a2 2 0 002 2h2m2 4h6a1 1 0 001-1v-4a1 1 0 00-1-1H9a1 1 0 00-1 1v4a1 1 0 001 1zm8-12V5a2 2 0 00-2-2H7a2 2 0 00-2 2v4h14z" />
                  </svg>
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
              <div className="flex-1 min-h-0 overflow-y-auto space-y-1 -mx-1 px-1">
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
          <form onSubmit={e => { e.preventDefault(); addHalf() }} className="space-y-3">
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
              <QtyStepper value={Number(halfQty)} onChange={n => setHalfQty(String(n))} />
            </Field>
            <Field label="Observações (opcional)">
              <input type="text" value={halfNotes} onChange={e => setHalfNotes(e.target.value)}
                placeholder="ex: borda recheada, sem cebola"
                className={inputCls} style={{ background: '#0d0b08' }} />
            </Field>
            <div className="flex gap-2 mt-1">
              <button type="submit" disabled={adding || !halfItem1 || !halfItem2}
                className="flex-1 py-2.5 rounded-xl text-sm font-semibold
                           bg-amber-500 hover:bg-amber-400 text-stone-900
                           disabled:opacity-40 transition-colors">
                {adding ? 'Adicionando…' : 'Adicionar meia a meia'}
              </button>
              <button type="button" onClick={() => addHalf(true)} disabled={adding || !halfItem1 || !halfItem2}
                title="Adicionar e imprimir na cozinha"
                className="px-3 py-2.5 rounded-xl border border-stone-700/60 text-stone-400
                           hover:text-amber-400 hover:border-stone-700/80 disabled:opacity-40 transition-all">
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.75}>
                  <path strokeLinecap="round" strokeLinejoin="round"
                    d="M17 17h2a2 2 0 002-2v-4a2 2 0 00-2-2H5a2 2 0 00-2 2v4a2 2 0 002 2h2m2 4h6a1 1 0 001-1v-4a1 1 0 00-1-1H9a1 1 0 00-1 1v4a1 1 0 001 1zm8-12V5a2 2 0 00-2-2H7a2 2 0 00-2 2v4h14z" />
                </svg>
              </button>
            </div>
          </form>
        )
      ) : (
        /* Tab manual */
        <form onSubmit={e => { e.preventDefault(); addManual() }} className="space-y-3">
          <Field label="Nome do item">
            <input type="text" required value={manName} onChange={e => setManName(e.target.value)}
              placeholder="ex: Cerveja especial" className={inputCls} style={{ background: '#0d0b08' }} />
          </Field>
          <Field label="Preço (R$)">
            <input type="text" inputMode="numeric" required value={manPrice}
              onChange={e => setManPrice(maskCurrency(e.target.value))}
              placeholder="0,00" className={inputCls} style={{ background: '#0d0b08' }} />
          </Field>
          <Field label="Quantidade">
            <QtyStepper value={Number(manQty)} onChange={n => setManQty(String(n))} />
          </Field>
          <Field label="Observações (opcional)">
            <input type="text" value={manNotes} onChange={e => setManNotes(e.target.value)}
              placeholder="ex: sem gelo" className={inputCls} style={{ background: '#0d0b08' }} />
          </Field>
          <div className="flex gap-2 mt-1">
            <button type="submit" disabled={adding}
              className="flex-1 py-2.5 rounded-xl text-sm font-semibold
                         bg-amber-500 hover:bg-amber-400 text-stone-900
                         disabled:opacity-40 transition-colors">
              {adding ? 'Adicionando…' : 'Adicionar item'}
            </button>
            <button type="button" onClick={() => addManual(true)} disabled={adding}
              title="Adicionar e imprimir na cozinha"
              className="px-3 py-2.5 rounded-xl border border-stone-700/60 text-stone-400
                         hover:text-amber-400 hover:border-stone-700/80 disabled:opacity-40 transition-all">
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.75}>
                <path strokeLinecap="round" strokeLinejoin="round"
                  d="M17 17h2a2 2 0 002-2v-4a2 2 0 00-2-2H5a2 2 0 00-2 2v4a2 2 0 002 2h2m2 4h6a1 1 0 001-1v-4a1 1 0 00-1-1H9a1 1 0 00-1 1v4a1 1 0 001 1zm8-12V5a2 2 0 00-2-2H7a2 2 0 00-2 2v4h14z" />
              </svg>
            </button>
          </div>
        </form>
      )}
      </div>
    </div>
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
  order, onClose, onFinished, onPaidUpdate,
}: {
  order: Order
  onClose: () => void
  onFinished: (orderId: string) => void
  onPaidUpdate?: (paid: number) => void
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

  // Notifica o pai com o valor já pago sempre que a lista de pagamentos muda
  useEffect(() => {
    onPaidUpdate?.(paid)
  }, [paid, onPaidUpdate])

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

// ── Modal: Dividir conta ──────────────────────────────────────────────────────

/** Divide `total` (R$) em `count` partes exatas em centavos (sem perda de precisão). */
function splitAmounts(total: number, count: number): number[] {
  const totalCents = Math.round(total * 100)
  const base = Math.floor(totalCents / count)
  const remainder = totalCents - base * count
  return Array.from({ length: count }, (_, i) => (base + (i < remainder ? 1 : 0)) / 100)
}

/** Distribui `total` (R$) proporcionalmente aos subtotais de cada pessoa, exato em centavos. */
function splitByShares(total: number, shares: number[]): number[] {
  const totalCents = Math.round(total * 100)
  const shareSum = shares.reduce((a, b) => a + b, 0)
  if (shareSum <= 0) return shares.map(() => 0)

  const raw = shares.map(s => (s / shareSum) * totalCents)
  const cents = raw.map(v => Math.floor(v))
  let remainder = totalCents - cents.reduce((a, b) => a + b, 0)

  // Método dos maiores restos: sobra de centavos vai pra quem tem a maior fração perdida no floor.
  const order = raw
    .map((v, i) => ({ i, frac: v - Math.floor(v) }))
    .sort((a, b) => b.frac - a.frac)
  for (let k = 0; k < remainder; k++) cents[order[k % order.length].i] += 1

  return cents.map(c => c / 100)
}

function SplitModal({
  order, onClose, onFinished, onPaidUpdate,
}: {
  order: Order
  onClose: () => void
  onFinished: (orderId: string) => void
  onPaidUpdate?: (paid: number) => void
}) {
  const [mode, setMode] = useState<'equal' | 'items'>('equal')
  const [count, setCount] = useState(2)
  const [assignments, setAssignments] = useState<Record<string, number>>({})
  const [payments, setPayments] = useState<Payment[]>([])
  const [loading, setLoading] = useState(true)
  const [activeSlot, setActiveSlot] = useState<number | null>(null)
  const [method, setMethod] = useState<PaymentMethod>('cash')
  const [amount, setAmount] = useState('')
  const [tendered, setTendered] = useState('')
  const [saving, setSaving] = useState(false)
  const [finishing, setFinishing] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const total = Number(order.total)
  const paid = payments
    .filter(p => p.status === 'confirmed')
    .reduce((sum, p) => sum + Number(p.amount), 0)
  const remaining = Math.max(0, Math.round((total - paid) * 100) / 100)
  const fullyPaid = remaining <= 0

  const activeItems = order.items.filter(i => i.status !== 'cancelled')
  const unassignedItems = mode === 'items'
    ? activeItems.filter(it => assignments[it.id] === undefined || assignments[it.id] >= count)
    : []
  const readyToPay = mode === 'equal' || unassignedItems.length === 0

  const amounts = mode === 'equal'
    ? splitAmounts(total, count)
    : readyToPay
      ? splitByShares(
          total,
          Array.from({ length: count }, (_, p) =>
            activeItems.filter(it => assignments[it.id] === p)
              .reduce((sum, it) => sum + Number(it.subtotal), 0)),
        )
      : Array(count).fill(0)

  // Heurística: marca como pagas as primeiras N parcelas cujo valor acumulado já foi coberto.
  let acc = 0
  const slotPaid = amounts.map(a => { acc += a; return acc <= paid + 0.005 })

  function assignItem(itemId: string, person: number) {
    setAssignments(prev => {
      const next = { ...prev }
      if (next[itemId] === person) delete next[itemId]
      else next[itemId] = person
      return next
    })
  }

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

  useEffect(() => {
    onPaidUpdate?.(paid)
  }, [paid, onPaidUpdate])

  function openSlot(i: number) {
    setError(null)
    setActiveSlot(i)
    setAmount(toCurrencyInput(Math.min(amounts[i], remaining)))
    setTendered('')
    setMethod('cash')
  }

  async function handlePaySlot(e: React.FormEvent) {
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
        reference: null,
      })
      await refreshPayments()
      setActiveSlot(null)
      setTendered('')
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
        <h2 className="text-stone-100 text-base font-bold">Dividir conta</h2>
        <button onClick={onClose} className="text-stone-600 hover:text-stone-400 transition-colors">
          <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      {/* Modo de divisão */}
      <div className="flex gap-1 p-1 rounded-xl mb-4" style={{ background: '#0d0b08' }}>
        {([['equal', 'Igualmente'], ['items', 'Por item']] as const).map(([m, label]) => (
          <button key={m} onClick={() => setMode(m)}
            className={[
              'flex-1 py-2 rounded-lg text-xs font-semibold transition-all',
              mode === m ? 'bg-amber-500/15 text-amber-400' : 'text-stone-500 hover:text-stone-300',
            ].join(' ')}>
            {label}
          </button>
        ))}
      </div>

      {/* Stepper de pessoas */}
      <div className="flex items-center justify-between rounded-2xl p-4 mb-4" style={{ background: '#0d0b08' }}>
        <span className="text-stone-500 text-sm">Dividir entre</span>
        <div className="flex items-center gap-3">
          <button type="button" onClick={() => setCount(c => Math.max(2, c - 1))} disabled={count <= 2}
            className="w-8 h-8 flex items-center justify-center rounded-lg border border-stone-700/60
                       text-stone-300 hover:bg-stone-800/60 disabled:opacity-30 transition-colors">
            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
              <path strokeLinecap="round" d="M5 12h14" />
            </svg>
          </button>
          <span className="text-stone-100 text-base font-black w-16 text-center tabular-nums">
            {count} {count === 1 ? 'pessoa' : 'pessoas'}
          </span>
          <button type="button" onClick={() => setCount(c => Math.min(20, c + 1))} disabled={count >= 20}
            className="w-8 h-8 flex items-center justify-center rounded-lg border border-stone-700/60
                       text-stone-300 hover:bg-stone-800/60 disabled:opacity-30 transition-colors">
            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
              <path strokeLinecap="round" d="M12 5v14M5 12h14" />
            </svg>
          </button>
        </div>
      </div>

      {/* Atribuição de itens por pessoa */}
      {mode === 'items' && (
        <div className="rounded-2xl p-3 mb-4 space-y-1" style={{ background: '#0d0b08' }}>
          {activeItems.length === 0 ? (
            <p className="text-stone-600 text-xs text-center py-2">Comanda sem itens</p>
          ) : (
            activeItems.map(item => (
              <div key={item.id} className="flex items-center justify-between gap-2 py-1.5">
                <div className="min-w-0 flex-1">
                  <p className="text-stone-300 text-xs truncate">{item.quantity}x {item.item_name}</p>
                  <p className="text-stone-600 text-[11px]">{brl(item.subtotal)}</p>
                </div>
                <div className="flex items-center gap-1 shrink-0">
                  {Array.from({ length: count }, (_, p) => (
                    <button key={p} type="button" onClick={() => assignItem(item.id, p)}
                      title={`Pessoa ${p + 1}`}
                      className={[
                        'w-6 h-6 rounded-full text-[10px] font-bold transition-all border',
                        assignments[item.id] === p
                          ? 'bg-amber-500 text-stone-900 border-amber-500'
                          : 'text-stone-500 border-stone-700/60 hover:border-stone-600',
                      ].join(' ')}>
                      {p + 1}
                    </button>
                  ))}
                </div>
              </div>
            ))
          )}
          {unassignedItems.length > 0 && (
            <p className="text-amber-400 text-[11px] pt-1.5 border-t border-stone-800/60">
              {unassignedItems.length} {unassignedItems.length === 1 ? 'item sem atribuir' : 'itens sem atribuir'} — toque no número da pessoa
            </p>
          )}
        </div>
      )}

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

      {loading ? (
        <div className="text-center py-6 text-stone-600 text-sm">Carregando pagamentos…</div>
      ) : !readyToPay ? (
        <p className="text-stone-600 text-sm text-center py-4">
          Atribua todos os itens a alguém pra ver o valor de cada pessoa
        </p>
      ) : (
        <>
          {/* Lista de parcelas por pessoa */}
          <div className="space-y-1.5 mb-2">
            {amounts.map((slotAmount, i) => (
              <div key={i} className="rounded-xl overflow-hidden" style={{ background: '#0d0b08' }}>
                <div className="flex items-center justify-between px-3.5 py-2.5">
                  <span className="text-stone-300 text-sm font-medium">Pessoa {i + 1}</span>
                  <div className="flex items-center gap-3">
                    <span className="text-stone-200 text-sm font-semibold">{brl(slotAmount)}</span>
                    {slotPaid[i] ? (
                      <span className="text-green-400 text-xs font-bold">✓ Pago</span>
                    ) : (
                      <button
                        onClick={() => (activeSlot === i ? setActiveSlot(null) : openSlot(i))}
                        className="text-xs font-bold text-amber-400 hover:text-amber-300 transition-colors px-2 py-1">
                        {activeSlot === i ? 'Fechar' : 'Receber'}
                      </button>
                    )}
                  </div>
                </div>

                {activeSlot === i && !slotPaid[i] && (
                  <form onSubmit={handlePaySlot} className="px-3.5 pb-3.5 space-y-3">
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
                          placeholder="0,00" className={inputCls} style={{ background: '#161210' }} />
                      </Field>
                      {method === 'cash' && (
                        <Field label="Recebido (R$)">
                          <input type="text" inputMode="numeric" value={tendered}
                            onChange={e => setTendered(maskCurrency(e.target.value))}
                            placeholder="0,00" className={inputCls} style={{ background: '#161210' }} />
                        </Field>
                      )}
                    </div>

                    {method === 'cash' && change > 0 && (
                      <div className="flex justify-between text-xs px-1">
                        <span className="text-stone-500">Troco</span>
                        <span className="text-amber-400 font-bold">{brl(change)}</span>
                      </div>
                    )}

                    <button type="submit" disabled={saving}
                      className="w-full py-2 rounded-xl text-sm font-semibold
                                 bg-amber-500 hover:bg-amber-400 text-stone-900
                                 disabled:opacity-40 transition-colors">
                      {saving ? 'Registrando…' : 'Registrar pagamento'}
                    </button>
                  </form>
                )}
              </div>
            ))}
          </div>

          {fullyPaid && (
            <button onClick={handleFinish} disabled={finishing}
              className="w-full py-3 rounded-xl text-sm font-bold mt-3
                         bg-green-500 hover:bg-green-400 text-stone-900
                         disabled:opacity-40 transition-colors">
              {finishing ? 'Finalizando…' : 'Finalizar comanda e liberar mesa'}
            </button>
          )}
        </>
      )}
    </ModalOverlay>
  )
}

// ── Modal: Desconto ───────────────────────────────────────────────────────────

function DiscountModal({
  order, onClose, onUpdated,
}: {
  order: Order
  onClose: () => void
  onUpdated: (o: Order) => void
}) {
  const subtotal = Number(order.subtotal)
  const [mode, setMode] = useState<'value' | 'percent'>('value')
  const [value, setValue] = useState(Number(order.discount) > 0 ? toCurrencyInput(order.discount) : '')
  const [percent, setPercent] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const discountValue = mode === 'value'
    ? parseCurrency(value)
    : Math.round(subtotal * (parseFloat(percent.replace(',', '.')) || 0)) / 100

  async function apply(amount: number) {
    setError(null)
    if (isNaN(amount) || amount < 0) { setError('Valor inválido'); return }
    if (amount > subtotal) { setError('O desconto não pode exceder o subtotal'); return }
    setSaving(true)
    try {
      const updated = await setOrderDiscount(order.id, amount)
      onUpdated(updated)
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro ao aplicar desconto')
    } finally {
      setSaving(false)
    }
  }

  return (
    <ModalOverlay onClose={onClose}>
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-stone-100 text-base font-bold">Desconto</h2>
        <button onClick={onClose} className="text-stone-600 hover:text-stone-400 transition-colors">
          <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      <div className="flex gap-1 p-1 rounded-xl mb-4" style={{ background: '#0d0b08' }}>
        {(['value', 'percent'] as const).map(m => (
          <button key={m} onClick={() => setMode(m)}
            className={['flex-1 py-2 rounded-lg text-xs font-semibold transition-all',
              mode === m ? 'bg-amber-500/15 text-amber-400' : 'text-stone-500 hover:text-stone-300'].join(' ')}>
            {m === 'value' ? 'Valor (R$)' : 'Percentual (%)'}
          </button>
        ))}
      </div>

      {error && (
        <p className="text-red-400 text-xs bg-red-500/10 border border-red-500/20 rounded-xl px-3 py-2 mb-3">{error}</p>
      )}

      {mode === 'value' ? (
        <Field label="Desconto (R$)">
          <input type="text" inputMode="numeric" value={value} autoFocus
            onChange={e => setValue(maskCurrency(e.target.value))}
            placeholder="0,00" className={inputCls} style={{ background: '#0d0b08' }} />
        </Field>
      ) : (
        <Field label="Desconto (%)">
          <input type="number" min={0} max={100} value={percent} autoFocus
            onChange={e => setPercent(e.target.value)}
            placeholder="ex: 10" className={inputCls} style={{ background: '#0d0b08' }} />
        </Field>
      )}

      <div className="flex justify-between text-xs px-1 mt-3">
        <span className="text-stone-500">Desconto aplicado</span>
        <span className="text-amber-400 font-bold">{brl(discountValue || 0)}</span>
      </div>

      <div className="flex gap-2 mt-4">
        {Number(order.discount) > 0 && (
          <button onClick={() => apply(0)} disabled={saving}
            className="px-3 py-2.5 rounded-xl text-sm font-semibold text-red-400 border border-red-500/30
                       hover:bg-red-500/10 disabled:opacity-40 transition-colors">
            Remover
          </button>
        )}
        <button onClick={() => apply(discountValue)} disabled={saving}
          className="flex-1 py-2.5 rounded-xl text-sm font-semibold bg-amber-500 hover:bg-amber-400
                     text-stone-900 disabled:opacity-40 transition-colors">
          {saving ? 'Aplicando…' : 'Aplicar desconto'}
        </button>
      </div>
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
  const [showSplit, setShowSplit] = useState(false)
  const [showDiscount, setShowDiscount] = useState(false)
  const [togglingFee, setTogglingFee] = useState(false)
  const [closing, setClosing] = useState(false)
  const [requestingBill, setRequestingBill] = useState(false)
  const [printSent, setPrintSent] = useState(false)
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [editingName, setEditingName] = useState(false)
  const [nameInput, setNameInput] = useState('')
  const [savingName, setSavingName] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)
  const [kitchenMode, setKitchenMode] = useState(false)
  const [kitchenSelected, setKitchenSelected] = useState<Set<string>>(new Set())
  const [paidSoFar, setPaidSoFar] = useState(0)
  const [sharingWA, setSharingWA] = useState(false)
  const [waHint, setWaHint] = useState<string | null>(null)
  const remaining = Math.max(0, Math.round((Number(order.total) - paidSoFar) * 100) / 100)

  // Carrega pagamentos do servidor ao abrir ou trocar de comanda
  useEffect(() => {
    fetchOrderPayments(order.id)
      .then(ps => {
        const total = ps
          .filter(p => p.status === 'confirmed')
          .reduce((sum, p) => sum + Number(p.amount), 0)
        setPaidSoFar(total)
      })
      .catch(() => setPaidSoFar(0))
  }, [order.id])

  const kitchenWhere = table
    ? `Mesa ${table.number}`
    : order.order_type === 'delivery'
      ? `Delivery${order.customer_name ? ' - ' + order.customer_name : ''}`
      : order.order_type === 'pickup'
        ? `Retirada${order.customer_name ? ' - ' + order.customer_name : ''}`
        : order.customer_name ?? 'Balcão'

  function enterKitchenMode() {
    const allIds = new Set(activeItems.filter(i => i.status !== 'served').map(i => i.id))
    setKitchenSelected(allIds)
    setKitchenMode(true)
  }

  function exitKitchenMode() {
    setKitchenMode(false)
    setKitchenSelected(new Set())
  }

  function toggleKitchenItem(id: string) {
    setKitchenSelected(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id); else next.add(id)
      return next
    })
  }

  function doKitchenPrint() {
    const items: KitchenItem[] = activeItems
      .filter(i => kitchenSelected.has(i.id))
      .map(i => ({ name: i.item_name, qty: i.quantity, notes: i.notes }))
    if (items.length === 0) return
    printCozinha(items, kitchenWhere)
    exitKitchenMode()
  }

  const cfg = ORDER_STATUS[order.status] ?? ORDER_STATUS.open
  const canEdit = order.status === 'open' || order.status === 'bill_requested'
  const canAddItem = order.status === 'open'
  const canRequestBill = order.status === 'open'
  const canClose = order.status === 'open' || order.status === 'bill_requested'
  // Garçom/cozinha não veem valores nem mexem em fechamento — só quem atende o caixa.
  const role = getUser()?.role
  const canSeeMoney = role !== 'waiter' && role !== 'kitchen'

  const activeItems = order.items.filter(i => i.status !== 'cancelled')
  const cancelledItems = order.items.filter(i => i.status === 'cancelled')

  async function handleRequestBill() {
    setActionError(null)
    setRequestingBill(true)
    try {
      const updated = await requestBill(order.id)
      onUpdated(updated)
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Erro')
    } finally {
      setRequestingBill(false)
    }
  }

  async function handlePrint() {
    // A impressora térmica só está ligada (por cabo) a um PC específico.
    // Se este dispositivo não é ele, manda a impressão pra quem tem.
    if (isPrintStation()) {
      printComanda(order, table, getUser()?.company_name ?? 'BarrioERP')
      return
    }
    setPrintSent(true)
    try {
      await requestRemotePrint(order.id)
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Erro ao enviar impressão')
    } finally {
      setTimeout(() => setPrintSent(false), 2000)
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

  async function handleSaveName() {
    setSavingName(true)
    try {
      const updated = await updateOrderCustomerName(order.id, nameInput.trim() || null)
      onUpdated(updated)
      setEditingName(false)
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Erro ao salvar nome')
    } finally {
      setSavingName(false)
    }
  }

  async function handleDelete() {
    setActionError(null)
    setDeleting(true)
    try {
      await cancelOrder(order.id)
      onClosed(order.id)
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Erro ao apagar comanda')
    } finally {
      setDeleting(false)
      setShowDeleteConfirm(false)
    }
  }

  async function handleShareWhatsApp() {
    setActionError(null)
    setWaHint(null)
    setSharingWA(true)
    try {
      const result = await shareReceiptWhatsApp(order, table, getUser()?.company_name ?? 'BarrioERP')
      if (result === 'downloaded') {
        setWaHint('Imagem baixada — anexe no WhatsApp Web que abriu em outra aba')
        setTimeout(() => setWaHint(null), 6000)
      }
    } catch (err) {
      if (err instanceof Error && err.name !== 'AbortError') {
        setActionError('Erro ao gerar recibo para o WhatsApp')
      }
    } finally {
      setSharingWA(false)
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
              {editingName ? (
                <div className="flex items-center gap-1.5">
                  <input
                    autoFocus
                    type="text"
                    value={nameInput}
                    onChange={e => setNameInput(e.target.value)}
                    onKeyDown={e => {
                      if (e.key === 'Enter') handleSaveName()
                      if (e.key === 'Escape') setEditingName(false)
                    }}
                    className="rounded-lg px-2 py-1 text-sm font-bold border border-amber-500/40
                               text-stone-100 bg-stone-900 focus:outline-none focus:ring-1
                               focus:ring-amber-500/30 w-36"
                  />
                  <button onClick={handleSaveName} disabled={savingName}
                    className="text-[11px] font-bold text-amber-400 hover:text-amber-300
                               disabled:opacity-40 transition-colors py-1 px-1.5">
                    {savingName ? '…' : 'OK'}
                  </button>
                  <button onClick={() => setEditingName(false)}
                    className="text-[11px] text-stone-600 hover:text-stone-400 transition-colors py-1 px-1">
                    ✕
                  </button>
                </div>
              ) : (
                <button
                  onClick={() => { setNameInput(order.customer_name ?? ''); setEditingName(true) }}
                  className="flex items-center gap-1.5 group"
                  title="Editar nome">
                  <h2 className="text-stone-100 font-bold text-base leading-tight group-hover:text-amber-400 transition-colors">
                    {order.customer_name ?? table?.label ?? 'Comanda avulsa'}
                  </h2>
                  <svg className="w-3 h-3 text-stone-700 group-hover:text-amber-400 transition-colors shrink-0"
                       fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                    <path strokeLinecap="round" strokeLinejoin="round"
                      d="M16.862 4.487l1.687-1.688a1.875 1.875 0 112.652 2.652L10.582 16.07a4.5 4.5 0 01-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 011.13-1.897l8.932-8.931z" />
                  </svg>
                </button>
              )}
              <span className={['text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full border', cfg.color, cfg.bg, cfg.border].join(' ')}>
                {cfg.label}
              </span>
              {order.order_type === 'delivery' && (
                <span className="text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full border
                                 text-blue-400 bg-blue-500/10 border-blue-500/25">
                  Delivery
                </span>
              )}
              {order.order_type === 'pickup' && (
                <span className="text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full border
                                 text-purple-400 bg-purple-500/10 border-purple-500/25">
                  Retirada
                </span>
              )}
            </div>
            <p className="text-stone-500 text-xs mt-0.5">
              {table
                ? `Mesa ${table.number}`
                : order.order_type === 'delivery'
                  ? 'Delivery'
                  : order.order_type === 'pickup'
                    ? 'Retirada'
                    : 'Balcão'
              }
              {' · '}{order.guest_count} {order.guest_count === 1 ? 'pessoa' : 'pessoas'} · aberta há {timeAgo(order.created_at)}
            </p>
          </div>

          {/* Imprimir recibo — local se este dispositivo tem a impressora
              térmica, senão manda a impressão pro PC que tem (ver isPrintStation) */}
          <button
            onClick={handlePrint}
            title={isPrintStation() ? 'Imprimir comanda' : 'Enviar para a impressora do bar'}
            className={[
              'shrink-0 flex items-center justify-center w-9 h-9 rounded-xl border transition-all',
              printSent
                ? 'border-green-500/40 text-green-400'
                : 'border-stone-800/60 text-stone-400 hover:text-amber-400 hover:border-stone-700/60',
            ].join(' ')}
            style={{ background: '#161210' }}>
            {printSent ? (
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
              </svg>
            ) : (
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.75}>
                <path strokeLinecap="round" strokeLinejoin="round"
                  d="M17 17h2a2 2 0 002-2v-4a2 2 0 00-2-2H5a2 2 0 00-2 2v4a2 2 0 002 2h2m2 4h6a1 1 0 001-1v-4a1 1 0 00-1-1H9a1 1 0 00-1 1v4a1 1 0 001 1zm8-12V5a2 2 0 00-2-2H7a2 2 0 00-2 2v4h14z" />
              </svg>
            )}
          </button>

          {/* Enviar recibo pelo WhatsApp (imagem formatada, igual ao impresso) */}
          <button
            onClick={handleShareWhatsApp}
            disabled={sharingWA}
            title="Enviar recibo pelo WhatsApp"
            className="shrink-0 flex items-center justify-center w-9 h-9 rounded-xl
                       border border-stone-800/60 text-stone-400 hover:text-green-400
                       hover:border-stone-700/60 disabled:opacity-40 transition-all"
            style={{ background: '#161210' }}>
            {sharingWA ? (
              <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M4 12a8 8 0 018-8" />
              </svg>
            ) : (
              <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
                <path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347z" />
                <path d="M12.001 2C6.478 2 2 6.477 2 12c0 1.912.535 3.7 1.462 5.222L2 22l4.897-1.436A9.945 9.945 0 0012 22c5.523 0 10-4.477 10-10S17.523 2 12.001 2zm0 18.222a8.19 8.19 0 01-4.415-1.284l-.317-.19-3.257.956.972-3.253-.207-.325A8.19 8.19 0 013.778 12c0-4.542 3.68-8.222 8.223-8.222 4.542 0 8.222 3.68 8.222 8.222 0 4.543-3.68 8.222-8.222 8.222z" />
              </svg>
            )}
          </button>
        </div>

        {waHint && (
          <p className="text-green-400 text-xs bg-green-500/10 border border-green-500/20
                         rounded-xl px-3 py-2 mt-3">{waHint}</p>
        )}
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
                canCancel={canEdit && !kitchenMode}
                onCancelled={onUpdated}
                kitchenMode={kitchenMode}
                kitchenSelected={kitchenSelected.has(item.id)}
                onKitchenToggle={() => toggleKitchenItem(item.id)}
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

        {/* Totais — só quem lida com pagamento/caixa vê o valor */}
        {canSeeMoney && (
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
        )}

        {/* Botões de ação */}
        {canClose && (
          kitchenMode ? (
            <div className="space-y-2">
              <p className="text-xs text-stone-500 text-center">
                Selecione os itens para imprimir na cozinha
              </p>
              <div className="flex gap-2">
                <button onClick={exitKitchenMode}
                  className="px-4 py-2.5 rounded-xl text-sm font-semibold
                             text-stone-400 border border-stone-700/60 hover:bg-stone-800/50 transition-colors">
                  Cancelar
                </button>
                <button onClick={doKitchenPrint} disabled={kitchenSelected.size === 0}
                  className="flex-1 py-2.5 rounded-xl text-sm font-semibold
                             bg-amber-500 hover:bg-amber-400 text-stone-900
                             disabled:opacity-40 transition-colors">
                  Imprimir {kitchenSelected.size} {kitchenSelected.size === 1 ? 'item' : 'itens'}
                </button>
              </div>
            </div>
          ) : (
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
                {activeItems.some(i => i.status !== 'served') && (
                  <button onClick={enterKitchenMode}
                    className="flex items-center gap-1.5 px-3 py-2.5 rounded-xl text-sm font-semibold
                               text-stone-300 border border-stone-700/60 hover:bg-stone-800/50 transition-colors">
                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.75}>
                      <path strokeLinecap="round" strokeLinejoin="round"
                        d="M17 17h2a2 2 0 002-2v-4a2 2 0 00-2-2H5a2 2 0 00-2 2v4a2 2 0 002 2h2m2 4h6a1 1 0 001-1v-4a1 1 0 00-1-1H9a1 1 0 00-1 1v4a1 1 0 001 1zm8-12V5a2 2 0 00-2-2H7a2 2 0 00-2 2v4h14z" />
                    </svg>
                    Cozinha
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
                {canSeeMoney && (
                  <button onClick={() => setShowPayment(true)}
                    className="flex-1 py-2.5 rounded-xl text-sm font-semibold
                               bg-amber-500 hover:bg-amber-400 text-stone-900 transition-colors">
                    Receber {brl(remaining > 0 ? remaining : order.total)}
                  </button>
                )}
              </div>
              {!canSeeMoney ? null : showDeleteConfirm ? (
                <div className="flex items-center justify-between gap-2 pt-0.5
                                rounded-xl px-3 py-2 border border-red-500/20 bg-red-500/5">
                  <p className="text-xs text-red-400 font-medium">Apagar esta comanda?</p>
                  <div className="flex gap-2">
                    <button onClick={() => setShowDeleteConfirm(false)}
                      className="text-[11px] text-stone-500 hover:text-stone-300 transition-colors py-1 px-2">
                      Cancelar
                    </button>
                    <button onClick={handleDelete} disabled={deleting}
                      className="text-[11px] font-bold text-red-400 hover:text-red-300
                                 disabled:opacity-40 transition-colors py-1 px-2">
                      {deleting ? 'Apagando…' : 'Sim, apagar'}
                    </button>
                  </div>
                </div>
              ) : (
                <div className="flex flex-wrap items-center gap-2 pt-1">
                  <button onClick={() => setShowDiscount(true)}
                    className="px-3 py-2 rounded-lg text-xs font-semibold border transition-colors
                               text-stone-300 border-stone-700/60 hover:bg-stone-800/50 hover:border-stone-600">
                    {Number(order.discount) > 0 ? `Desconto: ${brl(order.discount)}` : '+ Desconto'}
                  </button>
                  <button
                    onClick={async () => {
                      setTogglingFee(true)
                      try {
                        const updated = await setOrderServiceFee(order.id, Number(order.service_fee_percent) === 0)
                        onUpdated(updated)
                      } catch (err) {
                        setActionError(err instanceof Error ? err.message : 'Erro')
                      } finally {
                        setTogglingFee(false)
                      }
                    }}
                    disabled={togglingFee}
                    className="px-3 py-2 rounded-lg text-xs font-semibold border transition-colors
                               text-stone-300 border-stone-700/60 hover:bg-stone-800/50 hover:border-stone-600
                               disabled:opacity-40">
                    {togglingFee ? '…' : Number(order.service_fee_percent) > 0 ? `− Taxa ${order.service_fee_percent}%` : '+ Taxa de serviço'}
                  </button>
                  <button onClick={() => setShowSplit(true)}
                    className="px-3 py-2 rounded-lg text-xs font-semibold border transition-colors
                               text-amber-400 border-amber-500/30 bg-amber-500/8 hover:bg-amber-500/15">
                    Dividir conta
                  </button>
                  <button onClick={handleClose} disabled={closing}
                    className="px-3 py-2 rounded-lg text-xs font-semibold border transition-colors
                               text-amber-400 border-amber-500/30 bg-amber-500/8 hover:bg-amber-500/15
                               disabled:opacity-40">
                    {closing ? 'Salvando…' : 'Fiado'}
                  </button>
                  <button onClick={() => setShowDeleteConfirm(true)}
                    className="ml-auto px-3 py-2 rounded-lg text-xs font-semibold border transition-colors
                               text-red-400 border-red-500/25 hover:bg-red-500/10">
                    Apagar
                  </button>
                </div>
              )}
            </div>
          )
        )}
      </div>

      {showAddItem && (
        <AddItemModal
          order={order}
          table={table}
          onClose={() => setShowAddItem(false)}
          onAdded={updated => onUpdated(updated)}
        />
      )}

      {showPayment && (
        <PaymentModal
          order={order}
          onClose={() => setShowPayment(false)}
          onFinished={id => { setShowPayment(false); onClosed(id) }}
          onPaidUpdate={setPaidSoFar}
        />
      )}

      {showSplit && (
        <SplitModal
          order={order}
          onClose={() => setShowSplit(false)}
          onFinished={id => { setShowSplit(false); onClosed(id) }}
          onPaidUpdate={setPaidSoFar}
        />
      )}

      {showDiscount && (
        <DiscountModal
          order={order}
          onClose={() => setShowDiscount(false)}
          onUpdated={onUpdated}
        />
      )}
    </div>
  )
}
