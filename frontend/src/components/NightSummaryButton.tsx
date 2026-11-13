import { useState } from 'react'
import { getUser, sendNightSummary } from '../lib/api'

/**
 * "Enviar resumo da noite" no Telegram — pra usar ao fechar o bar. Manda tudo
 * da noite atual (das 6h até agora) e o envio automático das 6h não repete.
 * Só dono/gerente (o servidor confere também).
 */
export default function NightSummaryButton() {
  const role = getUser()?.role
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null)

  if (role !== 'owner' && role !== 'manager') return null

  async function send() {
    if (busy) return
    setBusy(true)
    setMsg(null)
    try {
      await sendNightSummary()
      setMsg({ ok: true, text: 'Resumo enviado no Telegram. Às 6h não vai de novo.' })
    } catch (err) {
      setMsg({ ok: false, text: err instanceof Error ? err.message : 'Não deu pra enviar.' })
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="mb-4">
      <button onClick={send} disabled={busy}
        className="w-full sm:w-auto h-11 px-4 inline-flex items-center justify-center gap-2 rounded-xl text-sm font-semibold
                   border border-sky-500/30 bg-sky-500/10 text-sky-400 hover:bg-sky-500/20 disabled:opacity-50 transition-colors">
        <span aria-hidden>📊</span>
        {busy ? 'Enviando…' : 'Fechou o bar? Enviar resumo da noite'}
      </button>
      {msg && (
        <p role="status" className={['mt-2 text-xs', msg.ok ? 'text-green-400' : 'text-red-400'].join(' ')}>
          {msg.text}
        </p>
      )}
    </div>
  )
}
