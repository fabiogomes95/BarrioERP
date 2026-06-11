import { useEffect, useRef, useState } from 'react'
import {
  createUser,
  deleteUser,
  fetchUsers,
  getUser,
  resetUserPassword,
  type TeamUser,
  type UserRole,
  updateUser,
} from '../lib/api'

// ── Helpers ───────────────────────────────────────────────────────────────────

const ROLE_CONFIG: Record<UserRole, { label: string; bg: string; text: string; border: string }> = {
  owner:   { label: 'Proprietário', bg: 'bg-amber-500/15',  text: 'text-amber-400',  border: 'border-amber-500/30' },
  manager: { label: 'Gerente',      bg: 'bg-blue-500/15',   text: 'text-blue-400',   border: 'border-blue-500/30'  },
  cashier: { label: 'Caixa',        bg: 'bg-green-500/15',  text: 'text-green-400',  border: 'border-green-500/30' },
  waiter:  { label: 'Garçom',       bg: 'bg-stone-500/15',  text: 'text-stone-400',  border: 'border-stone-500/30' },
  kitchen: { label: 'Cozinha',      bg: 'bg-orange-500/15', text: 'text-orange-400', border: 'border-orange-500/30'},
}

const ROLE_OPTIONS: UserRole[] = ['owner', 'manager', 'cashier', 'waiter', 'kitchen']

const FILTERS: { key: UserRole | 'all'; label: string }[] = [
  { key: 'all', label: 'Todos' },
  { key: 'owner',   label: 'Proprietários' },
  { key: 'manager', label: 'Gerentes' },
  { key: 'cashier', label: 'Caixas' },
  { key: 'waiter',  label: 'Garçons' },
  { key: 'kitchen', label: 'Cozinha' },
]

function initials(name: string) {
  const parts = name.trim().split(' ')
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase()
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase()
}

// ── Modal overlay ─────────────────────────────────────────────────────────────

function ModalOverlay({ onClose, children }: { onClose: () => void; children: React.ReactNode }) {
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: 'rgba(0,0,0,0.7)', backdropFilter: 'blur(4px)' }}
      onClick={onClose}
    >
      <div onClick={e => e.stopPropagation()}>{children}</div>
    </div>
  )
}

// ── UserModal (criar / editar) ────────────────────────────────────────────────

function UserModal({
  user,
  currentUserRole,
  onClose,
  onSaved,
}: {
  user: TeamUser | null
  currentUserRole: UserRole
  onClose: () => void
  onSaved: (u: TeamUser) => void
}) {
  const isEdit = !!user
  const [name, setName]         = useState(user?.name ?? '')
  const [email, setEmail]       = useState(user?.email ?? '')
  const [phone, setPhone]       = useState(user?.phone ?? '')
  const [role, setRole]         = useState<UserRole>(user?.role ?? 'waiter')
  const [password, setPassword] = useState('')
  const [isActive, setIsActive] = useState(user?.is_active ?? true)
  const [loading, setLoading]   = useState(false)
  const [error, setError]       = useState<string | null>(null)

  const availableRoles = currentUserRole === 'owner' ? ROLE_OPTIONS : ROLE_OPTIONS.filter(r => r !== 'owner')

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      let saved: TeamUser
      if (isEdit) {
        saved = await updateUser(user.id, {
          name: name.trim(),
          email: email.trim(),
          phone: phone.trim() || null,
          role,
          is_active: isActive,
        })
      } else {
        saved = await createUser({
          name: name.trim(),
          email: email.trim(),
          password,
          role,
          phone: phone.trim() || null,
        })
      }
      onSaved(saved)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro ao salvar')
    } finally {
      setLoading(false)
    }
  }

  const inputCls =
    'w-full rounded-xl px-3.5 py-2.5 text-sm border border-stone-800/80 text-stone-100 placeholder-stone-700 focus:outline-none focus:border-amber-500/40 focus:ring-1 focus:ring-amber-500/20 disabled:opacity-40 transition-all'

  return (
    <ModalOverlay onClose={onClose}>
      <div
        className="w-full max-w-md rounded-2xl border border-stone-800/60 p-6"
        style={{ background: '#161210' }}
      >
        <div className="flex items-center justify-between mb-5">
          <p className="text-stone-100 font-semibold text-sm">
            {isEdit ? 'Editar membro' : 'Novo membro'}
          </p>
          <button onClick={onClose} className="text-stone-600 hover:text-stone-400 transition-colors text-lg leading-none">×</button>
        </div>

        {error && (
          <div className="bg-red-500/8 border border-red-500/20 text-red-400 text-xs rounded-xl px-3.5 py-2.5 mb-4">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-3.5">
          <div>
            <label className="block text-[11px] font-semibold text-stone-500 uppercase tracking-wider mb-1.5">Nome</label>
            <input
              required
              value={name}
              onChange={e => setName(e.target.value)}
              placeholder="Nome completo"
              disabled={loading}
              className={inputCls}
              style={{ background: '#0f0d0a' }}
            />
          </div>

          <div>
            <label className="block text-[11px] font-semibold text-stone-500 uppercase tracking-wider mb-1.5">E-mail</label>
            <input
              type="email"
              required
              value={email}
              onChange={e => setEmail(e.target.value)}
              placeholder="nome@seubar.com"
              disabled={loading}
              className={inputCls}
              style={{ background: '#0f0d0a' }}
            />
          </div>

          {!isEdit && (
            <div>
              <label className="block text-[11px] font-semibold text-stone-500 uppercase tracking-wider mb-1.5">Senha</label>
              <input
                type="password"
                required
                value={password}
                onChange={e => setPassword(e.target.value)}
                placeholder="Mínimo 8 caracteres, 1 letra e 1 número"
                disabled={loading}
                className={inputCls}
                style={{ background: '#0f0d0a' }}
              />
            </div>
          )}

          <div>
            <label className="block text-[11px] font-semibold text-stone-500 uppercase tracking-wider mb-1.5">Telefone</label>
            <input
              value={phone}
              onChange={e => setPhone(e.target.value)}
              placeholder="(opcional)"
              disabled={loading}
              className={inputCls}
              style={{ background: '#0f0d0a' }}
            />
          </div>

          <div>
            <label className="block text-[11px] font-semibold text-stone-500 uppercase tracking-wider mb-1.5">Cargo</label>
            <select
              value={role}
              onChange={e => setRole(e.target.value as UserRole)}
              disabled={loading}
              className={inputCls}
              style={{ background: '#0f0d0a' }}
            >
              {availableRoles.map(r => (
                <option key={r} value={r}>{ROLE_CONFIG[r].label}</option>
              ))}
            </select>
          </div>

          {isEdit && (
            <div className="flex items-center justify-between py-1">
              <span className="text-sm text-stone-400">Conta ativa</span>
              <button
                type="button"
                onClick={() => setIsActive(v => !v)}
                disabled={loading}
                className="relative transition-colors"
                style={{ width: 40, height: 22 }}
              >
                <div
                  className="absolute inset-0 rounded-full transition-colors"
                  style={{ background: isActive ? '#F59E0B' : '#44403c' }}
                />
                <div
                  className="absolute top-0.5 rounded-full bg-white transition-all"
                  style={{ width: 18, height: 18, left: isActive ? 20 : 2 }}
                />
              </button>
            </div>
          )}

          <div className="flex gap-2 pt-1">
            <button
              type="button"
              onClick={onClose}
              disabled={loading}
              className="flex-1 py-2.5 rounded-xl text-sm font-medium border border-stone-800 text-stone-400 hover:text-stone-300 hover:border-stone-700 transition-colors"
            >
              Cancelar
            </button>
            <button
              type="submit"
              disabled={loading}
              className="flex-1 py-2.5 rounded-xl text-sm font-semibold bg-amber-500 hover:bg-amber-400 text-stone-900 disabled:opacity-40 transition-colors"
            >
              {loading ? 'Salvando…' : isEdit ? 'Salvar' : 'Criar membro'}
            </button>
          </div>
        </form>
      </div>
    </ModalOverlay>
  )
}

// ── PasswordModal ─────────────────────────────────────────────────────────────

function PasswordModal({ user, onClose }: { user: TeamUser; onClose: () => void }) {
  const [password, setPassword] = useState('')
  const [loading, setLoading]   = useState(false)
  const [error, setError]       = useState<string | null>(null)
  const [done, setDone]         = useState(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      await resetUserPassword(user.id, password)
      setDone(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro ao redefinir')
    } finally {
      setLoading(false)
    }
  }

  return (
    <ModalOverlay onClose={onClose}>
      <div
        className="w-full max-w-sm rounded-2xl border border-stone-800/60 p-6"
        style={{ background: '#161210' }}
      >
        <div className="flex items-center justify-between mb-5">
          <p className="text-stone-100 font-semibold text-sm">Redefinir senha</p>
          <button onClick={onClose} className="text-stone-600 hover:text-stone-400 text-lg leading-none">×</button>
        </div>

        {done ? (
          <div className="text-center py-4">
            <div className="w-10 h-10 rounded-full bg-green-500/15 border border-green-500/30 flex items-center justify-center mx-auto mb-3">
              <svg className="w-5 h-5 text-green-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
              </svg>
            </div>
            <p className="text-stone-300 text-sm mb-1">Senha redefinida</p>
            <p className="text-stone-600 text-xs">Informe a nova senha ao membro</p>
            <button
              onClick={onClose}
              className="mt-4 px-5 py-2 rounded-xl text-sm font-medium bg-stone-800 text-stone-300 hover:bg-stone-700 transition-colors"
            >
              Fechar
            </button>
          </div>
        ) : (
          <>
            <p className="text-stone-500 text-xs mb-4">
              Nova senha para <span className="text-stone-300">{user.name}</span>
            </p>
            {error && (
              <div className="bg-red-500/8 border border-red-500/20 text-red-400 text-xs rounded-xl px-3.5 py-2.5 mb-4">
                {error}
              </div>
            )}
            <form onSubmit={handleSubmit} className="space-y-3">
              <input
                type="password"
                required
                value={password}
                onChange={e => setPassword(e.target.value)}
                placeholder="Mínimo 8 caracteres"
                disabled={loading}
                className="w-full rounded-xl px-3.5 py-2.5 text-sm border border-stone-800/80 text-stone-100 placeholder-stone-700 focus:outline-none focus:border-amber-500/40 focus:ring-1 focus:ring-amber-500/20 disabled:opacity-40 transition-all"
                style={{ background: '#0f0d0a' }}
              />
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={onClose}
                  disabled={loading}
                  className="flex-1 py-2.5 rounded-xl text-sm font-medium border border-stone-800 text-stone-400 hover:text-stone-300 transition-colors"
                >
                  Cancelar
                </button>
                <button
                  type="submit"
                  disabled={loading}
                  className="flex-1 py-2.5 rounded-xl text-sm font-semibold bg-amber-500 hover:bg-amber-400 text-stone-900 disabled:opacity-40 transition-colors"
                >
                  {loading ? 'Salvando…' : 'Redefinir'}
                </button>
              </div>
            </form>
          </>
        )}
      </div>
    </ModalOverlay>
  )
}

// ── UserCard ──────────────────────────────────────────────────────────────────

function UserCard({
  user,
  currentUserId,
  canEdit,
  onEdit,
  onPassword,
  onDeactivate,
}: {
  user: TeamUser
  currentUserId: string
  canEdit: boolean
  onEdit: (u: TeamUser) => void
  onPassword: (u: TeamUser) => void
  onDeactivate: (u: TeamUser) => void
}) {
  const [confirmDeact, setConfirmDeact] = useState(false)
  const cfg  = ROLE_CONFIG[user.role]
  const self = user.id === currentUserId

  return (
    <div
      className="relative rounded-2xl border p-4 flex flex-col gap-3 transition-colors"
      style={{
        background: user.is_active ? '#161210' : '#100e0c',
        borderColor: user.is_active ? 'rgba(120,113,108,0.2)' : 'rgba(120,113,108,0.1)',
        opacity: user.is_active ? 1 : 0.6,
      }}
    >
      {/* Avatar + nome + status */}
      <div className="flex items-start gap-3">
        <div
          className="w-10 h-10 rounded-full flex items-center justify-center text-sm font-bold shrink-0 border"
          style={{
            background: `rgba(245,158,11,0.${user.is_active ? '12' : '06'})`,
            borderColor: `rgba(245,158,11,0.${user.is_active ? '25' : '12'})`,
            color: user.is_active ? '#F59E0B' : '#78716c',
          }}
        >
          {initials(user.name)}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5 flex-wrap">
            <p className="text-stone-100 text-sm font-medium truncate">{user.name}</p>
            {self && (
              <span className="text-[10px] text-stone-600 bg-stone-800/50 rounded-full px-1.5 py-0.5">você</span>
            )}
          </div>
          <p className="text-stone-600 text-xs truncate mt-0.5">{user.email}</p>
          {user.phone && <p className="text-stone-700 text-xs mt-0.5">{user.phone}</p>}
        </div>
      </div>

      {/* Badge cargo + status */}
      <div className="flex items-center gap-2">
        <span
          className={`text-[11px] font-semibold px-2.5 py-0.5 rounded-full border ${cfg.bg} ${cfg.text} ${cfg.border}`}
        >
          {cfg.label}
        </span>
        {!user.is_active && (
          <span className="text-[11px] text-stone-600 bg-stone-800/40 border border-stone-800/60 rounded-full px-2.5 py-0.5">
            Inativo
          </span>
        )}
      </div>

      {/* Ações */}
      {canEdit && !self && (
        <div className="flex gap-1.5">
          {!confirmDeact ? (
            <>
              <button
                onClick={() => onEdit(user)}
                className="flex-1 py-1.5 rounded-xl text-xs font-medium border border-stone-800/80 text-stone-400 hover:text-stone-300 hover:border-stone-700 transition-colors"
              >
                Editar
              </button>
              <button
                onClick={() => onPassword(user)}
                className="flex-1 py-1.5 rounded-xl text-xs font-medium border border-stone-800/80 text-stone-400 hover:text-stone-300 hover:border-stone-700 transition-colors"
              >
                Senha
              </button>
              <button
                onClick={() => setConfirmDeact(true)}
                className="flex-1 py-1.5 rounded-xl text-xs font-medium border border-red-500/20 text-red-500/70 hover:text-red-400 hover:border-red-500/40 transition-colors"
              >
                {user.is_active ? 'Remover' : 'Reativar'}
              </button>
            </>
          ) : (
            <>
              <span className="flex-1 text-xs text-red-400 self-center">Confirmar?</span>
              <button
                onClick={() => setConfirmDeact(false)}
                className="px-3 py-1.5 rounded-xl text-xs border border-stone-800 text-stone-500 hover:text-stone-400 transition-colors"
              >
                Não
              </button>
              <button
                onClick={() => { setConfirmDeact(false); onDeactivate(user) }}
                className="px-3 py-1.5 rounded-xl text-xs font-semibold bg-red-500/15 border border-red-500/30 text-red-400 hover:bg-red-500/25 transition-colors"
              >
                Sim
              </button>
            </>
          )}
        </div>
      )}
    </div>
  )
}

// ── EquipePage ────────────────────────────────────────────────────────────────

export default function EquipePage() {
  const currentUser = getUser()!
  const canEdit = currentUser.role === 'owner' || currentUser.role === 'manager'

  const [users, setUsers]             = useState<TeamUser[]>([])
  const [loading, setLoading]         = useState(true)
  const [filter, setFilter]           = useState<UserRole | 'all'>('all')
  const [search, setSearch]           = useState('')
  const [editUser, setEditUser]       = useState<TeamUser | null | undefined>(undefined)
  const [pwUser, setPwUser]           = useState<TeamUser | null>(null)
  const searchRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    fetchUsers()
      .then(setUsers)
      .finally(() => setLoading(false))
  }, [])

  function handleSaved(saved: TeamUser) {
    setUsers(prev => {
      const exists = prev.find(u => u.id === saved.id)
      return exists ? prev.map(u => u.id === saved.id ? saved : u) : [saved, ...prev]
    })
    setEditUser(undefined)
  }

  async function handleDeactivate(user: TeamUser) {
    try {
      if (user.is_active) {
        await deleteUser(user.id)
        setUsers(prev => prev.map(u => u.id === user.id ? { ...u, is_active: false } : u))
      } else {
        const updated = await updateUser(user.id, { is_active: true })
        setUsers(prev => prev.map(u => u.id === user.id ? updated : u))
      }
    } catch {
      // erros já tratados pelo request() helper
    }
  }

  const filtered = users.filter(u => {
    if (filter !== 'all' && u.role !== filter) return false
    if (search) {
      const q = search.toLowerCase()
      return u.name.toLowerCase().includes(q) || u.email.toLowerCase().includes(q)
    }
    return true
  })

  const activeCount   = users.filter(u => u.is_active).length
  const inactiveCount = users.filter(u => !u.is_active).length

  return (
    <div className="h-full flex flex-col" style={{ background: '#0d0b08' }}>
      {/* Header */}
      <div className="shrink-0 border-b border-stone-800/50 px-4 py-3" style={{ background: '#0f0d0a' }}>
        <div className="flex items-center justify-between gap-3">
          <div>
            <h1 className="text-stone-100 font-semibold text-base">Equipe</h1>
            {!loading && (
              <p className="text-stone-600 text-xs mt-0.5">
                {activeCount} ativo{activeCount !== 1 ? 's' : ''}
                {inactiveCount > 0 && ` · ${inactiveCount} inativo${inactiveCount !== 1 ? 's' : ''}`}
              </p>
            )}
          </div>
          {canEdit && (
            <button
              onClick={() => setEditUser(null)}
              className="flex items-center gap-1.5 px-3.5 py-2 rounded-xl text-sm font-semibold bg-amber-500 hover:bg-amber-400 text-stone-900 transition-colors"
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
              </svg>
              Novo membro
            </button>
          )}
        </div>

        {/* Busca */}
        <div className="mt-3 relative">
          <svg className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-stone-600 pointer-events-none"
               fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <circle cx="11" cy="11" r="8" />
            <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-4.35-4.35" />
          </svg>
          <input
            ref={searchRef}
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Buscar por nome ou e-mail…"
            className="w-full pl-9 pr-3.5 py-2 rounded-xl text-sm border border-stone-800/80 text-stone-300 placeholder-stone-700 focus:outline-none focus:border-amber-500/30 focus:ring-1 focus:ring-amber-500/15 transition-all"
            style={{ background: '#0d0b08' }}
          />
        </div>

        {/* Filtros por cargo */}
        <div className="mt-3 flex gap-1.5 flex-wrap">
          {FILTERS.map(f => (
            <button
              key={f.key}
              onClick={() => setFilter(f.key)}
              className="px-3 py-1 rounded-full text-xs font-medium transition-colors"
              style={{
                background: filter === f.key ? 'rgba(245,158,11,0.15)' : 'rgba(255,255,255,0.04)',
                color: filter === f.key ? '#F59E0B' : '#78716c',
                border: `1px solid ${filter === f.key ? 'rgba(245,158,11,0.3)' : 'rgba(255,255,255,0.06)'}`,
              }}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>

      {/* Grid */}
      <div className="flex-1 overflow-y-auto p-4">
        {loading ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="h-40 rounded-2xl animate-pulse" style={{ background: '#161210' }} />
            ))}
          </div>
        ) : filtered.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-20 text-center">
            <div
              className="w-12 h-12 rounded-2xl border border-stone-800/50 flex items-center justify-center mb-3"
              style={{ background: '#161210' }}
            >
              <svg className="w-5 h-5 text-stone-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                <path strokeLinecap="round" strokeLinejoin="round"
                  d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z" />
              </svg>
            </div>
            <p className="text-stone-500 text-sm">
              {search ? 'Nenhum resultado para esta busca' : 'Nenhum membro encontrado'}
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
            {filtered.map(u => (
              <UserCard
                key={u.id}
                user={u}
                currentUserId={currentUser.id}
                canEdit={canEdit}
                onEdit={setEditUser}
                onPassword={setPwUser}
                onDeactivate={handleDeactivate}
              />
            ))}
          </div>
        )}
      </div>

      {/* Modais */}
      {editUser !== undefined && (
        <UserModal
          user={editUser}
          currentUserRole={currentUser.role as UserRole}
          onClose={() => setEditUser(undefined)}
          onSaved={handleSaved}
        />
      )}
      {pwUser && (
        <PasswordModal user={pwUser} onClose={() => setPwUser(null)} />
      )}
    </div>
  )
}
