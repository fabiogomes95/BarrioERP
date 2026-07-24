import { useState, useEffect, useCallback } from 'react'
import {
  type StockItem, type StockUnit, type StockMovement, type StockMovementKind,
  fetchStockItems, createStockItem, updateStockItem, deleteStockItem,
  createStockMovement, fetchStockMovements,
} from '../lib/api'
import { inputCls, Field, ModalOverlay, ErrorBanner, Spinner } from '../components/ui'

const UNIT_LABEL: Record<StockUnit, string> = {
  unit: 'un', kg: 'kg', g: 'g', l: 'L', ml: 'ml',
}

const MOVEMENT_LABEL: Record<StockMovementKind, string> = {
  purchase: 'Compra', adjustment: 'Ajuste', sale: 'Venda', loss: 'Perda',
}

function fmtQty(value: string): string {
  const n = Number(value)
  // Sem casas decimais desnecessárias: 100.000 → 100, 12.500 → 12,5
  return n.toLocaleString('pt-BR', { maximumFractionDigits: 3 })
}

function timeOf(iso: string): string {
  return new Date(iso).toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })
}

// ── Modal: Novo/Editar insumo ────────────────────────────────────────────────

function StockItemModal({ item, onClose, onSaved }: {
  item: StockItem | null
  onClose: () => void
  onSaved: (item: StockItem) => void
}) {
  const editing = item !== null
  const [name, setName] = useState(item?.name ?? '')
  const [unit, setUnit] = useState<StockUnit>(item?.unit ?? 'unit')
  const [quantityOnHand, setQuantityOnHand] = useState(item?.quantity_on_hand ?? '0')
  const [minQuantity, setMinQuantity] = useState(item?.min_quantity ?? '0')
  const [notes, setNotes] = useState(item?.notes ?? '')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      if (editing) {
        const updated = await updateStockItem(item.id, {
          name: name.trim(), unit, min_quantity: Number(minQuantity), notes: notes.trim() || null,
        })
        onSaved(updated)
      } else {
        const created = await createStockItem({
          name: name.trim(), unit, quantity_on_hand: Number(quantityOnHand),
          min_quantity: Number(minQuantity), notes: notes.trim() || null,
        })
        onSaved(created)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro ao salvar insumo')
    } finally {
      setLoading(false)
    }
  }

  return (
    <ModalOverlay onClose={onClose}>
      <h2 className="text-stone-100 text-base font-bold mb-5">{editing ? 'Editar insumo' : 'Novo insumo'}</h2>

      {error && <ErrorBanner message={error} />}

      <form onSubmit={handleSubmit} className="space-y-3.5">
        <Field label="Nome">
          <input type="text" required value={name} onChange={e => setName(e.target.value)}
            placeholder="ex: Carne bovina, Coca-Cola 350ml" className={inputCls} autoFocus />
        </Field>

        <div className="grid grid-cols-2 gap-3">
          <Field label="Unidade">
            <select value={unit} onChange={e => setUnit(e.target.value as StockUnit)} className={inputCls}>
              {(Object.keys(UNIT_LABEL) as StockUnit[]).map(u => (
                <option key={u} value={u}>{UNIT_LABEL[u]}</option>
              ))}
            </select>
          </Field>
          {!editing && (
            <Field label="Quantidade inicial">
              <input type="number" min={0} step="0.001" value={quantityOnHand}
                onChange={e => setQuantityOnHand(e.target.value)} className={inputCls} />
            </Field>
          )}
        </div>

        <Field label="Estoque mínimo" hint="Abaixo disso o insumo aparece como estoque baixo">
          <input type="number" min={0} step="0.001" value={minQuantity}
            onChange={e => setMinQuantity(e.target.value)} className={inputCls} />
        </Field>

        <Field label="Observações (opcional)">
          <input type="text" value={notes} onChange={e => setNotes(e.target.value)}
            placeholder="…" className={inputCls} />
        </Field>

        <div className="flex gap-2 pt-1">
          <button type="button" onClick={onClose}
            className="flex-1 py-2.5 rounded-xl text-sm font-semibold text-stone-400
                       border border-stone-700/60 hover:bg-stone-800/50 transition-colors">
            Cancelar
          </button>
          <button type="submit" disabled={loading}
            className="flex-1 py-2.5 rounded-xl text-sm font-semibold bg-amber-500 hover:bg-amber-400
                       text-stone-900 disabled:opacity-40 transition-colors">
            {loading ? 'Salvando…' : editing ? 'Salvar' : 'Criar insumo'}
          </button>
        </div>
      </form>
    </ModalOverlay>
  )
}

// ── Modal: Movimentação manual ───────────────────────────────────────────────

function MovementModal({ item, onClose, onSaved }: {
  item: StockItem
  onClose: () => void
  onSaved: () => void
}) {
  const [kind, setKind] = useState<'purchase' | 'adjustment' | 'loss'>('purchase')
  const [isNegativeAdjustment, setIsNegativeAdjustment] = useState(false)
  const [quantity, setQuantity] = useState('')
  const [reason, setReason] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      await createStockMovement(item.id, {
        kind, quantity: Number(quantity),
        is_negative_adjustment: kind === 'adjustment' ? isNegativeAdjustment : undefined,
        reason: reason.trim() || null,
      })
      onSaved()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro ao registrar movimentação')
    } finally {
      setLoading(false)
    }
  }

  return (
    <ModalOverlay onClose={onClose}>
      <h2 className="text-stone-100 text-base font-bold leading-tight">{item.name}</h2>
      <p className="text-stone-500 text-xs mt-0.5 mb-5">
        Em estoque: {fmtQty(item.quantity_on_hand)} {UNIT_LABEL[item.unit]}
      </p>

      {error && <ErrorBanner message={error} />}

      <form onSubmit={handleSubmit} className="space-y-3.5">
        <div className="flex gap-1 p-1 rounded-xl" style={{ background: 'var(--color-app-bg)' }}>
          {(['purchase', 'adjustment', 'loss'] as const).map(k => (
            <button key={k} type="button" onClick={() => setKind(k)}
              className={[
                'flex-1 py-2 rounded-lg text-xs font-semibold transition-all',
                kind === k ? 'bg-amber-500/15 text-amber-400' : 'text-stone-500 hover:text-stone-300',
              ].join(' ')}>
              {MOVEMENT_LABEL[k]}
            </button>
          ))}
        </div>

        {kind === 'adjustment' && (
          <div className="flex gap-1 p-1 rounded-xl" style={{ background: 'var(--color-app-bg)' }}>
            <button type="button" onClick={() => setIsNegativeAdjustment(false)}
              className={[
                'flex-1 py-1.5 rounded-lg text-xs font-semibold transition-all',
                !isNegativeAdjustment ? 'bg-green-500/15 text-green-400' : 'text-stone-500 hover:text-stone-300',
              ].join(' ')}>
              + Somar
            </button>
            <button type="button" onClick={() => setIsNegativeAdjustment(true)}
              className={[
                'flex-1 py-1.5 rounded-lg text-xs font-semibold transition-all',
                isNegativeAdjustment ? 'bg-red-500/15 text-red-400' : 'text-stone-500 hover:text-stone-300',
              ].join(' ')}>
              − Subtrair
            </button>
          </div>
        )}

        <Field label={`Quantidade (${UNIT_LABEL[item.unit]})`}>
          <input type="number" min={0.001} step="0.001" required value={quantity}
            onChange={e => setQuantity(e.target.value)} placeholder="0" className={inputCls} autoFocus />
        </Field>

        <Field label="Motivo (opcional)">
          <input type="text" value={reason} onChange={e => setReason(e.target.value)}
            placeholder="…" className={inputCls} />
        </Field>

        <div className="flex gap-2 pt-1">
          <button type="button" onClick={onClose}
            className="flex-1 py-2.5 rounded-xl text-sm font-semibold text-stone-400
                       border border-stone-700/60 hover:bg-stone-800/50 transition-colors">
            Cancelar
          </button>
          <button type="submit" disabled={loading}
            className="flex-1 py-2.5 rounded-xl text-sm font-semibold bg-amber-500 hover:bg-amber-400
                       text-stone-900 disabled:opacity-40 transition-colors">
            {loading ? 'Salvando…' : 'Registrar'}
          </button>
        </div>
      </form>
    </ModalOverlay>
  )
}

// ── Modal: Histórico de movimentações ────────────────────────────────────────

function HistoryModal({ item, onClose }: { item: StockItem; onClose: () => void }) {
  const [movements, setMovements] = useState<StockMovement[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchStockMovements(item.id)
      .then(setMovements)
      .catch(err => setError(err instanceof Error ? err.message : 'Erro ao carregar histórico'))
      .finally(() => setLoading(false))
  }, [item.id])

  return (
    <ModalOverlay title={`Histórico — ${item.name}`} onClose={onClose}>
      {error && <ErrorBanner message={error} />}
      {loading ? (
        <Spinner />
      ) : movements.length === 0 ? (
        <p className="text-stone-600 text-sm py-6 text-center">Nenhuma movimentação registrada.</p>
      ) : (
        <div className="space-y-1.5 max-h-[60vh] overflow-y-auto">
          {movements.map(m => {
            const positive = Number(m.quantity_change) >= 0
            return (
              <div key={m.id} className="flex items-center justify-between gap-3 px-3 py-2.5 rounded-xl"
                   style={{ background: 'var(--color-app-bg)' }}>
                <div className="min-w-0">
                  <p className="text-stone-300 text-sm font-medium">
                    {MOVEMENT_LABEL[m.kind]}
                    {m.reason && <span className="text-stone-600 font-normal"> · {m.reason}</span>}
                  </p>
                  <p className="text-stone-600 text-xs mt-0.5">{timeOf(m.created_at)}</p>
                </div>
                <span className={['text-sm font-bold shrink-0', positive ? 'text-green-400' : 'text-red-400'].join(' ')}>
                  {positive ? '+' : ''}{fmtQty(m.quantity_change)} {UNIT_LABEL[item.unit]}
                </span>
              </div>
            )
          })}
        </div>
      )}
    </ModalOverlay>
  )
}

// ── Linha de insumo ───────────────────────────────────────────────────────────

function StockItemRow({ item, onMovement, onHistory, onEdit, onDelete }: {
  item: StockItem
  onMovement: () => void
  onHistory: () => void
  onEdit: () => void
  onDelete: () => void
}) {
  return (
    <div className="flex items-center justify-between gap-3 px-4 py-3 border-b border-stone-800/30 last:border-0">
      <div className="min-w-0">
        <div className="flex items-center gap-1.5">
          <p className="text-stone-200 text-sm font-medium truncate">{item.name}</p>
          {item.is_low && (
            <span className="shrink-0 text-[9px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded-full
                             text-red-400 bg-red-500/15 border border-red-500/30">
              Baixo
            </span>
          )}
        </div>
        <p className="text-stone-600 text-xs mt-0.5">
          {fmtQty(item.quantity_on_hand)} {UNIT_LABEL[item.unit]} em estoque
          {Number(item.min_quantity) > 0 && ` · mín. ${fmtQty(item.min_quantity)} ${UNIT_LABEL[item.unit]}`}
        </p>
      </div>
      <div className="flex items-center gap-1.5 shrink-0">
        <button onClick={onMovement} title="Registrar movimentação"
          className="px-2.5 py-1.5 rounded-lg text-xs font-semibold text-amber-400
                     border border-amber-500/30 hover:bg-amber-500/10 transition-colors">
          Mov.
        </button>
        <button onClick={onHistory} title="Histórico"
          className="px-2.5 py-1.5 rounded-lg text-xs font-semibold text-stone-400
                     border border-stone-700/60 hover:bg-stone-800/50 transition-colors">
          Histórico
        </button>
        <button onClick={onEdit} title="Editar"
          className="px-2.5 py-1.5 rounded-lg text-xs font-semibold text-stone-400
                     border border-stone-700/60 hover:bg-stone-800/50 transition-colors">
          Editar
        </button>
        <button onClick={onDelete} title="Remover"
          className="p-1.5 rounded-lg text-stone-600 hover:text-red-400 hover:bg-red-500/10 transition-colors">
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.9}>
            <path strokeLinecap="round" strokeLinejoin="round"
              d="M6 7h12M9 7V5a2 2 0 012-2h2a2 2 0 012 2v2m2 0v13a2 2 0 01-2 2H8a2 2 0 01-2-2V7h12z" />
          </svg>
        </button>
      </div>
    </div>
  )
}

// ── Página ────────────────────────────────────────────────────────────────────

type Modal =
  | { type: 'new' }
  | { type: 'edit'; item: StockItem }
  | { type: 'movement'; item: StockItem }
  | { type: 'history'; item: StockItem }

export default function EstoquePage() {
  const [items, setItems] = useState<StockItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [modal, setModal] = useState<Modal | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      setItems(await fetchStockItems())
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro ao carregar estoque')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  async function handleDelete(item: StockItem) {
    if (!confirm(`Remover "${item.name}" do estoque?`)) return
    try {
      await deleteStockItem(item.id)
      setItems(prev => prev.filter(i => i.id !== item.id))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro ao remover insumo')
    }
  }

  const visible = items.filter(i => !search || i.name.toLowerCase().includes(search.toLowerCase()))
  const lowCount = items.filter(i => i.is_low).length

  return (
    <div className="h-full overflow-y-auto">
      <div className="max-w-3xl mx-auto px-4 sm:px-6 py-6">

        {/* Cabeçalho */}
        <div className="flex items-start justify-between gap-3 mb-4 flex-wrap">
          <div>
            <h1 className="text-stone-100 text-xl font-bold leading-tight">Estoque</h1>
            <p className="text-stone-500 text-sm mt-1">
              {items.length} {items.length === 1 ? 'insumo' : 'insumos'}
              {lowCount > 0 && <span className="text-red-400"> · {lowCount} com estoque baixo</span>}
            </p>
          </div>
          <button onClick={() => setModal({ type: 'new' })}
            className="flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-semibold
                       bg-amber-500 hover:bg-amber-400 text-stone-900 transition-colors">
            <span className="text-base leading-none">+</span>
            Novo insumo
          </button>
        </div>

        {/* Busca */}
        <input type="text" value={search} onChange={e => setSearch(e.target.value)}
          placeholder="Buscar insumo…" className={[inputCls, 'mb-5'].join(' ')} />

        {error && <ErrorBanner message={error} onRetry={load} />}

        {loading ? (
          <Spinner />
        ) : visible.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-center">
            <p className="text-stone-400 text-sm font-medium">
              {search ? 'Nenhum insumo encontrado' : 'Nenhum insumo cadastrado'}
            </p>
            <p className="text-stone-600 text-xs mt-1">
              {search ? 'Tente outra busca' : 'Clique em "Novo insumo" para começar'}
            </p>
          </div>
        ) : (
          <div className="rounded-2xl border border-stone-800/60 overflow-hidden"
               style={{ background: 'var(--color-app-surface)' }}>
            {visible
              .sort((a, b) => a.name.localeCompare(b.name))
              .map(item => (
                <StockItemRow
                  key={item.id}
                  item={item}
                  onMovement={() => setModal({ type: 'movement', item })}
                  onHistory={() => setModal({ type: 'history', item })}
                  onEdit={() => setModal({ type: 'edit', item })}
                  onDelete={() => handleDelete(item)}
                />
              ))}
          </div>
        )}
      </div>

      {/* Modais */}
      {(modal?.type === 'new' || modal?.type === 'edit') && (
        <StockItemModal
          item={modal.type === 'edit' ? modal.item : null}
          onClose={() => setModal(null)}
          onSaved={saved => {
            setItems(prev => modal.type === 'edit'
              ? prev.map(i => i.id === saved.id ? saved : i)
              : [...prev, saved])
            setModal(null)
          }}
        />
      )}

      {modal?.type === 'movement' && (
        <MovementModal item={modal.item} onClose={() => setModal(null)}
          onSaved={() => { setModal(null); load() }} />
      )}

      {modal?.type === 'history' && (
        <HistoryModal item={modal.item} onClose={() => setModal(null)} />
      )}
    </div>
  )
}
