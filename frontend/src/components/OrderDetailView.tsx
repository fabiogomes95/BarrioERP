import { useState, useEffect } from 'react'
import {
  type Order, type Table, type Payment, cancelOrder, setOrderServiceFee, closeOrder, requestBill, fetchOrderPayments, updateOrderCustomerName, getUser, requestRemotePrint,
} from '../lib/api'
import { brl, timeAgo } from '../lib/format'
import { ORDER_STATUS } from '../lib/orderStatus'
import { groupForScreen } from '../lib/groupItems'
import { shareReceiptWhatsApp } from '../lib/receiptImage'
import { ModalOverlay } from './ui'
import { closeOrFinish } from './order/closeOrFinish'
import { OrderItemRow, ItemGroupRow } from './order/ItemRows'
import { AddItemModal } from './order/AddItemModal'
import { PaymentModal } from './order/PaymentModal'
import { SplitModal } from './order/SplitModal'
import { DiscountModal } from './order/DiscountModal'

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
  const [showMoreActions, setShowMoreActions] = useState(false)
  const [editingName, setEditingName] = useState(false)
  const [nameInput, setNameInput] = useState('')
  const [savingName, setSavingName] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)
  const [kitchenMode, setKitchenMode] = useState(false)
  const [kitchenSelected, setKitchenSelected] = useState<Set<string>>(new Set())
  const [payments, setPayments] = useState<Payment[]>([])
  const [sharingWA, setSharingWA] = useState(false)
  const [waHint, setWaHint] = useState<string | null>(null)
  const paidSoFar = payments
    .filter(p => p.status === 'confirmed')
    .reduce((sum, p) => sum + Number(p.amount), 0)
  const remaining = Math.max(0, Math.round((Number(order.total) - paidSoFar) * 100) / 100)

  // Carrega pagamentos do servidor ao abrir ou trocar de comanda
  useEffect(() => {
    fetchOrderPayments(order.id)
      .then(setPayments)
      .catch(() => setPayments([]))
  }, [order.id])

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
    const items = activeItems
      .filter(i => kitchenSelected.has(i.id))
      .map(i => ({ name: i.item_name, qty: i.quantity, notes: i.notes }))
    if (items.length === 0) return
    // Direto na térmica pelo servidor — mesmo ticket do pedido online
    requestRemotePrint(order.id, 'cozinha', items)
      .catch(err => setActionError(err instanceof Error ? err.message : 'Erro ao imprimir'))
    exitKitchenMode()
  }

  const cfg = ORDER_STATUS[order.status] ?? ORDER_STATUS.open
  const canEdit = order.status === 'open' || order.status === 'bill_requested'
  const canAddItem = order.status === 'open' || order.status === 'bill_requested'
  const canRequestBill = order.status === 'open'
  const canClose = order.status === 'open' || order.status === 'bill_requested'
  // Garçom/cozinha não veem valores nem mexem em fechamento — só quem atende o caixa.
  const role = getUser()?.role
  const canSeeMoney = role !== 'waiter' && role !== 'kitchen'

  // Ordem do lançamento, sempre — mexer na quantidade não pode mudar a posição
  // (o servidor já manda assim; aqui é só garantia).
  const sortedItems = [...order.items].sort(
    (a, b) => Date.parse(a.created_at) - Date.parse(b.created_at) || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0),
  )
  const activeItems = sortedItems.filter(i => i.status !== 'cancelled')
  const cancelledItems = sortedItems.filter(i => i.status === 'cancelled')
  const hasUnservedItems = activeItems.some(i => i.status !== 'served')

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
    // A térmica está ligada por cabo no PC do servidor: de qualquer aparelho
    // (inclusive o próprio PC), o servidor imprime direto — sem a janela de
    // impressão do Chrome, mesmo layout do ticket do pedido online.
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
      await closeOrFinish(order.id, order.version, closeOrder)
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
      const result = await shareReceiptWhatsApp(order, table, getUser()?.company_name ?? 'Barrio', payments)
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
           style={{ background: 'var(--color-app-surface-2)' }}>
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

          {/* Imprimir recibo — o servidor manda direto pra térmica do bar,
              de qualquer aparelho (ver handlePrint) */}
          <button
            onClick={handlePrint}
            title="Imprimir comanda na impressora do bar"
            className={[
              'shrink-0 flex items-center justify-center w-9 h-9 rounded-xl border transition-all',
              printSent
                ? 'border-green-500/40 text-green-400'
                : 'border-stone-800/60 text-stone-400 hover:text-amber-400 hover:border-stone-700/60',
            ].join(' ')}
            style={{ background: 'var(--color-app-surface)' }}>
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
            style={{ background: 'var(--color-app-surface)' }}>
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
            {/* Escolhendo itens pra cozinha: lista de lançamentos, um por um.
                Fora disso, iguais (nome + preço + observação) viram uma linha
                "12× Churrasco" que abre os lançamentos ao tocar. */}
            {kitchenMode
              ? activeItems.map(item => (
                  <OrderItemRow
                    key={item.id}
                    item={item}
                    canCancel={false}
                    onCancelled={onUpdated}
                    kitchenMode
                    kitchenSelected={kitchenSelected.has(item.id)}
                    onKitchenToggle={() => toggleKitchenItem(item.id)}
                  />
                ))
              : groupForScreen(activeItems).map(g => g.items.length === 1 ? (
                  <OrderItemRow key={g.key} item={g.items[0]} canCancel={canEdit} onCancelled={onUpdated} />
                ) : (
                  <ItemGroupRow key={g.key} group={g} canEdit={canEdit} onUpdated={onUpdated} />
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
           style={{ background: 'var(--color-app-surface-2)' }}>

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
              <span className="text-base font-black" style={{ color: 'var(--color-app-price)' }}>{brl(order.total)}</span>
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
          ) : showDeleteConfirm ? (
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
            // Rodapé enxuto: "+ Item" e "Cozinha" ficam sempre visíveis (só
            // como ícone, pra não pesar) porque são usados o tempo todo —
            // testamos escondê-los atrás do "Mais" e atrapalhou o fluxo real
            // do garçom. O que sobra no "Mais" é só o que é usado bem menos
            // (desconto, taxa, dividir conta, fiado, apagar) — eram 9 botões
            // de texto sempre visíveis, viravam poluição principalmente no
            // celular; isso continua fora do caminho principal.
            <div className="flex gap-2">
              {canAddItem && (
                <button onClick={() => setShowAddItem(true)} title="Adicionar item" aria-label="Adicionar item"
                  className="w-11 shrink-0 flex items-center justify-center rounded-xl text-xl font-bold leading-none
                             text-stone-300 border border-stone-700/60 hover:bg-stone-800/50 transition-colors">
                  +
                </button>
              )}
              {hasUnservedItems && (
                <button onClick={enterKitchenMode} title="Imprimir cozinha" aria-label="Imprimir cozinha"
                  className="w-11 shrink-0 flex items-center justify-center rounded-xl
                             text-stone-300 border border-stone-700/60 hover:bg-stone-800/50 transition-colors">
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.75}>
                    <path strokeLinecap="round" strokeLinejoin="round"
                      d="M17 17h2a2 2 0 002-2v-4a2 2 0 00-2-2H5a2 2 0 00-2 2v4a2 2 0 002 2h2m2 4h6a1 1 0 001-1v-4a1 1 0 00-1-1H9a1 1 0 00-1 1v4a1 1 0 001 1zm8-12V5a2 2 0 00-2-2H7a2 2 0 00-2 2v4h14z" />
                  </svg>
                </button>
              )}
              {canRequestBill && (
                <button onClick={handleRequestBill} disabled={requestingBill}
                  className="py-2.5 px-4 rounded-xl text-sm font-semibold
                             text-orange-400 border border-orange-500/30 bg-orange-500/8
                             hover:bg-orange-500/15 disabled:opacity-40 transition-colors">
                  {requestingBill ? '…' : 'Conta'}
                </button>
              )}
              {canSeeMoney && (
                <button onClick={() => setShowPayment(true)}
                  className="flex-1 py-2.5 rounded-xl text-sm font-semibold
                             bg-amber-500 hover:bg-amber-400 text-stone-900 transition-colors">
                  Receber {brl(remaining > 0 ? remaining : order.total)}
                </button>
              )}
              {canSeeMoney && (
                <button onClick={() => setShowMoreActions(true)} aria-label="Mais opções"
                  className="w-11 shrink-0 rounded-xl text-lg font-bold leading-none
                             text-stone-300 border border-stone-700/60 hover:bg-stone-800/50 transition-colors">
                  ⋯
                </button>
              )}
            </div>
          )
        )}
      </div>

      {/* Sheet "Mais opções" — só o que é usado com pouca frequência (ver
          comentário acima; "+ Item" e "Cozinha" ficaram sempre visíveis). */}
      {showMoreActions && (
        <ModalOverlay title="Mais opções" onClose={() => setShowMoreActions(false)}>
          <div className="flex flex-col -mx-1">
            {canSeeMoney && (
              <>
                <button onClick={() => { setShowMoreActions(false); setShowDiscount(true) }}
                  className="text-left px-3 py-3 rounded-xl text-sm font-medium text-stone-200 hover:bg-stone-800/50 transition-colors">
                  {Number(order.discount) > 0 ? `Desconto: ${brl(order.discount)}` : 'Desconto'}
                </button>
                <button
                  onClick={async () => {
                    setTogglingFee(true)
                    try {
                      const updated = await setOrderServiceFee(order.id, Number(order.service_fee_percent) === 0)
                      onUpdated(updated)
                      setShowMoreActions(false)
                    } catch (err) {
                      setActionError(err instanceof Error ? err.message : 'Erro')
                    } finally {
                      setTogglingFee(false)
                    }
                  }}
                  disabled={togglingFee}
                  className="text-left px-3 py-3 rounded-xl text-sm font-medium text-stone-200 hover:bg-stone-800/50
                             disabled:opacity-40 transition-colors">
                  {togglingFee ? '…' : Number(order.service_fee_percent) > 0 ? `Remover taxa de serviço (${order.service_fee_percent}%)` : 'Taxa de serviço'}
                </button>
                <button onClick={() => { setShowMoreActions(false); setShowSplit(true) }}
                  className="text-left px-3 py-3 rounded-xl text-sm font-medium text-stone-200 hover:bg-stone-800/50 transition-colors">
                  Dividir conta
                </button>
                <button onClick={() => { setShowMoreActions(false); handleClose() }} disabled={closing}
                  className="text-left px-3 py-3 rounded-xl text-sm font-medium text-stone-200 hover:bg-stone-800/50
                             disabled:opacity-40 transition-colors">
                  {closing ? 'Salvando…' : 'Fiado (fechar sem cobrar agora)'}
                </button>
                <div className="border-t border-stone-800/60 my-1.5" />
                <button onClick={() => { setShowMoreActions(false); setShowDeleteConfirm(true) }}
                  className="text-left px-3 py-3 rounded-xl text-sm font-medium text-red-400 hover:bg-red-500/10 transition-colors">
                  Apagar comanda
                </button>
              </>
            )}
          </div>
        </ModalOverlay>
      )}

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
          onPaidUpdate={setPayments}
        />
      )}

      {showSplit && (
        <SplitModal
          order={order}
          onClose={() => setShowSplit(false)}
          onFinished={id => { setShowSplit(false); onClosed(id) }}
          onPaidUpdate={setPayments}
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
