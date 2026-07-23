import { useState, useEffect } from 'react'
import { NavLink, Outlet, useNavigate, useLocation } from 'react-router-dom'
import { clearToken, getUser, refreshCompanyName } from '../lib/api'
import { useBillRequestAlerts } from '../lib/notifications'

// ── Ícones ────────────────────────────────────────────────────────────────────

function IconMenu() {
  return (
    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.9}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M4 6h16M4 12h16M4 18h16" />
    </svg>
  )
}

function IconHome() {
  return (
    <svg className="w-[18px] h-[18px]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.75}>
      <path strokeLinecap="round" strokeLinejoin="round"
        d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" />
    </svg>
  )
}

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

function IconCash() {
  return (
    <svg className="w-[18px] h-[18px]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.75}>
      <path strokeLinecap="round" strokeLinejoin="round"
        d="M17 9V7a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2m2 4h10a2 2 0 002-2v-6a2 2 0 00-2-2H9a2 2 0 00-2 2v6a2 2 0 002 2zm7-5a2 2 0 11-4 0 2 2 0 014 0z" />
    </svg>
  )
}

function IconCog() {
  return (
    <svg className="w-[18px] h-[18px]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.75}>
      <path strokeLinecap="round" strokeLinejoin="round"
        d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
    </svg>
  )
}

function IconFiado() {
  return (
    <svg className="w-[18px] h-[18px]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.75}>
      <path strokeLinecap="round" strokeLinejoin="round"
        d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16l3.5-2 3.5 2 3.5-2 3.5 2zM9 12h6M9 8h4" />
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

function IconHistory() {
  return (
    <svg className="w-[18px] h-[18px]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.75}>
      <path strokeLinecap="round" strokeLinejoin="round"
        d="M3 12a9 9 0 109-9 9.75 9.75 0 00-6.74 2.74L3 8M3 3v5h5M12 7v5l3 3" />
    </svg>
  )
}

// ── Itens de navegação ────────────────────────────────────────────────────────

// roles: undefined = visível pra todos; senão, só pros roles listados
const NAV = [
  { to: '/dashboard',  label: 'Início',        Icon: IconHome },
  { to: '/mesas',      label: 'Mesas',         Icon: IconTable },
  { to: '/pedidos',    label: 'Pedidos',       Icon: IconClipboard },
  { to: '/caixa',      label: 'Caixa',         Icon: IconCash,    roles: ['owner', 'manager', 'cashier'] },
  { to: '/fiado',      label: 'Fiado',         Icon: IconFiado },
  { to: '/cardapio',   label: 'Cardápio',      Icon: IconBook },
  { to: '/auditoria',  label: 'Auditoria',     Icon: IconHistory, roles: ['owner', 'manager'] },
  { to: '/admin',      label: 'Administração', Icon: IconCog,     roles: ['owner', 'manager'] },
]

function userInitials(name?: string) {
  if (!name) return '?'
  return name.split(' ').slice(0, 2).map(n => n[0]).join('').toUpperCase()
}

// ── Drawer lateral (recolhível) ─────────────────────────────────────────────────

function SideDrawer({ open, onClose }: { open: boolean; onClose: () => void }) {
  const user = getUser()
  const navigate = useNavigate()
  const location = useLocation()

  // Fecha com Escape
  useEffect(() => {
    const h = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', h)
    return () => document.removeEventListener('keydown', h)
  }, [onClose])

  return (
    <>
      {/* Backdrop */}
      <div
        onClick={onClose}
        className={[
          'fixed inset-0 z-40 transition-opacity duration-200',
          open ? 'opacity-100' : 'opacity-0 pointer-events-none',
        ].join(' ')}
        style={{ background: 'rgba(0,0,0,0.6)', backdropFilter: 'blur(2px)' }}
      />

      {/* Painel */}
      <aside
        className={[
          'fixed top-0 left-0 h-full w-64 z-50 flex flex-col border-r border-stone-800/60',
          'transform transition-transform duration-200 ease-out',
          open ? 'translate-x-0' : '-translate-x-full',
        ].join(' ')}
        style={{ background: '#0f0d0a' }}
      >
        {/* Marca + fechar */}
        <div className="px-5 py-5 border-b border-stone-800/50 flex items-center gap-3">
          <div className="w-9 h-9 rounded-full overflow-hidden shrink-0 ring-1 ring-amber-500/20">
            <img src="/icon-recanto.png" alt="" className="w-full h-full object-cover" />
          </div>
          <div className="min-w-0 flex-1">
            <p className="text-stone-100 text-sm font-semibold leading-tight truncate">{user?.company_name ?? 'BarrioERP'}</p>
            <p className="text-stone-600 text-[11px] mt-0.5">Gestão do bar</p>
          </div>
          <button onClick={onClose}
            className="text-stone-600 hover:text-stone-300 transition-colors p-1 -mr-1" title="Fechar">
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Navegação */}
        <nav className="flex-1 p-3 space-y-0.5 overflow-y-auto">
          {NAV.filter(item => !item.roles || item.roles.includes(user?.role ?? '')).map(({ to, label, Icon }) => {
            const extraActive = to === '/admin' && location.pathname.startsWith('/equipe')
            return (
            <NavLink
              key={to}
              to={to}
              onClick={onClose}
              className={({ isActive }) =>
                [
                  'group flex items-center gap-3 px-3 py-2.5 rounded-lg',
                  'text-sm font-medium transition-all duration-150',
                  isActive || extraActive
                    ? 'bg-amber-500/10 text-amber-400'
                    : 'text-stone-500 hover:text-stone-200 hover:bg-stone-800/50',
                ].join(' ')
              }
            >
              {({ isActive }) => (
                <>
                  <span className={isActive || extraActive ? 'text-amber-400' : 'text-stone-600 group-hover:text-stone-400 transition-colors'}>
                    <Icon />
                  </span>
                  {label}
                  {(isActive || extraActive) && <span className="ml-auto w-1.5 h-1.5 rounded-full bg-amber-500" />}
                </>
              )}
            </NavLink>
          )})}
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
    </>
  )
}

// ── Top bar (hambúrguer) ────────────────────────────────────────────────────────

// Atalhos rápidos sempre visíveis no topo (as telas mais usadas no bar)
const QUICK = [
  { to: '/mesas',   label: 'Mesas',   Icon: IconTable },
  { to: '/pedidos', label: 'Pedidos', Icon: IconClipboard },
]

function TopBar({ onMenu, barName }: { onMenu: () => void; barName: string }) {
  return (
    <header
      className="relative flex items-center gap-2 sm:gap-3 px-2 sm:px-4 h-14 shrink-0 border-b border-stone-800/50"
      style={{ background: '#161210' }}
    >
      <button
        onClick={onMenu}
        className="flex items-center justify-center w-9 h-9 rounded-xl text-stone-300
                   hover:text-amber-400 hover:bg-stone-800/60 active:scale-95 transition-all shrink-0"
        title="Menu"
      >
        <IconMenu />
      </button>

      {/* Marca: no mobile fica no fluxo normal (ícone só, ao lado do menu) pra nunca disputar espaço
          com os atalhos da direita. A partir de sm sobra espaço e ela vira centralizada com o nome. */}
      <img src="/icon-recanto.png" alt={barName}
           className="sm:hidden w-8 h-8 rounded-full shrink-0 object-cover" />
      <div className="hidden sm:flex absolute left-1/2 -translate-x-1/2 items-center gap-2
                      pointer-events-none max-w-[55%]">
        <img src="/icon-recanto.png" alt="" className="w-7 h-7 rounded-full shrink-0 object-cover" />
        <span className="text-stone-100 text-sm font-bold tracking-tight truncate">{barName}</span>
      </div>

      {/* Atalhos: Mesas e Pedidos */}
      <nav className="ml-auto flex items-center gap-1.5">
        {QUICK.map(({ to, label, Icon }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              [
                'flex items-center gap-1.5 px-3 sm:px-4 py-2 rounded-xl text-sm font-semibold transition-all',
                isActive
                  ? 'bg-amber-500/15 text-amber-400 border border-amber-500/30'
                  : 'text-stone-400 border border-stone-800/60 hover:text-stone-200 hover:border-stone-700/60',
              ].join(' ')
            }
          >
            <Icon />
            {label}
          </NavLink>
        ))}
      </nav>
    </header>
  )
}

// ── Layout principal ──────────────────────────────────────────────────────────

function BillRequestToasts() {
  const { alerts, dismiss } = useBillRequestAlerts()
  const navigate = useNavigate()

  if (alerts.length === 0) return null

  return (
    <div className="fixed top-3 right-3 z-[100] flex flex-col gap-2 w-[calc(100%-1.5rem)] max-w-sm">
      {alerts.map(a => (
        <div key={a.id}
          className="flex items-center gap-3 rounded-xl border border-orange-500/30 shadow-lg px-3.5 py-3"
          style={{ background: '#1a1410' }}>
          <div className="w-9 h-9 rounded-full bg-orange-500/15 flex items-center justify-center shrink-0">
            <svg className="w-5 h-5 text-orange-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.9}>
              <path strokeLinecap="round" strokeLinejoin="round"
                d="M15 17h5l-1.4-1.4A2 2 0 0118 14.2V11a6 6 0 10-12 0v3.2a2 2 0 01-.6 1.4L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
            </svg>
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-stone-100 text-sm font-semibold">Conta solicitada</p>
            <p className="text-stone-400 text-xs truncate">{a.tableLabel || `Mesa ${a.tableNumber}`}</p>
          </div>
          <button
            onClick={() => { dismiss(a.id); navigate(`/comanda/${a.orderId}`) }}
            className="text-xs font-semibold text-amber-400 hover:text-amber-300 px-2 py-1 shrink-0">
            Ver
          </button>
          <button
            onClick={() => dismiss(a.id)}
            aria-label="Dispensar"
            className="text-stone-500 hover:text-stone-300 shrink-0">
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
      ))}
    </div>
  )
}

export default function Layout() {
  const [open, setOpen] = useState(false)
  const [barName, setBarName] = useState(getUser()?.company_name ?? 'BarrioERP')

  // Busca o nome do bar do backend (funciona mesmo com token antigo sem o nome)
  useEffect(() => {
    refreshCompanyName().then(name => { if (name) setBarName(name) }).catch(() => {})
  }, [])

  return (
    <div className="flex flex-col h-screen" style={{ background: '#0d0b08' }}>
      {/* Barra superior com o menu hambúrguer */}
      <TopBar onMenu={() => setOpen(true)} barName={barName} />

      {/* Drawer lateral recolhível */}
      <SideDrawer open={open} onClose={() => setOpen(false)} />

      {/* Alerta em tempo real: mesa solicitou a conta (som + toast) */}
      <BillRequestToasts />

      {/* Conteúdo da rota ativa */}
      <main className="flex-1 overflow-auto min-h-0">
        <Outlet />
      </main>
    </div>
  )
}
