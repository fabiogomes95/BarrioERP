import { useEffect, useState, type ReactNode } from 'react'
import { NavLink } from 'react-router-dom'
import { getEffectiveTheme, setTheme, type Theme } from '../lib/theme'

export const inputCls = `w-full rounded-xl px-3.5 py-2.5 text-sm border border-stone-800/80
  text-stone-100 placeholder-stone-700 focus:outline-none transition-all
  focus:border-amber-500/40 focus:ring-1 focus:ring-amber-500/20`.replace(/\s+/g, ' ')

export function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <div>
      <label className="block text-[11px] font-semibold text-stone-500 uppercase tracking-wider mb-1.5">
        {label}
      </label>
      {children}
      {hint && <p className="text-stone-700 text-[10px] mt-1">{hint}</p>}
    </div>
  )
}

export function ModalOverlay({ title, onClose, children }: {
  title?: string; onClose: () => void; children: ReactNode
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
      <div className="w-full max-w-md rounded-3xl border border-stone-800/70 p-5
                      max-h-[85dvh] overflow-y-auto overscroll-contain"
           style={{ background: 'var(--color-app-surface)' }}
           onClick={e => e.stopPropagation()}>
        {title && (
          <div className="flex items-center justify-between mb-5">
            <h2 className="text-stone-100 text-base font-bold">{title}</h2>
            <button onClick={onClose} className="text-stone-600 hover:text-stone-400 transition-colors p-1">
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        )}
        {children}
      </div>
    </div>
  )
}

export function QtyStepper({ value, onChange, min = 1, max = 99 }: {
  value: number; onChange: (v: number) => void; min?: number; max?: number
}) {
  return (
    <div className="flex items-center gap-2.5">
      <button type="button" onClick={() => onChange(Math.max(min, value - 1))} disabled={value <= min}
        className="w-10 h-10 flex items-center justify-center rounded-xl border border-stone-700/60
                   text-stone-300 hover:bg-stone-800/60 active:scale-95 disabled:opacity-30 transition-all">
        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
          <path strokeLinecap="round" d="M5 12h14" />
        </svg>
      </button>
      <span className="text-stone-100 text-base font-bold w-8 text-center tabular-nums">{value}</span>
      <button type="button" onClick={() => onChange(Math.min(max, value + 1))} disabled={value >= max}
        className="w-10 h-10 flex items-center justify-center rounded-xl border border-stone-700/60
                   text-stone-300 hover:bg-stone-800/60 active:scale-95 disabled:opacity-30 transition-all">
        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
          <path strokeLinecap="round" d="M12 5v14M5 12h14" />
        </svg>
      </button>
    </div>
  )
}

export function ErrorBanner({ message, onRetry, onDismiss }: {
  message: string; onRetry?: () => void; onDismiss?: () => void
}) {
  return (
    <div className="flex items-center gap-3 bg-red-500/10 border border-red-500/20
                    text-red-400 text-sm rounded-2xl px-4 py-3 mb-4">
      {message}
      {onRetry && (
        <button onClick={onRetry} className="ml-auto text-xs underline underline-offset-2">
          Tentar novamente
        </button>
      )}
      {onDismiss && (
        <button onClick={onDismiss} className="ml-2 text-xs underline underline-offset-2">
          Fechar
        </button>
      )}
    </div>
  )
}

export function AdminTabs() {
  const tabCls = ({ isActive }: { isActive: boolean }) =>
    [
      'px-3.5 py-1.5 rounded-lg text-sm font-semibold transition-colors',
      isActive ? 'bg-amber-500/15 text-amber-400' : 'text-stone-500 hover:text-stone-300',
    ].join(' ')
  return (
    <div className="flex gap-1 p-1 rounded-xl mb-4 w-fit" style={{ background: 'var(--color-app-bg)' }}>
      <NavLink to="/admin" end className={tabCls}>Geral</NavLink>
      <NavLink to="/equipe" className={tabCls}>Equipe</NavLink>
      <NavLink to="/auditoria" className={tabCls}>Auditoria</NavLink>
    </div>
  )
}

/** Botão sol/lua — alterna e lembra o tema claro/escuro (localStorage). */
export function ThemeToggle({ className }: { className?: string }) {
  const [theme, setThemeState] = useState<Theme>(getEffectiveTheme())

  function toggle() {
    const next: Theme = theme === 'dark' ? 'light' : 'dark'
    setTheme(next)
    setThemeState(next)
  }

  return (
    <button
      onClick={toggle}
      title={theme === 'dark' ? 'Mudar para modo claro' : 'Mudar para modo escuro'}
      className={[
        'flex items-center justify-center w-8 h-8 rounded-lg transition-colors',
        'text-stone-500 hover:text-amber-400 hover:bg-stone-800/50',
        className ?? '',
      ].join(' ')}
    >
      {theme === 'dark' ? (
        <svg className="w-[18px] h-[18px]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.75}>
          <path strokeLinecap="round" strokeLinejoin="round"
            d="M12 3v1.5m0 15V21m9-9h-1.5M4.5 12H3m15.36 6.36-1.06-1.06M6.7 6.7 5.64 5.64m12.72 0-1.06 1.06M6.7 17.3l-1.06 1.06M16 12a4 4 0 11-8 0 4 4 0 018 0z" />
        </svg>
      ) : (
        <svg className="w-[18px] h-[18px]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.75}>
          <path strokeLinecap="round" strokeLinejoin="round"
            d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z" />
        </svg>
      )}
    </button>
  )
}

export function Spinner({ text }: { text?: string }) {
  return (
    <div className="text-center py-16 text-stone-600 text-sm">{text ?? 'Carregando...'}</div>
  )
}
