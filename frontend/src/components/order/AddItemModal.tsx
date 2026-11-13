import { useState, useEffect } from 'react'
import {
  type Order, type Table, type Category, type MenuItem, fetchCategories, fetchMenuItems, addOrderItem, requestRemotePrint,
} from '../../lib/api'
import { brl, maskCurrency, parseCurrency } from '../../lib/format'
import { Field, QtyStepper } from '../ui'
import { inputCls } from '../../lib/styles'

// ── Modal: Adicionar item ─────────────────────────────────────────────────────

export function AddItemModal({
  order, onClose, onAdded,
}: {
  order: Order
  table: Table | undefined
  onClose: () => void
  onAdded: (updated: Order) => void
}) {
  // "Adicionar e imprimir": só o item recém-lançado sai na térmica do bar,
  // direto pelo servidor (mesmo padrão de ticket do pedido online)
  function printKitchenItem(name: string, qty: number, notes: string | null) {
    requestRemotePrint(order.id, 'cozinha', [{ name, qty, notes }])
      .catch(err => setAddError(err instanceof Error ? `Item lançado, mas não imprimiu: ${err.message}` : 'Item lançado, mas não imprimiu'))
  }
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
      // Com complemento continua ligado ao item do cardápio (o servidor monta
      // "Churrasco - frango") — assim vai pra cozinha e baixa estoque
      const updated = await addOrderItem(order.id, {
        menu_item_id: picking.id,
        complemento: comp || undefined,
        quantity: Number(qty),
        notes: notes.trim() || null,
      })
      if (andPrint) printKitchenItem(effectiveName, Number(qty), notes.trim() || null)
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
      if (andPrint) printKitchenItem(name, Number(manQty), manNotes.trim() || null)
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
      // O servidor monta o mesmo nome e cobra a metade mais cara; mandar as
      // duas metades (e não um item manual) faz a pizza ir pra cozinha (KDS)
      const updated = await addOrderItem(order.id, {
        menu_item_id: halfItem1.id,
        half_with: halfItem2.id,
        quantity: Number(halfQty),
        notes: halfNotes.trim() || null,
      })
      if (andPrint) printKitchenItem(name, Number(halfQty), halfNotes.trim() || null)
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
      {/* flex-1 (não 100dvh): o pai já é fixo nas 4 bordas — o dvh fica errado
          no Android depois do "puxar pra atualizar" (ver Layout) */}
      <div className="w-full flex-1 min-h-0 sm:flex-none sm:h-auto sm:max-w-md sm:max-h-[85dvh] sm:rounded-3xl
                      overflow-y-auto overscroll-contain flex flex-col p-5"
           style={{
             background: 'var(--color-app-surface)',
             paddingTop: 'max(1.25rem, env(safe-area-inset-top))',
             paddingBottom: 'max(1.25rem, env(safe-area-inset-bottom))',
           }}
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
      <div className="flex gap-1 p-1 rounded-xl mb-4" style={{ background: 'var(--color-app-bg)' }}>
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
              <div className="flex items-center gap-3 p-3 rounded-xl" style={{ background: 'var(--color-app-bg)' }}>
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
                  className={inputCls} style={{ background: 'var(--color-app-bg)' }} />
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
                  style={{ background: 'var(--color-app-bg)' }} />
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
                className={inputCls + ' appearance-none'} style={{ background: 'var(--color-app-bg)' }}>
                <option value="">Escolha o sabor…</option>
                {halfOptions.map(i => (
                  <option key={i.id} value={i.id}>{i.name} — {brl(i.price)}</option>
                ))}
              </select>
            </Field>
            <Field label="Segunda metade (½)">
              <select value={half2} onChange={e => setHalf2(e.target.value)}
                className={inputCls + ' appearance-none'} style={{ background: 'var(--color-app-bg)' }}>
                <option value="">Escolha o sabor…</option>
                {halfOptions.map(i => (
                  <option key={i.id} value={i.id}>{i.name} — {brl(i.price)}</option>
                ))}
              </select>
            </Field>

            {/* Preço calculado = metade mais cara */}
            {halfItem1 && halfItem2 && (
              <div className="flex items-center justify-between rounded-xl px-3.5 py-2.5"
                   style={{ background: 'var(--color-app-bg)' }}>
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
                className={inputCls} style={{ background: 'var(--color-app-bg)' }} />
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
              placeholder="ex: Cerveja especial" className={inputCls} style={{ background: 'var(--color-app-bg)' }} />
          </Field>
          <Field label="Preço (R$)">
            <input type="text" inputMode="numeric" required value={manPrice}
              onChange={e => setManPrice(maskCurrency(e.target.value))}
              placeholder="0,00" className={inputCls} style={{ background: 'var(--color-app-bg)' }} />
          </Field>
          <Field label="Quantidade">
            <QtyStepper value={Number(manQty)} onChange={n => setManQty(String(n))} />
          </Field>
          <Field label="Observações (opcional)">
            <input type="text" value={manNotes} onChange={e => setManNotes(e.target.value)}
              placeholder="ex: sem gelo" className={inputCls} style={{ background: 'var(--color-app-bg)' }} />
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
