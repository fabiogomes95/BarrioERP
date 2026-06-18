import { useState, type FormEvent } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { login } from '../lib/api'

export default function LoginPage() {
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      await login(email, password)
      navigate('/', { replace: true })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro ao conectar com o servidor')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div
      className="min-h-screen flex items-center justify-center p-4"
      style={{ background: '#0d0b08' }}
    >
      {/* Glow de fundo sutil */}
      <div
        className="absolute inset-0 pointer-events-none"
        style={{
          background:
            'radial-gradient(ellipse 60% 40% at 50% -10%, rgba(180,100,10,0.12) 0%, transparent 70%)',
        }}
      />

      <div className="relative w-full max-w-[340px]">

        {/* Marca */}
        <div className="text-center mb-10 select-none">
          <div
            className="inline-flex items-center justify-center w-12 h-12 rounded-2xl
                        border border-amber-500/20 mb-4 text-xl"
            style={{ background: 'rgba(245,158,11,0.07)' }}
          >
            🍺
          </div>
          <h1 className="text-xl font-bold text-stone-100 tracking-tight">BarrioERP</h1>
          <p className="text-stone-600 text-xs mt-1">Gestão de bares e restaurantes</p>
        </div>

        {/* Card */}
        <div
          className="rounded-2xl border border-stone-800/70 p-6"
          style={{ background: '#121009' }}
        >
          <p className="text-stone-300 text-sm font-semibold mb-5">Entrar na sua conta</p>

          {error && (
            <div className="flex items-start gap-2.5 bg-red-500/8 border border-red-500/20
                            text-red-400 text-xs rounded-xl px-3.5 py-3 mb-4">
              <svg className="w-3.5 h-3.5 mt-0.5 shrink-0" fill="none" viewBox="0 0 24 24"
                   stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round"
                      d="M12 9v4m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" />
              </svg>
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-3.5">
            <div>
              <label htmlFor="email"
                     className="block text-[11px] font-semibold text-stone-500 uppercase tracking-wider mb-1.5">
                E-mail
              </label>
              <input
                id="email"
                type="email"
                required
                autoComplete="email"
                value={email}
                onChange={e => setEmail(e.target.value)}
                placeholder="voce@seubar.com"
                disabled={loading}
                className="w-full rounded-xl px-3.5 py-2.5 text-sm
                           border border-stone-800/80 text-stone-100 placeholder-stone-700
                           focus:outline-none focus:border-amber-500/40 focus:ring-1 focus:ring-amber-500/20
                           disabled:opacity-40 transition-all"
                style={{ background: '#0d0b08' }}
              />
            </div>

            <div>
              <label htmlFor="password"
                     className="block text-[11px] font-semibold text-stone-500 uppercase tracking-wider mb-1.5">
                Senha
              </label>
              <input
                id="password"
                type="password"
                required
                autoComplete="current-password"
                value={password}
                onChange={e => setPassword(e.target.value)}
                placeholder="••••••••"
                disabled={loading}
                className="w-full rounded-xl px-3.5 py-2.5 text-sm
                           border border-stone-800/80 text-stone-100 placeholder-stone-700
                           focus:outline-none focus:border-amber-500/40 focus:ring-1 focus:ring-amber-500/20
                           disabled:opacity-40 transition-all"
                style={{ background: '#0d0b08' }}
              />
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full mt-1 py-2.5 rounded-xl text-sm font-semibold
                         bg-amber-500 hover:bg-amber-400 active:bg-amber-600
                         text-stone-900 disabled:opacity-40 disabled:cursor-not-allowed
                         transition-colors duration-150"
            >
              {loading ? 'Entrando…' : 'Entrar'}
            </button>
          </form>
        </div>

        {/* Criar conta */}
        <p className="text-center text-stone-600 text-xs mt-5">
          Ainda não tem um bar cadastrado?{' '}
          <Link to="/register" className="text-amber-500/80 hover:text-amber-400 font-semibold transition-colors">
            Criar agora
          </Link>
        </p>
      </div>
    </div>
  )
}
