import { useState, useEffect, useCallback, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  type Order, type Table, type OrderType, type OnlineOrder,
  fetchOpenOrders, fetchTables, createOrder, getUser, cancelOrder, mergeOrders,
  fetchOnlineOrders, acceptOnlineOrder, rejectOnlineOrder,
} from '../lib/api'
import { ONLINE_ORDER_EVENT } from '../lib/notifications'
import { brl, timeAgo, ORDER_STATUS } from '../components/OrderDetailView'
import { inputCls, Field, ModalOverlay } from '../components/ui'

const ORDER_TYPE_LABEL: Record<string, string> = {
  counter: 'Balcão',
  delivery: 'Delivery',
  pickup: 'Retirada',
}

// ── Helpers de modal ──────────────────────────────────────────────────────────

// ── Card de comanda (grade) ───────────────────────────────────────────────────

function orderTitle(order: Order, table: Table | undefined) {
  return order.customer_name ?? table?.label ?? 'Comanda avulsa'
}

const LONG_PRESS_MS = 450

function OrderCard({ order, table, selecting, selected, onClick, onLongPress }: {
  order: Order
  table: Table | undefined
  selecting: boolean
  selected: boolean
  onClick: () => void
  onLongPress: () => void
}) {
  const cfg = ORDER_STATUS[order.status] ?? ORDER_STATUS.open
  const activeItems = order.items.filter(i => i.status !== 'cancelled').length
  const title = orderTitle(order, table)

  // Segurar (toque longo ou mouse pressionado) entra no modo de seleção.
  // Se o dedo se mexer (rolando a lista), cancela — senão rolar marcava comanda.
  const timer = useRef<number | null>(null)
  const start = useRef<{ x: number; y: number } | null>(null)
  const fired = useRef(false)
  function cancelPress() {
    if (timer.current !== null) { clearTimeout(timer.current); timer.current = null }
  }
  function onPointerDown(e: React.PointerEvent) {
    if (e.pointerType === 'mouse' && e.button !== 0) return
    fired.current = false
    start.current = { x: e.clientX, y: e.clientY }
    cancelPress()
    timer.current = window.setTimeout(() => {
      fired.current = true
      navigator.vibrate?.(25)
      onLongPress()
    }, LONG_PRESS_MS)
  }
  function onPointerMove(e: React.PointerEvent) {
    if (!start.current) return
    if (Math.abs(e.clientX - start.current.x) > 10 || Math.abs(e.clientY - start.current.y) > 10) cancelPress()
  }

  return (
    <button
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={cancelPress}
      onPointerLeave={cancelPress}
      onPointerCancel={cancelPress}
      onClick={() => {
        // O clique que vem logo depois do "segurar" não abre a comanda
        if (fired.current) { fired.current = false; return }
        onClick()
      }}
      onContextMenu={e => { e.preventDefault(); cancelPress(); fired.current = true; onLongPress() }}
      aria-pressed={selecting ? selected : undefined}
      className={[
        'group w-full text-left rounded-2xl border p-4 select-none',
        'transition-all duration-150 relative overflow-hidden',
        selected
          ? 'border-amber-500/70 ring-2 ring-amber-500/50'
          : 'border-stone-800/50 hover:border-stone-700/70',
        selecting ? '' : 'hover:-translate-y-0.5 hover:shadow-lg hover:shadow-black/40 active:translate-y-0',
      ].join(' ')}
      style={{ background: 'var(--color-app-surface)', WebkitTouchCallout: 'none' }}>

      {selecting && (
        <span className={[
          'absolute top-2.5 right-2.5 w-5 h-5 rounded-full border-2 flex items-center justify-center z-10',
          selected ? 'bg-amber-500 border-amber-500' : 'border-stone-600 bg-stone-900/70',
        ].join(' ')}>
          {selected && (
            <svg className="w-3 h-3 text-stone-900" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
            </svg>
          )}
        </span>
      )}

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
        {!selecting && (
          <span className={[
            'shrink-0 text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full border',
            cfg.color, cfg.bg, cfg.border,
          ].join(' ')}>
            {cfg.label}
          </span>
        )}
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

// ── Seleção múltipla: mesclar / apagar ────────────────────────────────────────

function MergeModal({ orders, tables, onClose, onMerged }: {
  orders: Order[]
  tables: Table[]
  onClose: () => void
  onMerged: (o: Order) => void
}) {
  // Destino padrão: a comanda com mais itens (geralmente a "principal")
  const [targetId, setTargetId] = useState(() =>
    [...orders].sort((a, b) => b.items.length - a.items.length)[0]?.id ?? '')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const total = orders.reduce((s, o) => s + Number(o.subtotal), 0)

  async function confirm() {
    setSaving(true)
    setError(null)
    try {
      const merged = await mergeOrders(targetId, orders.filter(o => o.id !== targetId).map(o => o.id))
      onMerged(merged)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro ao mesclar comandas')
      setSaving(false)
    }
  }

  return (
    <ModalOverlay onClose={onClose}>
      <h2 className="text-stone-100 text-base font-bold mb-1">Mesclar {orders.length} comandas</h2>
      <p className="text-stone-500 text-xs mb-4">
        Os itens vão todos para a comanda escolhida. As outras são encerradas e as mesas delas ficam livres.
      </p>
      <p className="text-stone-400 text-[11px] font-semibold uppercase tracking-wider mb-2">Deixar tudo na comanda:</p>
      <div className="space-y-1.5 mb-4 max-h-72 overflow-auto">
        {orders.map(o => {
          const table = tables.find(t => t.id === o.table_id)
          const n = o.items.filter(i => i.status !== 'cancelled').length
          return (
            <label key={o.id}
              className={[
                'flex items-center gap-3 px-3 py-2.5 rounded-xl border cursor-pointer transition-colors',
                targetId === o.id ? 'border-amber-500/50 bg-amber-500/10' : 'border-stone-800/60 hover:bg-stone-800/40',
              ].join(' ')}>
              <input type="radio" name="merge-target" checked={targetId === o.id}
                onChange={() => setTargetId(o.id)} className="accent-amber-500" />
              <span className="flex-1 min-w-0">
                <span className="block text-stone-100 text-sm font-semibold truncate">{orderTitle(o, table)}</span>
                <span className="block text-stone-500 text-xs">
                  {table ? `Mesa ${table.number} · ` : ''}{n} {n === 1 ? 'item' : 'itens'}
                </span>
              </span>
              <span className="text-amber-400 text-sm font-bold">{brl(o.subtotal)}</span>
            </label>
          )
        })}
      </div>
      <div className="flex justify-between text-sm px-1 mb-4">
        <span className="text-stone-500">Subtotal somado</span>
        <span className="text-stone-100 font-bold">{brl(total)}</span>
      </div>
      {error && (
        <p className="text-red-400 text-xs bg-red-500/10 border border-red-500/20 rounded-xl px-3 py-2.5 mb-3">{error}</p>
      )}
      <div className="flex gap-2">
        <button onClick={onClose}
          className="flex-1 py-2.5 rounded-xl text-sm font-semibold text-stone-400 border border-stone-700/60 hover:bg-stone-800/50">
          Cancelar
        </button>
        <button onClick={confirm} disabled={saving || !targetId}
          className="flex-1 py-2.5 rounded-xl text-sm font-semibold bg-amber-500 hover:bg-amber-400 text-stone-900 disabled:opacity-40">
          {saving ? 'Mesclando…' : 'Mesclar'}
        </button>
      </div>
    </ModalOverlay>
  )
}

function DeleteManyModal({ orders, tables, onClose, onDone }: {
  orders: Order[]
  tables: Table[]
  onClose: () => void
  onDone: () => void
}) {
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function confirm() {
    setSaving(true)
    setError(null)
    // Uma por vez: se uma falhar, as já apagadas continuam apagadas e a
    // mensagem diz qual travou (em vez de um erro genérico)
    for (const o of orders) {
      try {
        await cancelOrder(o.id)
      } catch (err) {
        setError(`${orderTitle(o, tables.find(t => t.id === o.table_id))}: ${err instanceof Error ? err.message : 'erro'}`)
        setSaving(false)
        return
      }
    }
    onDone()
  }

  return (
    <ModalOverlay onClose={onClose}>
      <h2 className="text-stone-100 text-base font-bold mb-1">Apagar {orders.length} comandas?</h2>
      <p className="text-stone-500 text-xs mb-4">Não dá para desfazer. As mesas ficam livres.</p>
      <ul className="space-y-1 mb-4 max-h-60 overflow-auto">
        {orders.map(o => (
          <li key={o.id} className="flex justify-between text-sm px-3 py-2 rounded-lg" style={{ background: 'var(--color-app-bg)' }}>
            <span className="text-stone-200 truncate">{orderTitle(o, tables.find(t => t.id === o.table_id))}</span>
            <span className="text-stone-400 shrink-0 ml-2">{brl(o.total)}</span>
          </li>
        ))}
      </ul>
      {error && (
        <p className="text-red-400 text-xs bg-red-500/10 border border-red-500/20 rounded-xl px-3 py-2.5 mb-3">{error}</p>
      )}
      <div className="flex gap-2">
        <button onClick={onClose}
          className="flex-1 py-2.5 rounded-xl text-sm font-semibold text-stone-400 border border-stone-700/60 hover:bg-stone-800/50">
          Voltar
        </button>
        <button onClick={confirm} disabled={saving}
          className="flex-1 py-2.5 rounded-xl text-sm font-semibold bg-red-500/90 hover:bg-red-500 text-white disabled:opacity-40">
          {saving ? 'Apagando…' : `Apagar ${orders.length}`}
        </button>
      </div>
    </ModalOverlay>
  )
}

// ── Pedidos online (cardápio público → aceite) ────────────────────────────────

function formatPhone(digits: string) {
  const d = digits.length > 11 && digits.startsWith('55') ? digits.slice(2) : digits
  return d.length < 10 ? d : `(${d.slice(0, 2)}) ${d.slice(2, -4)}-${d.slice(-4)}`
}

const PAYMENT_LABEL = { cash: 'Dinheiro', pix: 'Pix', credit: 'Crédito', debit: 'Débito' } as const

function OnlineOrderCard({ oo, onAccept, onReject }: {
  oo: OnlineOrder
  onAccept: () => Promise<void>
  onReject: () => Promise<void>
}) {
  const [busy, setBusy] = useState<'accept' | 'reject' | null>(null)
  const [confirmReject, setConfirmReject] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const phone = formatPhone(oo.customer_phone)

  async function run(kind: 'accept' | 'reject', fn: () => Promise<void>) {
    setBusy(kind)
    setError(null)
    try {
      await fn()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro')
      setBusy(null)
    }
  }

  return (
    <div className="rounded-2xl border border-emerald-500/30 p-4 flex flex-col"
         style={{ background: 'var(--color-app-surface)' }}>
      <div className="flex items-start justify-between gap-2 mb-2">
        <div className="min-w-0">
          <p className="text-stone-100 text-sm font-semibold leading-tight truncate">
            #{oo.number} · {oo.customer_name}
          </p>
          <p className="text-stone-500 text-xs mt-0.5">
            <a href={whatsLink(oo.customer_phone)}
               className="text-emerald-400 hover:underline">{phone}</a>
            {' · '}{timeAgo(oo.created_at)}
          </p>
        </div>
        <span className="shrink-0 text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full border
                         text-emerald-400 bg-emerald-500/10 border-emerald-500/30">
          {oo.fulfillment === 'delivery' ? '🛵 Entrega' : '📦 Retirada'}
        </span>
      </div>

      <ul className="text-xs text-stone-300 space-y-1 py-2 border-t border-stone-800/50">
        {oo.items.map((it, i) => (
          <li key={i} className="flex justify-between gap-2">
            <span className="min-w-0"><b className="text-stone-100">{it.quantity}x</b> {it.item_name}</span>
            <span className="text-stone-500 shrink-0">{brl(String(Number(it.unit_price) * it.quantity))}</span>
          </li>
        ))}
      </ul>
      {oo.payment_method && (
        <p className="text-xs text-stone-200 bg-stone-800/60 rounded-lg px-2.5 py-1.5 mb-2">
          💳 Pagamento: <b>{PAYMENT_LABEL[oo.payment_method]}</b>
          {oo.payment_method === 'cash' && oo.change_for && ` · troco p/ ${brl(oo.change_for)}`}
          {oo.payment_method === 'pix' && ' · mandar a chave no WhatsApp'}
        </p>
      )}
      {oo.delivery_location && (
        <p className="text-xs text-stone-200 bg-emerald-500/10 rounded-lg px-2.5 py-1.5 mb-2">📍 Entregar em: {oo.delivery_location}</p>
      )}
      {oo.notes && (
        <p className="text-xs text-stone-200 bg-amber-500/10 rounded-lg px-2.5 py-1.5 mb-2">Obs: {oo.notes}</p>
      )}

      <div className="flex items-center justify-between pt-2.5 border-t border-stone-800/50 mt-auto">
        <span className="text-amber-400 text-sm font-bold">{brl(oo.total)}</span>
        <div className="flex gap-2">
          {confirmReject ? (
            <>
              <button onClick={() => setConfirmReject(false)} disabled={busy !== null}
                className="px-3 py-1.5 rounded-lg text-xs font-semibold text-stone-400 border border-stone-700/60">
                Voltar
              </button>
              <button onClick={() => run('reject', onReject)} disabled={busy !== null}
                className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-red-500/90 hover:bg-red-500 text-white disabled:opacity-40">
                {busy === 'reject' ? 'Recusando…' : 'Confirmar recusa'}
              </button>
            </>
          ) : (
            <>
              <button onClick={() => setConfirmReject(true)} disabled={busy !== null}
                className="px-3 py-1.5 rounded-lg text-xs font-semibold text-stone-400 border border-stone-700/60
                           hover:text-red-400 hover:border-red-500/40 disabled:opacity-40">
                Recusar
              </button>
              <button onClick={() => run('accept', onAccept)} disabled={busy !== null}
                className="px-3.5 py-1.5 rounded-lg text-xs font-bold bg-emerald-500 hover:bg-emerald-400 text-stone-900 disabled:opacity-40">
                {busy === 'accept' ? 'Aceitando…' : 'Aceitar'}
              </button>
            </>
          )}
        </div>
      </div>
      {error && <p className="text-red-400 text-xs mt-2">{error}</p>}
    </div>
  )
}

/**
 * Abre a conversa com o cliente direto no app do WhatsApp (Desktop no PC,
 * app no celular) — whatsapp:// pula a página intermediária do navegador que
 * o wa.me abre no computador. Telefone só com dígitos, com ou sem 55.
 */
function whatsLink(phone: string, text?: string) {
  const digits = phone.length <= 11 ? `55${phone}` : phone
  return `whatsapp://send?phone=${digits}${text ? `&text=${encodeURIComponent(text)}` : ''}`
}

// Sem emoji de propósito: o WhatsApp Desktop do Windows estraga emoji vindo
// em link wa.me (vira "�") — e esse botão é usado justamente no PC do caixa.
function acceptedMessage(oo: OnlineOrder) {
  const first = oo.customer_name.split(' ')[0]
  const next = oo.fulfillment === 'delivery'
    ? 'Já estamos preparando e logo sai pra entrega.'
    : 'Já estamos preparando, te avisamos quando estiver pronto pra retirar.'
  return `Oi ${first}! Seu pedido #${oo.number} foi aceito. ${next}`
}

function OnlineOrdersPanel({ onAccepted }: { onAccepted: () => void }) {
  const [pending, setPending] = useState<OnlineOrder[]>([])
  // Último aceito: oferece (sem obrigar) avisar o cliente no WhatsApp
  const [lastAccepted, setLastAccepted] = useState<OnlineOrder | null>(null)

  const load = useCallback(() => {
    fetchOnlineOrders().then(setPending).catch(() => {})
  }, [])

  useEffect(() => {
    load()
    // Chega na hora pelo SSE (Layout → notifications.ts); o intervalo cobre
    // reconexão perdida
    window.addEventListener(ONLINE_ORDER_EVENT, load)
    const id = setInterval(load, 30_000)
    return () => { window.removeEventListener(ONLINE_ORDER_EVENT, load); clearInterval(id) }
  }, [load])

  if (pending.length === 0 && !lastAccepted) return null

  return (
    <section className="mb-5">
      {lastAccepted && (
        <div className="flex items-center gap-3 rounded-xl border border-emerald-500/30 bg-emerald-500/10 px-3.5 py-2.5 mb-3">
          <p className="flex-1 min-w-0 text-sm text-stone-200 truncate">
            <span className="text-emerald-400 font-semibold">Pedido #{lastAccepted.number} aceito</span>
            {' · '}{lastAccepted.customer_name}
          </p>
          <a href={whatsLink(lastAccepted.customer_phone, acceptedMessage(lastAccepted))}
             onClick={() => setLastAccepted(null)}
             className="shrink-0 px-3 py-1.5 rounded-lg text-xs font-bold bg-emerald-500 hover:bg-emerald-400 text-stone-900">
            Avisar no WhatsApp
          </a>
          <button onClick={() => setLastAccepted(null)} aria-label="Dispensar"
            className="shrink-0 text-stone-500 hover:text-stone-300">
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
      )}

      {pending.length > 0 && (<>
      <h2 className="flex items-center gap-2 text-stone-200 text-sm font-bold mb-2.5">
        <span className="relative flex w-2.5 h-2.5">
          <span className="absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75 animate-ping" />
          <span className="relative inline-flex rounded-full w-2.5 h-2.5 bg-emerald-500" />
        </span>
        Pedidos online aguardando
        <span className="text-stone-500 font-medium">({pending.length})</span>
      </h2>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
        {pending.map(oo => (
          <OnlineOrderCard
            key={oo.id}
            oo={oo}
            onAccept={async () => {
              // Fica na tela de Pedidos: a comanda nova aparece na lista e
              // abre só se alguém tocar nela
              await acceptOnlineOrder(oo.id)
              setPending(prev => prev.filter(p => p.id !== oo.id))
              setLastAccepted(oo)
              onAccepted()
            }}
            onReject={async () => {
              await rejectOnlineOrder(oo.id)
              setPending(prev => prev.filter(p => p.id !== oo.id))
            }}
          />
        ))}
      </div>
      </>)}
    </section>
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
                className={inputCls + ' appearance-none'} style={{ background: 'var(--color-app-bg)' }}>
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
                  className={inputCls} style={{ background: 'var(--color-app-bg)' }} />
              </Field>
              <div />
            </div>
          )}
          <Field label="Cliente (opcional)">
            <input type="text" value={customerName} onChange={e => setCustomerName(e.target.value)}
              placeholder="Deixe vazio para numerar automaticamente"
              className={inputCls} style={{ background: 'var(--color-app-bg)' }} />
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
  // Mesmos papéis da API /online-orders (quem cuida de caixa/telefone)
  const role = getUser()?.role
  const canHandleOnline = role === 'owner' || role === 'manager' || role === 'cashier'
  // Mesmas permissões do backend: mesclar = owner/manager/cashier, apagar = owner/manager
  const canMerge = canHandleOnline
  const canDelete = role === 'owner' || role === 'manager'

  // Seleção múltipla (segurar uma comanda entra no modo)
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [showMerge, setShowMerge] = useState(false)
  const [showDeleteMany, setShowDeleteMany] = useState(false)
  const selectedOrders = orders.filter(o => selected.has(o.id))  // ignora as que sumiram no refresh
  const selecting = selectedOrders.length > 0 && (canMerge || canDelete)

  function addToSelection(id: string) {
    setSelected(prev => new Set(prev).add(id))
  }
  function toggleSelection(id: string) {
    setSelected(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id); else next.add(id)
      return next
    })
  }
  function clearSelection() { setSelected(new Set()) }

  useEffect(() => {
    if (!selecting) return
    const h = (e: KeyboardEvent) => { if (e.key === 'Escape') clearSelection() }
    document.addEventListener('keydown', h)
    return () => document.removeEventListener('keydown', h)
  }, [selecting])

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
           style={{ background: 'var(--color-app-surface-2)' }}>
        {selecting ? (
          <div className="flex items-center justify-between gap-3 mb-4 min-h-[42px]">
            <div className="flex items-center gap-2 min-w-0">
              <button onClick={clearSelection} aria-label="Cancelar seleção"
                className="w-9 h-9 shrink-0 flex items-center justify-center rounded-xl border border-stone-800/60
                           text-stone-400 hover:text-stone-200" style={{ background: 'var(--color-app-surface)' }}>
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
              <p className="text-stone-100 text-sm font-bold truncate">
                {selectedOrders.length} {selectedOrders.length === 1 ? 'selecionada' : 'selecionadas'}
              </p>
            </div>
            <div className="flex items-center gap-2 shrink-0">
              {canMerge && (
                <button onClick={() => setShowMerge(true)} disabled={selectedOrders.length < 2}
                  title={selectedOrders.length < 2 ? 'Selecione pelo menos 2 comandas' : undefined}
                  className="px-3.5 py-2 rounded-xl text-sm font-semibold bg-amber-500 hover:bg-amber-400 text-stone-900
                             disabled:opacity-40 transition-colors">
                  Mesclar
                </button>
              )}
              {canDelete && (
                <button onClick={() => setShowDeleteMany(true)}
                  className="px-3.5 py-2 rounded-xl text-sm font-semibold text-red-400 border border-red-500/30
                             hover:bg-red-500/10 transition-colors">
                  Apagar
                </button>
              )}
            </div>
          </div>
        ) : (
        <div className="flex items-start justify-between gap-4 mb-4">
          <div>
            <h1 className="text-stone-100 text-lg font-bold leading-tight">Pedidos</h1>
            {!loading && (
              <p className="text-stone-500 text-xs mt-0.5">
                {orders.length} {orders.length === 1 ? 'comanda aberta' : 'comandas abertas'}
                {orders.length > 1 && (canMerge || canDelete) && ' · segure uma para selecionar'}
              </p>
            )}
          </div>
          <div className="flex items-center gap-2">
            <button onClick={load} disabled={loading}
              className="flex items-center justify-center w-9 h-9 rounded-xl
                         border border-stone-800/60 text-stone-500 hover:text-stone-300
                         hover:border-stone-700/60 disabled:opacity-40 transition-all"
              style={{ background: 'var(--color-app-surface)' }} title="Atualizar">
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
        )}

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
            style={{ background: 'var(--color-app-surface)' }} />
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
        {canHandleOnline && <OnlineOrdersPanel onAccepted={load} />}

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
                   style={{ background: 'var(--color-app-surface)' }}>
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
                selecting={selecting}
                selected={selected.has(order.id)}
                onClick={() => selecting ? toggleSelection(order.id) : navigate(`/comanda/${order.id}`)}
                onLongPress={() => { if (canMerge || canDelete) addToSelection(order.id) }}
              />
            ))}
          </div>
        )}
      </div>

      {showMerge && (
        <MergeModal
          orders={selectedOrders}
          tables={tables}
          onClose={() => setShowMerge(false)}
          onMerged={merged => { setShowMerge(false); clearSelection(); navigate(`/comanda/${merged.id}`) }}
        />
      )}

      {showDeleteMany && (
        <DeleteManyModal
          orders={selectedOrders}
          tables={tables}
          onClose={() => { setShowDeleteMany(false); load() }}
          onDone={() => { setShowDeleteMany(false); clearSelection(); load() }}
        />
      )}

      {showNewOrder && (
        <NewOrderModal
          onClose={() => setShowNewOrder(false)}
          onCreated={order => { setShowNewOrder(false); navigate(`/comanda/${order.id}`) }}
        />
      )}
    </div>
  )
}
