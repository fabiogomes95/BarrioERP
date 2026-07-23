import { useState, useEffect, useCallback } from 'react'
import {
  type BarSettings,
  fetchSettings, updateSettings, getUser, updateLocalCompanyName, changeMyPassword,
} from '../lib/api'
import { inputCls, Field, AdminTabs } from '../components/ui'

function ChangePasswordCard() {
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [confirm, setConfirm] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [ok, setOk] = useState(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null); setOk(false)
    if (next.length < 6) { setError('A nova senha precisa ter pelo menos 6 caracteres'); return }
    if (next !== confirm) { setError('A confirmação não bate com a nova senha'); return }
    setSaving(true)
    try {
      await changeMyPassword(current, next)
      setCurrent(''); setNext(''); setConfirm('')
      setOk(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro ao trocar senha')
    } finally {
      setSaving(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4 rounded-2xl border border-stone-800/60 p-5 mt-5"
          style={{ background: 'var(--color-app-surface)' }}>
      <h2 className="text-stone-200 text-sm font-bold">Minha senha</h2>

      {error && (
        <div className="bg-red-500/10 border border-red-500/20 text-red-400 text-sm rounded-xl px-3 py-2">{error}</div>
      )}
      {ok && (
        <div className="bg-green-500/10 border border-green-500/20 text-green-400 text-sm rounded-xl px-3 py-2">
          Senha alterada ✓
        </div>
      )}

      <Field label="Senha atual">
        <input type="password" required value={current} autoComplete="current-password"
          onChange={e => setCurrent(e.target.value)} className={inputCls} style={{ background: 'var(--color-app-bg)' }} />
      </Field>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Nova senha">
          <input type="password" required value={next} autoComplete="new-password"
            onChange={e => setNext(e.target.value)} className={inputCls} style={{ background: 'var(--color-app-bg)' }} />
        </Field>
        <Field label="Confirmar nova senha">
          <input type="password" required value={confirm} autoComplete="new-password"
            onChange={e => setConfirm(e.target.value)} className={inputCls} style={{ background: 'var(--color-app-bg)' }} />
        </Field>
      </div>
      <button type="submit" disabled={saving}
        className="w-full py-2.5 rounded-xl text-sm font-semibold text-stone-300 border border-stone-700/60
                   hover:bg-stone-800/50 disabled:opacity-40 transition-colors">
        {saving ? 'Salvando…' : 'Trocar senha'}
      </button>
    </form>
  )
}

export default function AdminPage() {
  const role = getUser()?.role
  const canEdit = role === 'owner' || role === 'manager'
  const [name, setName] = useState('')
  const [phone, setPhone] = useState('')
  const [address, setAddress] = useState('')
  const [fee, setFee] = useState('0')
  const [estName, setEstName] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [ok, setOk] = useState(false)

  const apply = useCallback((s: BarSettings) => {
    setName(s.company_name)
    setPhone(s.company_phone ?? '')
    setAddress(s.address ?? '')
    setFee(String(Number(s.service_fee_percent)))
    setEstName(s.establishment_name)
  }, [])

  useEffect(() => {
    fetchSettings()
      .then(apply)
      .catch(err => setError(err instanceof Error ? err.message : 'Erro ao carregar'))
      .finally(() => setLoading(false))
  }, [apply])

  async function handleSave(e: React.FormEvent) {
    e.preventDefault()
    setError(null); setOk(false); setSaving(true)
    try {
      const s = await updateSettings({
        company_name: name.trim(),
        company_phone: phone.trim() || null,
        address: address.trim() || null,
        service_fee_percent: Number(fee.replace(',', '.')) || 0,
      })
      apply(s)
      updateLocalCompanyName(s.company_name)
      setOk(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro ao salvar')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="h-full overflow-y-auto">
      <div className="max-w-xl mx-auto px-4 sm:px-6 py-6">
        <div className="mb-4">
          <h1 className="text-stone-100 text-xl font-bold leading-tight">Administração</h1>
          <p className="text-stone-500 text-sm mt-1">Dados do bar, taxa de serviço e equipe</p>
        </div>

        <AdminTabs />

        {error && (
          <div className="bg-red-500/10 border border-red-500/20 text-red-400 text-sm rounded-2xl px-4 py-3 mb-4">{error}</div>
        )}
        {ok && (
          <div className="bg-green-500/10 border border-green-500/20 text-green-400 text-sm rounded-2xl px-4 py-3 mb-4">
            Configurações salvas ✓
          </div>
        )}

        {loading ? (
          <div className="text-center py-16 text-stone-600 text-sm">Carregando…</div>
        ) : (
          <form onSubmit={handleSave} className="space-y-4 rounded-2xl border border-stone-800/60 p-5"
                style={{ background: 'var(--color-app-surface)' }}>
            <Field label="Nome do bar">
              <input type="text" required value={name} disabled={!canEdit}
                onChange={e => setName(e.target.value)} className={inputCls} style={{ background: 'var(--color-app-bg)' }} />
            </Field>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Telefone">
                <input type="tel" value={phone} disabled={!canEdit}
                  onChange={e => setPhone(e.target.value)} placeholder="(11) 99999-0000"
                  className={inputCls} style={{ background: 'var(--color-app-bg)' }} />
              </Field>
              <Field label="Taxa de serviço (%)" hint="Ex: 10. Aplicada a novas comandas.">
                <input type="number" min={0} max={100} step="0.5" value={fee} disabled={!canEdit}
                  onChange={e => setFee(e.target.value)} className={inputCls} style={{ background: 'var(--color-app-bg)' }} />
              </Field>
            </div>
            <Field label="Endereço">
              <input type="text" value={address} disabled={!canEdit}
                onChange={e => setAddress(e.target.value)} placeholder="Rua, número, bairro"
                className={inputCls} style={{ background: 'var(--color-app-bg)' }} />
            </Field>
            <p className="text-stone-700 text-[11px]">Unidade: {estName}</p>

            {canEdit ? (
              <button type="submit" disabled={saving}
                className="w-full py-2.5 rounded-xl text-sm font-semibold bg-amber-500 hover:bg-amber-400
                           text-stone-900 disabled:opacity-40 transition-colors">
                {saving ? 'Salvando…' : 'Salvar'}
              </button>
            ) : (
              <p className="text-stone-600 text-xs text-center">Apenas o dono ou gerente pode editar.</p>
            )}
          </form>
        )}

        <p className="text-stone-700 text-[11px] mt-4">
          A taxa de serviço só vale para comandas <b>abertas após</b> a alteração — comandas já abertas
          mantêm a taxa do momento em que foram criadas.
        </p>

        <ChangePasswordCard />
      </div>
    </div>
  )
}
