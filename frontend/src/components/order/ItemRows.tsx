import { useState } from 'react'
import {
  type Order, type OrderItem, cancelOrderItem, setItemQuantity, serveOrderItem, getUser,
} from '../../lib/api'
import { brl, itemTime } from '../../lib/format'
import { type ItemGroup } from '../../lib/groupItems'

// ── Linha de item da comanda ──────────────────────────────────────────────────

export function OrderItemRow({
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
  const [serving, setServing] = useState(false)

  const isCancelled = item.status === 'cancelled'
  const editable = canCancel && !isCancelled && item.status !== 'served'
  // Garçom/cozinha só cancelam (ou diminuem) item ainda pendente; depois que
  // foi pra cozinha, só caixa/gerente/dono — mesma regra do servidor.
  const role = getUser()?.role
  const canReduce = editable && (item.status === 'pending' || role === 'owner' || role === 'manager' || role === 'cashier')
  const canServe = canCancel && (item.status === 'ready' || item.status === 'pending')
  // Motivo do cancelamento: opcional só pro dono (mesma regra do servidor)
  const reasonOptional = role === 'owner'
  const reasonOk = reasonOptional || reason.trim().length >= 3

  // Erro de qualquer ação da linha (quantidade, servir, cancelar) — antes só o
  // cancelar mostrava; quantidade/servir falhavam em silêncio.
  const [rowError, setRowError] = useState<string | null>(null)

  function showError(err: unknown, fallback: string) {
    setRowError(err instanceof Error ? err.message : fallback)
  }

  async function handleServe() {
    if (serving) return
    setServing(true)
    setRowError(null)
    try {
      const updated = await serveOrderItem(item.order_id, item.id)
      onCancelled(updated)
    } catch (err) {
      showError(err, 'Não deu pra marcar como servido.')
    } finally {
      setServing(false)
    }
  }

  async function changeQty(delta: number) {
    const next = item.quantity + delta
    if (next < 1 || next > 99 || qtyLoading) return
    setQtyLoading(true)
    setRowError(null)
    try {
      const updated = await setItemQuantity(item.order_id, item.id, next)
      onCancelled(updated)
    } catch (err) {
      showError(err, 'Não deu pra mudar a quantidade.')
    } finally {
      setQtyLoading(false)
    }
  }

  async function confirmCancel() {
    if (!reasonOk || loading) return
    setLoading(true)
    setRowError(null)
    try {
      const updated = await cancelOrderItem(item.order_id, item.id, reason.trim())
      onCancelled(updated)
      setCancelling(false)
      setReason('')
    } catch (err) {
      showError(err, 'Não deu pra cancelar o item.')
    } finally {
      setLoading(false)
    }
  }

  const status = ITEM_STATUS[item.status]
  const showActions = !kitchenMode && !isCancelled && (editable || canServe)

  return (
    <div className={['px-4 py-3.5 border-b border-stone-800/40', isCancelled ? 'opacity-50' : ''].join(' ')}>
      {/* Linha 1: nome + valor da linha (ou seleção da cozinha) */}
      <div className="flex items-start gap-3">
        <div className="flex-1 min-w-0">
          <p className={['text-[15px] font-semibold leading-snug break-words',
            isCancelled ? 'line-through text-stone-500' : 'text-stone-100'].join(' ')}>
            {!editable && <span className="text-amber-400 tabular-nums">{item.quantity}× </span>}
            {item.item_name}
          </p>
          {/* Linha 2: preço unitário · horário · situação */}
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1 mt-1 text-xs text-stone-500 tabular-nums">
            {item.quantity > 1 && <span>{item.quantity} × {brl(item.unit_price)}</span>}
            {item.quantity > 1 && <span aria-hidden>·</span>}
            <span>{itemTime(item)}</span>
            {status && (
              <span className={['inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-semibold border',
                status.cls].join(' ')}>
                <span className="w-1.5 h-1.5 rounded-full bg-current" aria-hidden />
                {status.label}
              </span>
            )}
          </div>
          {item.notes && (
            <p className="text-stone-400 text-[13px] mt-1.5 italic break-words">Obs.: {item.notes}</p>
          )}
          {isCancelled && item.cancelled_reason && (
            <p className="text-stone-500 text-xs mt-1">Motivo: {item.cancelled_reason}</p>
          )}
        </div>

        <div className="flex items-center gap-2 shrink-0">
          <span className={['text-[15px] font-bold tabular-nums', isCancelled ? 'text-stone-600' : 'text-stone-200'].join(' ')}>
            {brl(item.subtotal)}
          </span>
          {kitchenMode && !isCancelled && (
            <button onClick={onKitchenToggle} aria-pressed={!!kitchenSelected}
              aria-label={kitchenSelected ? `Tirar ${item.item_name} da cozinha` : `Mandar ${item.item_name} pra cozinha`}
              className={[
                'w-10 h-10 rounded-full border-2 flex items-center justify-center transition-colors',
                kitchenSelected
                  ? 'bg-amber-500 border-amber-500 text-stone-900'
                  : 'border-stone-600 text-transparent hover:border-amber-500/60',
              ].join(' ')}>
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
              </svg>
            </button>
          )}
        </div>
      </div>

      {/* Linha 3: ações — botões de 40px, quantidade à esquerda e cancelar
          bem longe dela (antes ficavam colados e pequenos: tocava errado). */}
      {showActions && !cancelling && (
        <div className="flex items-center gap-2 mt-3">
          {editable && (
            <div className="flex items-center rounded-xl border border-stone-700/70 overflow-hidden">
              <button onClick={() => changeQty(-1)} disabled={qtyLoading || item.quantity <= 1 || !canReduce}
                aria-label={`Diminuir ${item.item_name}`}
                className="w-10 h-10 flex items-center justify-center text-stone-200
                           hover:bg-stone-800/70 active:bg-stone-700/70 disabled:opacity-30 transition-colors">
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                  <path strokeLinecap="round" d="M5 12h14" />
                </svg>
              </button>
              <span className={['min-w-9 text-center text-base font-bold tabular-nums text-stone-100',
                qtyLoading ? 'opacity-40' : ''].join(' ')} aria-live="polite">
                {item.quantity}
              </span>
              <button onClick={() => changeQty(1)} disabled={qtyLoading || item.quantity >= 99}
                aria-label={`Aumentar ${item.item_name}`}
                className="w-10 h-10 flex items-center justify-center text-stone-200
                           hover:bg-stone-800/70 active:bg-stone-700/70 disabled:opacity-30 transition-colors">
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                  <path strokeLinecap="round" d="M12 5v14M5 12h14" />
                </svg>
              </button>
            </div>
          )}

          <div className="flex-1" />

          {canServe && (
            <button onClick={handleServe} disabled={serving}
              className="h-10 px-3.5 inline-flex items-center gap-1.5 rounded-xl text-sm font-semibold
                         text-green-400 border border-green-500/30 hover:bg-green-500/10
                         active:bg-green-500/20 disabled:opacity-40 transition-colors">
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
              </svg>
              {serving ? 'Salvando…' : 'Servido'}
            </button>
          )}
          {canReduce && (
            <button onClick={() => { setCancelling(true); setRowError(null) }}
              aria-label={`Cancelar ${item.item_name}`} title="Cancelar item"
              className="h-10 w-10 inline-flex items-center justify-center rounded-xl
                         text-stone-500 border border-stone-700/60 hover:text-red-400 hover:border-red-500/40
                         hover:bg-red-500/10 active:bg-red-500/20 transition-colors">
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round"
                  d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
              </svg>
            </button>
          )}
        </div>
      )}

      {/* Cancelar: motivo obrigatório */}
      {cancelling && (
        <div className="mt-3 space-y-2">
          <input
            type="text" value={reason} onChange={e => setReason(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') confirmCancel() }}
            placeholder={reasonOptional ? 'Motivo do cancelamento (opcional)' : 'Motivo do cancelamento (obrigatório)'}
            maxLength={300} autoFocus
            className="w-full h-11 rounded-xl px-3.5 text-sm border border-stone-700/70
                       text-stone-100 placeholder-stone-600 bg-stone-900/60
                       focus:outline-none focus:border-red-500/50"
          />
          <div className="flex gap-2">
            <button onClick={() => { setCancelling(false); setReason(''); setRowError(null) }}
              className="flex-1 h-10 rounded-xl text-sm font-semibold text-stone-400 border border-stone-700/60
                         hover:bg-stone-800/60 transition-colors">
              Voltar
            </button>
            <button onClick={confirmCancel} disabled={loading || !reasonOk}
              className="flex-1 h-10 rounded-xl text-sm font-bold
                         bg-red-500/15 text-red-400 border border-red-500/30
                         hover:bg-red-500/25 disabled:opacity-40 transition-colors">
              {loading ? 'Cancelando…' : 'Cancelar item'}
            </button>
          </div>
        </div>
      )}

      {rowError && (
        <p role="alert" className="mt-2 text-red-400 text-xs bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2">
          {rowError}
        </p>
      )}
    </div>
  )
}

// Selo da situação do item. Pendente não tem selo (bebida nem passa pela
// cozinha); servido aparece discreto.
// ── Grupo de lançamentos iguais ("12× Churrasco · 2 lançamentos") ──────────────

const STATUS_PLURAL: Record<string, [string, string]> = {
  pending: ['a servir', 'a servir'],
  sent: ['na cozinha', 'na cozinha'],
  preparing: ['preparando', 'preparando'],
  ready: ['pronto', 'prontos'],
  served: ['servido', 'servidos'],
}

export function ItemGroupRow({ group, canEdit, onUpdated }: {
  group: ItemGroup
  canEdit: boolean
  onUpdated: (updated: Order) => void
}) {
  const [open, setOpen] = useState(false)

  // Resumo da situação somando as quantidades: "5 servidos · 7 preparando"
  const byStatus = new Map<string, number>()
  for (const it of group.items) byStatus.set(it.status, (byStatus.get(it.status) ?? 0) + it.quantity)
  const summary = [...byStatus].map(([st, qty]) => {
    const [one, many] = STATUS_PLURAL[st] ?? [st, st]
    return `${qty} ${qty === 1 ? one : many}`
  }).join(' · ')
  const single = byStatus.size === 1 ? ITEM_STATUS[group.items[0].status] : undefined

  return (
    <div className="border-b border-stone-800/40">
      <button type="button" onClick={() => setOpen(v => !v)} aria-expanded={open}
        className="w-full text-left px-4 py-3.5 flex items-start gap-3 hover:bg-stone-800/30 active:bg-stone-800/50 transition-colors">
        <div className="flex-1 min-w-0">
          <p className="text-stone-100 text-[15px] font-semibold leading-snug break-words">
            <span className="text-amber-400 tabular-nums">{group.quantity}× </span>{group.item_name}
          </p>
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1 mt-1 text-xs text-stone-500 tabular-nums">
            <span>{group.quantity} × {brl(group.unit_price)}</span>
            <span aria-hidden>·</span>
            <span>{group.items.length} lançamentos</span>
            {single ? (
              <span className={['inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-semibold border',
                single.cls].join(' ')}>
                <span className="w-1.5 h-1.5 rounded-full bg-current" aria-hidden />{single.label}
              </span>
            ) : (
              <span className="text-stone-400">{summary}</span>
            )}
          </div>
          {group.notes && (
            <p className="text-stone-400 text-[13px] mt-1.5 italic break-words">Obs.: {group.notes}</p>
          )}
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <span className="text-stone-200 text-[15px] font-bold tabular-nums">{brl(group.subtotal)}</span>
          <svg className={['w-5 h-5 text-stone-500 transition-transform', open ? 'rotate-180' : ''].join(' ')}
            fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} aria-hidden>
            <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
          </svg>
        </div>
      </button>
      {open && (
        <div className="ml-4 border-l-2 border-amber-500/30 bg-stone-900/20">
          {group.items.map(it => (
            <OrderItemRow key={it.id} item={it} canCancel={canEdit} onCancelled={onUpdated} />
          ))}
        </div>
      )}
    </div>
  )
}

const ITEM_STATUS: Partial<Record<OrderItem['status'], { label: string; cls: string }>> = {
  sent:      { label: 'Na cozinha', cls: 'text-blue-400 border-blue-500/30 bg-blue-500/10' },
  preparing: { label: 'Preparando', cls: 'text-amber-400 border-amber-500/30 bg-amber-500/10' },
  ready:     { label: 'Pronto',     cls: 'text-green-400 border-green-500/30 bg-green-500/10' },
  served:    { label: 'Servido',    cls: 'text-stone-500 border-stone-700/60 bg-transparent' },
}
