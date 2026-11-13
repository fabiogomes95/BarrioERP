import { useEffect, useState } from 'react'
import {
  fetchOnlineOrdersPause, setOnlineOrdersPause, fetchDayNotice, setDayNotice, type DayNotice,
} from '../lib/api'
import { Field, ModalOverlay } from './ui'
import { inputCls } from '../lib/styles'

const LAST_NOTICE_KEY = 'barrio:last-day-notice'

/**
 * Controles do cardápio online (fica na tela Cardápio):
 *  - pausar/retomar os pedidos pelo site (pausado, o cliente finaliza pelo WhatsApp);
 *  - aviso do dia ("Hoje sem delivery: só bebidas e churrasco na brasa"),
 *    com opção de desligar a entrega. O aviso vale até as 5h e some sozinho.
 */
export default function OnlineMenuControls() {
  const [paused, setPaused] = useState<boolean | null>(null)
  const [notice, setNotice] = useState<DayNotice | null>(null)
  const [busy, setBusy] = useState(false)
  const [editing, setEditing] = useState(false)
  const [text, setText] = useState('')
  const [noDelivery, setNoDelivery] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const load = () => {
      fetchOnlineOrdersPause().then(setPaused).catch(() => {})
      fetchDayNotice().then(setNotice).catch(() => {})
    }
    load()
    const id = setInterval(load, 60_000)  // outro aparelho pode ter mudado / aviso venceu às 5h
    return () => clearInterval(id)
  }, [])

  async function togglePause() {
    if (paused === null || busy) return
    setBusy(true)
    try { setPaused(await setOnlineOrdersPause(!paused)) } catch { /* mantém o estado atual */ }
    finally { setBusy(false) }
  }

  function openEditor() {
    let last = ''
    try { last = localStorage.getItem(LAST_NOTICE_KEY) ?? '' } catch { /* sem storage */ }
    setText(notice?.active ? notice.text : last)
    setNoDelivery(notice?.active ? notice.no_delivery : false)
    setError(null)
    setEditing(true)
  }

  async function saveNotice(t: string, nd: boolean) {
    setBusy(true); setError(null)
    try {
      setNotice(await setDayNotice(t.trim(), nd))
      if (t.trim()) { try { localStorage.setItem(LAST_NOTICE_KEY, t.trim()) } catch { /* ok */ } }
      setEditing(false)
    } catch {
      setError('Não deu pra salvar. Tente de novo.')
    } finally { setBusy(false) }
  }

  if (paused === null && notice === null) return null
  const smallBtn = 'shrink-0 px-2.5 py-1 rounded-lg text-[11px] font-bold disabled:opacity-50 transition-colors'

  return (
    <div className="mt-3 rounded-xl border border-stone-800/70 p-2.5 space-y-2.5"
         style={{ background: 'var(--color-app-bg)' }}>
      <p className="text-[10px] font-bold text-stone-500 uppercase tracking-wider">Cardápio online</p>

      {paused !== null && (
        <div className={['flex items-center gap-2 rounded-lg px-2 py-1.5',
          paused ? 'bg-amber-500/15 border border-amber-500/40' : ''].join(' ')}>
          <span className={['w-2 h-2 rounded-full shrink-0', paused ? 'bg-amber-400' : 'bg-emerald-500'].join(' ')} />
          <p className="flex-1 min-w-0 text-xs text-stone-300 leading-tight">
            Pedidos pelo site:{' '}
            <b className={paused ? 'text-amber-400' : 'text-emerald-400'}>{paused ? 'pausados' : 'recebendo'}</b>
            {paused && <span className="block text-[10px] text-stone-500">Cliente finaliza pelo WhatsApp</span>}
          </p>
          <button onClick={togglePause} disabled={busy}
            className={smallBtn + (paused
              ? ' bg-amber-500 hover:bg-amber-400 text-stone-900'
              : ' bg-stone-800 hover:bg-stone-700 text-stone-300')}>
            {busy ? '...' : paused ? 'Retomar' : 'Pausar'}
          </button>
        </div>
      )}

      {notice !== null && (notice.active ? (
        <div className="rounded-lg px-2 py-1.5 bg-orange-500/10 border border-orange-500/40">
          <p className="text-[10px] font-bold text-orange-400 uppercase tracking-wider">📢 Aviso do dia</p>
          {notice.text && <p className="text-xs text-stone-200 mt-0.5 break-words">{notice.text}</p>}
          {notice.no_delivery && <p className="text-[10px] text-stone-400 mt-0.5">Sem entrega hoje — só retirada.</p>}
          <div className="flex items-center gap-1.5 mt-1.5">
            <span className="flex-1 text-[10px] text-stone-500">Sai sozinho às 5h</span>
            <button onClick={openEditor} disabled={busy} className={smallBtn + ' bg-stone-800 hover:bg-stone-700 text-stone-200'}>
              Editar
            </button>
            <button onClick={() => saveNotice('', false)} disabled={busy}
              className={smallBtn + ' text-stone-400 hover:text-red-400 hover:bg-stone-800/60'}>
              Tirar
            </button>
          </div>
        </div>
      ) : (
        <button onClick={openEditor}
          className="w-full flex items-center gap-1.5 px-2 py-1.5 rounded-lg text-xs font-semibold text-stone-400
                     hover:text-orange-400 hover:bg-stone-800/60 transition-colors">
          📢 Colocar aviso do dia
        </button>
      ))}

      {editing && (
        <ModalOverlay title="Aviso do dia no cardápio" onClose={() => setEditing(false)}>
          <div className="space-y-4">
            <Field label="Mensagem" hint={`Aparece em destaque no topo do cardápio. ${text.length}/280`}>
              <textarea value={text} onChange={e => setText(e.target.value.slice(0, 280))} rows={3} autoFocus
                placeholder="Ex.: Hoje sem delivery: só bebidas (cerveja e destilados) e churrasco na brasa."
                className={inputCls + ' resize-none'} />
            </Field>
            <label className="flex items-start gap-3 cursor-pointer">
              <input type="checkbox" checked={noDelivery} onChange={e => setNoDelivery(e.target.checked)}
                className="mt-0.5 w-4 h-4 accent-orange-500" />
              <span className="text-sm text-stone-200">
                Sem entrega hoje
                <span className="block text-xs text-stone-500">O cardápio tira a opção "Entrega" e deixa só retirada.</span>
              </span>
            </label>
            <p className="text-xs text-stone-500">Vale até as 5h da manhã e some sozinho.</p>
            {error && <p className="text-sm text-red-400">{error}</p>}
            <button onClick={() => saveNotice(text, noDelivery)} disabled={busy || (!text.trim() && !noDelivery)}
              className="w-full py-3 rounded-xl text-sm font-bold bg-orange-500 hover:bg-orange-400 text-stone-900 disabled:opacity-40">
              {busy ? 'Salvando...' : 'Publicar no cardápio'}
            </button>
          </div>
        </ModalOverlay>
      )}
    </div>
  )
}
