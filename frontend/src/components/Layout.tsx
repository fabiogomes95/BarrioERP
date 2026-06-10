import { useState, useRef, useEffect } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import { clearToken, getUser } from '../lib/api'

/**
 * Shell da aplicação.
 *
 * Estrutura:
 *   ┌──────────────────────────────────────┐
 *   │ [≡]  [  Pedidos  ] [  Mesas  ]       │  ← barra de abas
 *   ├──────────────────────────────────────┤
 *   │           <Outlet />                 │  ← conteúdo da aba ativa
 *   └──────────────────────────────────────┘
 *
 * Abas principais (sempre visíveis): Pedidos, Mesas
 * Menu suspenso (≡, canto esquerdo): Cardápio, Equipe, Sair
 */

// Ícone lista (Pedidos)
function IconList() {
  return (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
    </svg>
  )
}

// Ícone mesa/restaurante (Mesas)
function IconTable() {
  return (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M3 10h18M3 10V6a1 1 0 011-1h16a1 1 0 011 1v4M3 10l2 10h14l2-10" />
    </svg>
  )
}

function DropdownMenu() {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  const user = getUser()

  useEffect(() => {
    function onClickOutside(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', onClickOutside)
    return () => document.removeEventListener('mousedown', onClickOutside)
  }, [])

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen(v => !v)}
        className="flex items-center justify-center w-9 h-9 rounded-lg text-gray-400
                   hover:text-white hover:bg-gray-800 transition-colors"
        aria-label="Menu"
      >
        <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M4 6h16M4 12h16M4 18h16" />
        </svg>
      </button>

      {open && (
        <div className="absolute left-0 top-11 z-50 w-48 bg-gray-900 border border-gray-800
                        rounded-xl shadow-xl overflow-hidden">

          {/* Usuário no topo do dropdown */}
          <div className="px-4 py-3 border-b border-gray-800">
            <p className="text-sm text-white font-medium">{user?.name}</p>
            <p className="text-xs text-gray-500 capitalize">{user?.role}</p>
          </div>

          {/* Navegação secundária */}
          {[
            { to: '/cardapio', label: 'Cardápio' },
            { to: '/equipe',   label: 'Equipe'   },
          ].map(item => (
            <NavLink
              key={item.to}
              to={item.to}
              onClick={() => setOpen(false)}
              className={({ isActive }) =>
                [
                  'block px-4 py-3 text-sm transition-colors',
                  isActive
                    ? 'bg-indigo-600/20 text-indigo-400'
                    : 'text-gray-300 hover:bg-gray-800 hover:text-white',
                ].join(' ')
              }
            >
              {item.label}
            </NavLink>
          ))}

          {/* Sair */}
          <div className="border-t border-gray-800">
            <button
              onClick={() => { clearToken(); window.location.href = '/login' }}
              className="w-full text-left px-4 py-3 text-sm text-red-400 hover:bg-gray-800 transition-colors"
            >
              Sair
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

// Estilo da aba ativa: borda inferior indigo, texto branco
// Estilo inativo: texto cinza, sem borda
const tabClass = ({ isActive }: { isActive: boolean }) =>
  [
    'flex items-center gap-2 px-6 py-3 text-sm font-medium border-b-2 transition-colors whitespace-nowrap',
    isActive
      ? 'border-indigo-500 text-white'
      : 'border-transparent text-gray-400 hover:text-white hover:border-gray-600',
  ].join(' ')

export default function Layout() {
  return (
    <div className="flex flex-col h-screen bg-gray-950">

      {/* ── Barra de navegação ─────────────────────────────────────────── */}
      <nav className="bg-gray-900 border-b border-gray-800 flex items-center shrink-0">

        {/* Menu suspenso — lado esquerdo */}
        <div className="px-2">
          <DropdownMenu />
        </div>

        {/* Abas principais */}
        <NavLink to="/pedidos" className={tabClass}>
          <IconList />
          Pedidos
        </NavLink>

        <NavLink to="/mesas" className={tabClass}>
          <IconTable />
          Mesas
        </NavLink>

      </nav>

      {/* ── Conteúdo da aba ativa ──────────────────────────────────────── */}
      <main className="flex-1 overflow-auto">
        <Outlet />
      </main>

    </div>
  )
}
