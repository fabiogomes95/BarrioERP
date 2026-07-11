import { useEffect, type ReactNode } from 'react'
import { NavLink } from 'react-router-dom'

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
      <div className="w-full max-w-md rounded-3xl border border-stone-800/70 p-5"
           style={{ background: '#161210' }}
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
    <div className="flex gap-1 p-1 rounded-xl mb-4 w-fit" style={{ background: '#0d0b08' }}>
      <NavLink to="/admin" end className={tabCls}>Geral</NavLink>
      <NavLink to="/equipe" className={tabCls}>Equipe</NavLink>
      <NavLink to="/auditoria" className={tabCls}>Auditoria</NavLink>
    </div>
  )
}

export function Spinner({ text }: { text?: string }) {
  return (
    <div className="text-center py-16 text-stone-600 text-sm">{text ?? 'Carregando...'}</div>
  )
}
