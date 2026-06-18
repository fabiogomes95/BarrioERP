import { useState, useEffect, useCallback } from 'react'
import {
  type Category, type MenuItem,
  getUser,
  fetchCategories, fetchMenuItems,
  createCategory, updateCategory, deleteCategory,
  createMenuItem, updateMenuItem,
} from '../lib/api'
import { maskCurrency, parseCurrency, toCurrencyInput } from '../lib/format'

// ── Helpers ───────────────────────────────────────────────────────────────────

function brl(v: string | number) {
  return Number(v).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })
}

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

// ── Toggle reutilizável ───────────────────────────────────────────────────────

function Toggle({ label, hint, value, onChange }: {
  label: string; hint?: string; value: boolean; onChange: (v: boolean) => void
}) {
  return (
    <label className="flex items-center justify-between gap-3 cursor-pointer select-none">
      <div>
        <p className="text-sm text-stone-300">{label}</p>
        {hint && <p className="text-xs text-stone-600 mt-0.5">{hint}</p>}
      </div>
      <div onClick={() => onChange(!value)}
        className={['relative shrink-0 w-10 rounded-full transition-colors duration-200', value ? 'bg-amber-500' : 'bg-stone-700'].join(' ')}
        style={{ height: '22px' }}>
        <span className={['absolute top-0.5 w-4 h-4 rounded-full bg-white shadow transition-transform duration-200', value ? 'translate-x-5' : 'translate-x-0.5'].join(' ')} />
      </div>
    </label>
  )
}

// ── Modal base ────────────────────────────────────────────────────────────────

function ModalOverlay({ title, onClose, children }: {
  title: string; onClose: () => void; children: React.ReactNode
}) {
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
        <div className="flex items-center justify-between mb-5">
          <h2 className="text-stone-100 text-base font-bold">{title}</h2>
          <button onClick={onClose} className="text-stone-600 hover:text-stone-400 transition-colors p-1">
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
        {children}
      </div>
    </div>
  )
}

// ── Modal de categoria ────────────────────────────────────────────────────────

function CategoryModal({ editing, onClose, onSaved }: {
  editing: Category | null; onClose: () => void; onSaved: (c: Category) => void
}) {
  const [name, setName] = useState(editing?.name ?? '')
  const [description, setDescription] = useState(editing?.description ?? '')
  const [sortOrder, setSortOrder] = useState(String(editing?.sort_order ?? 0))
  const [isActive, setIsActive] = useState(editing?.is_active ?? true)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault(); setError(null); setLoading(true)
    try {
      const data = { name: name.trim(), description: description.trim() || null, sort_order: Number(sortOrder) }
      const saved = editing
        ? await updateCategory(editing.id, { ...data, is_active: isActive })
        : await createCategory(data)
      onSaved(saved)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro ao salvar')
    } finally { setLoading(false) }
  }

  return (
    <ModalOverlay title={editing ? 'Editar categoria' : 'Nova categoria'} onClose={onClose}>
      {error && <p className="text-red-400 text-xs bg-red-500/10 border border-red-500/20 rounded-xl px-3 py-2.5 mb-4">{error}</p>}
      <form onSubmit={handleSubmit} className="space-y-3.5">
        <Field label="Nome">
          <input type="text" required value={name} onChange={e => setName(e.target.value)}
            placeholder="ex: Bebidas, Pratos, Sobremesas"
            className={inputCls} style={{ background: '#0d0b08' }} />
        </Field>
        <Field label="Descrição (opcional)">
          <input type="text" value={description} onChange={e => setDescription(e.target.value)}
            placeholder="ex: Cervejas, chopes e coquetéis"
            className={inputCls} style={{ background: '#0d0b08' }} />
        </Field>
        <Field label="Posição (ordem)">
          <input type="number" min={0} max={9999} value={sortOrder}
            onChange={e => setSortOrder(e.target.value)}
            className={inputCls} style={{ background: '#0d0b08' }} />
        </Field>
        {editing && <Toggle label="Categoria ativa" value={isActive} onChange={setIsActive} />}
        <div className="flex gap-2 pt-1">
          <button type="button" onClick={onClose}
            className="flex-1 py-2.5 rounded-xl text-sm font-semibold text-stone-400 border border-stone-700/60 hover:bg-stone-800/50 transition-colors">
            Cancelar
          </button>
          <button type="submit" disabled={loading}
            className="flex-1 py-2.5 rounded-xl text-sm font-semibold bg-amber-500 hover:bg-amber-400 text-stone-900 disabled:opacity-40 transition-colors">
            {loading ? 'Salvando…' : 'Salvar'}
          </button>
        </div>
      </form>
    </ModalOverlay>
  )
}

// ── Modal de item ─────────────────────────────────────────────────────────────

function ItemModal({ editing, defaultCategoryId, categories, onClose, onSaved }: {
  editing: MenuItem | null
  defaultCategoryId: string
  categories: Category[]
  onClose: () => void
  onSaved: (item: MenuItem) => void
}) {
  const [categoryId, setCategoryId] = useState(editing?.category_id ?? defaultCategoryId)
  const [name, setName] = useState(editing?.name ?? '')
  const [description, setDescription] = useState(editing?.description ?? '')
  const [price, setPrice] = useState(editing ? toCurrencyInput(editing.price) : '')
  const [sortOrder, setSortOrder] = useState(String(editing?.sort_order ?? 0))
  const [isAvailable, setIsAvailable] = useState(editing?.is_available ?? true)
  const [isActive, setIsActive] = useState(editing?.is_active ?? true)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault(); setError(null)
    const priceNum = parseCurrency(price)
    if (isNaN(priceNum) || priceNum <= 0) { setError('Preço inválido'); return }
    setLoading(true)
    try {
      const data = {
        category_id: categoryId,
        name: name.trim(),
        description: description.trim() || null,
        price: priceNum,
        sort_order: Number(sortOrder),
        is_available: isAvailable,
      }
      const saved = editing
        ? await updateMenuItem(editing.id, { ...data, is_active: isActive })
        : await createMenuItem(data)
      onSaved(saved)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro ao salvar item')
    } finally { setLoading(false) }
  }

  return (
    <ModalOverlay title={editing ? 'Editar item' : 'Novo item'} onClose={onClose}>
      {error && <p className="text-red-400 text-xs bg-red-500/10 border border-red-500/20 rounded-xl px-3 py-2.5 mb-4">{error}</p>}
      <form onSubmit={handleSubmit} className="space-y-3.5">
        <Field label="Categoria">
          <select value={categoryId} onChange={e => setCategoryId(e.target.value)}
            className={inputCls + ' appearance-none'} style={{ background: '#0d0b08' }}>
            {categories.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </Field>
        <Field label="Nome do item">
          <input type="text" required value={name} onChange={e => setName(e.target.value)}
            placeholder="ex: Cerveja Heineken 600ml"
            className={inputCls} style={{ background: '#0d0b08' }} />
        </Field>
        <Field label="Descrição (opcional)">
          <input type="text" value={description} onChange={e => setDescription(e.target.value)}
            placeholder="ex: Gelada, servida em copo americano"
            className={inputCls} style={{ background: '#0d0b08' }} />
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Preço (R$)">
            <input type="text" inputMode="numeric" required value={price}
              onChange={e => setPrice(maskCurrency(e.target.value))}
              placeholder="0,00" className={inputCls} style={{ background: '#0d0b08' }} />
          </Field>
          <Field label="Posição">
            <input type="number" min={0} max={9999} value={sortOrder}
              onChange={e => setSortOrder(e.target.value)}
              className={inputCls} style={{ background: '#0d0b08' }} />
          </Field>
        </div>
        <div className="space-y-3 pt-1">
          <Toggle label="Disponível agora" hint="Desative quando o item acabar" value={isAvailable} onChange={setIsAvailable} />
          {editing && <Toggle label="Item ativo no cardápio" hint="Inativo não aparece para clientes" value={isActive} onChange={setIsActive} />}
        </div>
        <div className="flex gap-2 pt-1">
          <button type="button" onClick={onClose}
            className="flex-1 py-2.5 rounded-xl text-sm font-semibold text-stone-400 border border-stone-700/60 hover:bg-stone-800/50 transition-colors">
            Cancelar
          </button>
          <button type="submit" disabled={loading}
            className="flex-1 py-2.5 rounded-xl text-sm font-semibold bg-amber-500 hover:bg-amber-400 text-stone-900 disabled:opacity-40 transition-colors">
            {loading ? 'Salvando…' : 'Salvar'}
          </button>
        </div>
      </form>
    </ModalOverlay>
  )
}

// ── Card de item ──────────────────────────────────────────────────────────────

function ItemCard({ item, canEdit, onToggleAvailable, onEdit, onToggleActive }: {
  item: MenuItem; canEdit: boolean
  onToggleAvailable: () => Promise<void>
  onEdit: () => void
  onToggleActive: () => void
}) {
  const [toggling, setToggling] = useState(false)

  async function handleToggle() {
    setToggling(true)
    try { await onToggleAvailable() } finally { setToggling(false) }
  }

  return (
    <div className={['rounded-2xl border border-stone-800/50 p-4 transition-all', !item.is_active ? 'opacity-40' : ''].join(' ')}
         style={{ background: '#161210' }}>
      <div className="flex items-start justify-between gap-2 mb-2">
        <div className="flex-1 min-w-0">
          <p className="text-stone-100 text-sm font-semibold leading-tight truncate">{item.name}</p>
          {item.description && (
            <p className="text-stone-600 text-xs mt-0.5 leading-snug line-clamp-2">{item.description}</p>
          )}
        </div>
        <span className="text-amber-400 text-base font-black shrink-0 leading-tight">{brl(item.price)}</span>
      </div>

      <div className="flex items-center justify-between mt-3 pt-3 border-t border-stone-800/40">
        {/* Toggle disponibilidade */}
        <button onClick={canEdit ? handleToggle : undefined} disabled={toggling || !canEdit}
          className={[
            'flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-semibold transition-all',
            item.is_available ? 'bg-green-500/10 text-green-400 border border-green-500/20' : 'bg-red-500/10 text-red-400 border border-red-500/20',
            canEdit && !toggling ? 'hover:opacity-80 cursor-pointer' : 'cursor-default',
          ].join(' ')}>
          <span className={['w-1.5 h-1.5 rounded-full', item.is_available ? 'bg-green-400' : 'bg-red-400', toggling ? 'animate-pulse' : ''].join(' ')} />
          {item.is_available ? 'Disponível' : 'Indisponível'}
        </button>

        {canEdit && (
          <div className="flex items-center gap-1">
            <button onClick={onEdit}
              className="w-7 h-7 flex items-center justify-center rounded-lg text-stone-600 hover:text-stone-300 hover:bg-stone-800/60 transition-all"
              title="Editar">
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round"
                  d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
              </svg>
            </button>
            <button onClick={onToggleActive}
              className="w-7 h-7 flex items-center justify-center rounded-lg text-stone-600 hover:text-red-400 hover:bg-red-500/10 transition-all"
              title={item.is_active ? 'Desativar item' : 'Reativar item'}>
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                {item.is_active
                  ? <path strokeLinecap="round" strokeLinejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                  : <path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                }
              </svg>
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

// ── Página principal ──────────────────────────────────────────────────────────

export default function CardapioPage() {
  const user = getUser()
  const canEdit = user?.role === 'owner' || user?.role === 'manager'

  const [categories, setCategories] = useState<Category[]>([])
  const [items, setItems] = useState<MenuItem[]>([])
  const [selectedCat, setSelectedCat] = useState<Category | null>(null)
  const [loading, setLoading] = useState(true)
  const [mobileItems, setMobileItems] = useState(false)
  const [search, setSearch] = useState('')

  const [catModal, setCatModal] = useState<{ open: boolean; editing: Category | null }>({ open: false, editing: null })
  const [itemModal, setItemModal] = useState<{ open: boolean; editing: MenuItem | null }>({ open: false, editing: null })

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [cats, its] = await Promise.all([fetchCategories(), fetchMenuItems()])
      const sorted = cats.sort((a, b) => a.sort_order - b.sort_order)
      setCategories(sorted)
      setItems(its.sort((a, b) => a.sort_order - b.sort_order))
      setSelectedCat(prev => prev ?? (sorted[0] ?? null))
    } finally { setLoading(false) }
  }, [])

  useEffect(() => { load() }, []) // eslint-disable-line

  function visibleItems(cat: Category | null) {
    if (!cat) return { active: [], inactive: [] }
    let list = items.filter(i => i.category_id === cat.id)
    if (search) list = list.filter(i => i.name.toLowerCase().includes(search.toLowerCase()))
    return { active: list.filter(i => i.is_active), inactive: list.filter(i => !i.is_active) }
  }

  function handleCatSaved(c: Category) {
    setCategories(prev => {
      const exists = prev.find(x => x.id === c.id)
      return (exists ? prev.map(x => x.id === c.id ? c : x) : [...prev, c]).sort((a, b) => a.sort_order - b.sort_order)
    })
    setSelectedCat(c)
    setCatModal({ open: false, editing: null })
  }

  function handleItemSaved(item: MenuItem) {
    setItems(prev => {
      const exists = prev.find(x => x.id === item.id)
      return (exists ? prev.map(x => x.id === item.id ? item : x) : [...prev, item]).sort((a, b) => a.sort_order - b.sort_order)
    })
    setItemModal({ open: false, editing: null })
  }

  async function handleToggleAvailable(item: MenuItem) {
    const updated = await updateMenuItem(item.id, { is_available: !item.is_available })
    setItems(prev => prev.map(i => i.id === updated.id ? updated : i))
  }

  async function handleToggleActive(item: MenuItem) {
    const updated = await updateMenuItem(item.id, { is_active: !item.is_active })
    setItems(prev => prev.map(i => i.id === updated.id ? updated : i))
  }

  async function handleDeleteCat(cat: Category) {
    try {
      await deleteCategory(cat.id)
      setCategories(prev => prev.filter(c => c.id !== cat.id))
      if (selectedCat?.id === cat.id) setSelectedCat(categories.find(c => c.id !== cat.id) ?? null)
    } catch { /* ignore */ }
  }

  const { active: activeItems, inactive: inactiveItems } = visibleItems(selectedCat)

  return (
    <div className="h-full flex">

      {/* ── Coluna de categorias ─────────────────────────────────── */}
      <div className={['flex flex-col shrink-0 border-r border-stone-800/50 w-full md:w-64',
        mobileItems ? 'hidden md:flex' : 'flex'].join(' ')}>

        <div className="px-4 pt-5 pb-4 border-b border-stone-800/50 shrink-0"
             style={{ background: '#0f0d0a' }}>
          <div className="flex items-center justify-between">
            <h1 className="text-stone-100 text-lg font-bold">Cardápio</h1>
            {canEdit && (
              <button onClick={() => setCatModal({ open: true, editing: null })}
                className="flex items-center gap-1 px-3 py-2 rounded-xl text-xs font-semibold
                           bg-amber-500/10 text-amber-400 border border-amber-500/20 hover:bg-amber-500/20 transition-colors">
                <span className="text-sm leading-none">+</span> Categoria
              </button>
            )}
          </div>
          {!loading && (
            <p className="text-stone-600 text-xs mt-1">
              {categories.length} {categories.length === 1 ? 'categoria' : 'categorias'}
            </p>
          )}
        </div>

        <div className="flex-1 overflow-y-auto p-2">
          {loading ? (
            <div className="space-y-1">
              {Array.from({ length: 5 }).map((_, i) => (
                <div key={i} className="h-14 rounded-xl bg-stone-800/30 animate-pulse" />
              ))}
            </div>
          ) : categories.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 text-center px-4">
              <p className="text-stone-500 text-sm">Nenhuma categoria</p>
              {canEdit && <p className="text-stone-700 text-xs mt-1">Clique em "+ Categoria" para começar</p>}
            </div>
          ) : (
            <div className="space-y-0.5">
              {categories.map(cat => {
                const count = items.filter(i => i.category_id === cat.id && i.is_active).length
                const isSelected = selectedCat?.id === cat.id
                return (
                  <div key={cat.id}
                    className={[
                      'group flex items-center gap-2.5 px-3 py-3 rounded-xl cursor-pointer transition-all',
                      isSelected ? 'bg-amber-500/10 border border-amber-500/20' : 'hover:bg-stone-800/40 border border-transparent',
                      !cat.is_active ? 'opacity-40' : '',
                    ].join(' ')}
                    onClick={() => { setSelectedCat(cat); setMobileItems(true) }}>
                    <div className="flex-1 min-w-0">
                      <p className={['text-sm font-semibold leading-tight truncate', isSelected ? 'text-amber-400' : 'text-stone-300'].join(' ')}>
                        {cat.name}
                      </p>
                      <p className="text-stone-600 text-xs mt-0.5">{count} {count === 1 ? 'item' : 'itens'}</p>
                    </div>
                    {canEdit && (
                      <div className="flex gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
                        <button onClick={e => { e.stopPropagation(); setCatModal({ open: true, editing: cat }) }}
                          className="w-6 h-6 flex items-center justify-center rounded-lg text-stone-600 hover:text-stone-300 hover:bg-stone-700/50">
                          <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                            <path strokeLinecap="round" strokeLinejoin="round" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                          </svg>
                        </button>
                        <button onClick={e => { e.stopPropagation(); handleDeleteCat(cat) }}
                          className="w-6 h-6 flex items-center justify-center rounded-lg text-stone-600 hover:text-red-400 hover:bg-red-500/10">
                          <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                            <path strokeLinecap="round" strokeLinejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                          </svg>
                        </button>
                      </div>
                    )}
                    {isSelected && <span className="w-1 h-1 rounded-full bg-amber-500 shrink-0" />}
                  </div>
                )
              })}
            </div>
          )}
        </div>
      </div>

      {/* ── Coluna de itens ──────────────────────────────────────── */}
      <div className={['flex flex-col flex-1 overflow-hidden', mobileItems ? 'flex' : 'hidden md:flex'].join(' ')}>
        {selectedCat ? (
          <>
            <div className="px-5 pt-5 pb-4 border-b border-stone-800/50 shrink-0"
                 style={{ background: '#0f0d0a' }}>
              <div className="flex items-center gap-3 mb-4">
                <button onClick={() => setMobileItems(false)}
                  className="md:hidden text-stone-500 hover:text-stone-300 transition-colors">
                  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
                  </svg>
                </button>
                <div className="flex-1 min-w-0">
                  <h2 className="text-stone-100 text-base font-bold leading-tight truncate">{selectedCat.name}</h2>
                  {selectedCat.description && (
                    <p className="text-stone-500 text-xs mt-0.5 truncate">{selectedCat.description}</p>
                  )}
                </div>
                {canEdit && (
                  <button onClick={() => setItemModal({ open: true, editing: null })}
                    className="flex items-center gap-1.5 px-3 py-2 rounded-xl text-sm font-semibold
                               bg-amber-500 hover:bg-amber-400 text-stone-900 transition-colors shrink-0">
                    <span className="text-base leading-none">+</span> Novo item
                  </button>
                )}
              </div>
              <div className="relative">
                <svg className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-stone-600 pointer-events-none"
                     fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-4.35-4.35M17 11A6 6 0 105 11a6 6 0 0012 0z" />
                </svg>
                <input type="text" value={search} onChange={e => setSearch(e.target.value)}
                  placeholder="Buscar item…"
                  className="w-full pl-9 pr-4 py-2.5 rounded-xl text-sm border border-stone-800/60
                             text-stone-200 placeholder-stone-600 focus:outline-none
                             focus:border-amber-500/40 focus:ring-1 focus:ring-amber-500/20 transition-all"
                  style={{ background: '#161210' }} />
              </div>
            </div>

            <div className="flex-1 overflow-y-auto p-4">
              {activeItems.length === 0 && inactiveItems.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-20 text-center">
                  <div className="w-12 h-12 rounded-2xl bg-stone-800/60 flex items-center justify-center mb-3 text-2xl">🍽</div>
                  <p className="text-stone-400 text-sm font-medium">
                    {search ? 'Nenhum item encontrado' : 'Categoria vazia'}
                  </p>
                  {canEdit && !search && (
                    <p className="text-stone-600 text-xs mt-1">Clique em "+ Novo item" para adicionar</p>
                  )}
                </div>
              ) : (
                <div className="space-y-5">
                  {activeItems.length > 0 && (
                    <div>
                      <p className="text-stone-600 text-[11px] font-bold uppercase tracking-wider mb-2.5 px-1">
                        {activeItems.length} {activeItems.length === 1 ? 'item' : 'itens'}
                      </p>
                      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
                        {activeItems.map(item => (
                          <ItemCard key={item.id} item={item} canEdit={canEdit}
                            onToggleAvailable={() => handleToggleAvailable(item)}
                            onEdit={() => setItemModal({ open: true, editing: item })}
                            onToggleActive={() => handleToggleActive(item)} />
                        ))}
                      </div>
                    </div>
                  )}
                  {inactiveItems.length > 0 && (
                    <div>
                      <p className="text-stone-700 text-[11px] font-bold uppercase tracking-wider mb-2.5 px-1">
                        Inativos ({inactiveItems.length})
                      </p>
                      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
                        {inactiveItems.map(item => (
                          <ItemCard key={item.id} item={item} canEdit={canEdit}
                            onToggleAvailable={() => handleToggleAvailable(item)}
                            onEdit={() => setItemModal({ open: true, editing: item })}
                            onToggleActive={() => handleToggleActive(item)} />
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          </>
        ) : (
          <div className="flex flex-col items-center justify-center h-full text-center p-8">
            <div className="w-14 h-14 rounded-2xl bg-stone-800/40 flex items-center justify-center mb-4 text-3xl">🍽</div>
            <p className="text-stone-500 text-sm font-medium">Selecione uma categoria</p>
            {canEdit && <p className="text-stone-700 text-xs mt-1">Ou crie uma nova para começar</p>}
          </div>
        )}
      </div>

      {catModal.open && (
        <CategoryModal editing={catModal.editing}
          onClose={() => setCatModal({ open: false, editing: null })}
          onSaved={handleCatSaved} />
      )}

      {itemModal.open && selectedCat && (
        <ItemModal editing={itemModal.editing}
          defaultCategoryId={selectedCat.id}
          categories={categories.filter(c => c.is_active)}
          onClose={() => setItemModal({ open: false, editing: null })}
          onSaved={handleItemSaved} />
      )}
    </div>
  )
}
