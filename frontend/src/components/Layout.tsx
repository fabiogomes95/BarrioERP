import { useState, useRef, useEffect } from 'react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { clearToken, getUser } from '../lib/api'

// ── Ícones ────────────────────────────────────────────────────────────────────

function IconTable() {
  return (
    <svg className="w-[18px] h-[18px]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.75}>
      <path strokeLinecap="round" strokeLinejoin="round"
        d="M3 7h18M5 7v10M19 7v10M3 12h18" />
    </svg>
  )
}

function IconClipboard() {
  return (
    <svg className="w-[18px] h-[18px]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.75}>
      <path strokeLinecap="round" strokeLinejoin="round"
        d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7
           a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2
           M9 5a2 2 0 012-2h2a2 2 0 012 2" />
    </svg>
  )
}

function IconBook() {
  return (
    <svg className="w-[18px] h-[18px]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.75}>
      <path strokeLinecap="round" strokeLinejoin="round"
        d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477
           3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253
           m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253
           v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
    </svg>
  )
}

function IconUsers() {
  return (
    <svg className="w-[18px] h-[18px]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.75}>
      <path strokeLinecap="round" strokeLinejoin="round"
        d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10
           0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3
           0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857
           m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z" />
    </svg>
  )
}

function IconLogout() {
  return (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.75}>
      <path strokeLinecap="round" strokeLinejoin="round"
        d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3
           3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
    </svg>
  )
}

// ── Itens de navegação ────────────────────────────────────────────────────────

const NAV = [
  { to: '/mesas',    label: 'Mesas',    Icon: IconTable },
  { to: '/pedidos',  label: 'Pedidos',  Icon: IconClipboard },
  { to: '/cardapio', label: 'Cardápio', Icon: IconBook },
  { to: '/equipe',   label: 'Equipe',   Icon: IconUsers },
]

function userInitials(name?: string) {
  if (!name) return '?'
  return name.split(' ').slice(0, 2).map(n => n[0]).join('').toUpperCase()
}

// ── Sidebar (desktop md+) ─────────────────────────────────────────────────────

function Sidebar() {
  const user = getUser()
  const navigate = useNavigate()

  return (
    <aside
      className="hidden md:flex flex-col w-56 shrink-0 border-r border-stone-800/50"
      style={{ background: '#0f0d0a' }}
    >
      {/* Marca */}
      <div className="px-5 py-5 border-b border-stone-800/50">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-amber-500/10 border border-amber-500/20
                          flex items-center justify-center shrink-0 text-base">
            🍺
          </div>
          <div className="min-w-0">
            {/* TODO: nome do estabelecimento via API */}
            <p className="text-stone-100 text-sm font-semibold leading-tight truncate">
              BarrioERP
            </p>
            <p className="text-stone-600 text-[11px] mt-0.5">Gestão do bar</p>
          </div>
        </div>
      </div>

      {/* Navegação */}
      <nav className="flex-1 p-3 space-y-0.5 overflow-y-auto">
        {NAV.map(({ to, label, Icon }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              [
                'group flex items-center gap-3 px-3 py-2.5 rounded-lg',
                'text-sm font-medium transition-all duration-150',
                isActive
                  ? 'bg-amber-500/10 text-amber-400'
                  : 'text-stone-500 hover:text-stone-200 hover:bg-stone-800/50',
              ].join(' ')
            }
          >
            {({ isActive }) => (
              <>
                <span className={isActive ? 'text-amber-400' : 'text-stone-600 group-hover:text-stone-400 transition-colors'}>
                  <Icon />
                </span>
                {label}
                {isActive && (
                  <span className="ml-auto w-1.5 h-1.5 rounded-full bg-amber-500" />
                )}
              </>
            )}
          </NavLink>
        ))}
      </nav>

      {/* Perfil + Sair */}
      <div className="p-3 border-t border-stone-800/50">
        <div className="flex items-center gap-2.5 px-2 py-2 rounded-lg">
          <div className="w-7 h-7 rounded-full bg-amber-500/15 border border-amber-500/25
                          flex items-center justify-center shrink-0">
            <span className="text-[11px] font-bold text-amber-400">{userInitials(user?.name)}</span>
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-stone-200 text-xs font-semibold truncate leading-tight">{user?.name}</p>
            <p className="text-stone-600 text-[10px] capitalize mt-0.5">{user?.role}</p>
          </div>
          <button
            onClick={() => { clearToken(); navigate('/login', { replace: true }) }}
            className="text-stone-700 hover:text-red-400 transition-colors p-1 rounded"
            title="Sair"
          >
            <IconLogout />
          </button>
        </div>
      </div>
    </aside>
  )
}

// ── Header mobile ─────────────────────────────────────────────────────────────

function MobileHeader() {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  const user = getUser()
  const navigate = useNavigate()

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  return (
    <header
      className="md:hidden flex items-center justify-between px-4 h-14 shrink-0 border-b border-stone-800/50"
      style={{ background: '#161210' }}
    >
      {/* Marca */}
      <div className="flex items-center gap-2.5">
        <span className="text-base">🍺</span>
        <span className="text-stone-200 text-sm font-bold tracking-tight">BarrioERP</span>
      </div>

      {/* Avatar com menu */}
      <div ref={ref} className="relative">
        <button
          onClick={() => setOpen(v => !v)}
          className="w-8 h-8 rounded-full bg-amber-500/15 border border-amber-500/25
                     flex items-center justify-center active:scale-95 transition-transform"
        >
          <span className="text-[11px] font-bold text-amber-400">{userInitials(user?.name)}</span>
        </button>

        {open && (
          <div className="absolute right-0 top-10 z-50 w-48
                          bg-stone-900 border border-stone-700/50 rounded-2xl
                          shadow-2xl shadow-black/60 overflow-hidden">
            <div className="px-4 py-3 border-b border-stone-800/80">
              <p className="text-sm text-stone-100 font-semibold leading-tight">{user?.name}</p>
              <p className="text-xs text-amber-500/70 capitalize mt-0.5">{user?.role}</p>
            </div>
            <button
              onClick={() => { clearToken(); navigate('/login', { replace: true }) }}
              className="w-full flex items-center gap-3 px-4 py-3 text-sm
                         text-red-400/70 hover:bg-stone-800/60 hover:text-red-400
                         transition-colors"
            >
              <IconLogout />
              Sair
            </button>
          </div>
        )}
      </div>
    </header>
  )
}

// ── Bottom nav (mobile) ───────────────────────────────────────────────────────

function BottomNav() {
  return (
    <nav
      className="md:hidden fixed bottom-0 left-0 right-0 flex items-stretch
                 border-t border-stone-800/50 z-20 safe-area-inset-bottom"
      style={{ background: '#161210' }}
    >
      {NAV.map(({ to, label, Icon }) => (
        <NavLink
          key={to}
          to={to}
          className={({ isActive }) =>
            [
              'flex-1 flex flex-col items-center justify-center gap-1 py-2.5',
              'transition-colors duration-150 select-none',
              isActive ? 'text-amber-400' : 'text-stone-600 active:text-stone-300',
            ].join(' ')
          }
        >
          {({ isActive }) => (
            <>
              <span className={isActive ? 'drop-shadow-[0_0_6px_rgba(245,158,11,0.5)]' : ''}>
                <Icon />
              </span>
              <span className="text-[10px] font-semibold tracking-wide">{label}</span>
              {isActive && <span className="absolute bottom-0 w-8 h-0.5 rounded-full bg-amber-500" />}
            </>
          )}
        </NavLink>
      ))}
    </nav>
  )
}

// ── Layout principal ──────────────────────────────────────────────────────────

export default function Layout() {
  return (
    <div className="flex h-screen" style={{ background: '#0d0b08' }}>

      {/* Sidebar — visível apenas desktop */}
      <Sidebar />

      {/* Área principal */}
      <div className="flex flex-col flex-1 min-w-0 overflow-hidden">

        {/* Header — visível apenas mobile */}
        <MobileHeader />

        {/* Conteúdo da rota ativa */}
        <main className="flex-1 overflow-auto pb-16 md:pb-0">
          <Outlet />
        </main>
      </div>

      {/* Bottom nav — visível apenas mobile */}
      <BottomNav />
    </div>
  )
}
