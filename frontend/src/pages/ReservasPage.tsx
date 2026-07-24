import { useState, useEffect, useCallback } from 'react'
import {
  type Reservation, type ReservationStatus, type Table,
  fetchReservations, createReservation, updateReservation, checkInReservation, cancelReservation,
  fetchTables,
} from '../lib/api'
import { inputCls, Field, ModalOverlay, ErrorBanner, Spinner } from '../components/ui'

const STATUS_CFG: Record<ReservationStatus, { label: string; color: string; bg: string; border: string }> = {
  confirmed: { label: 'Confirmada',      color: 'text-blue-400',  bg: 'bg-blue-500/10',  border: 'border-blue-500/25' },
  seated:    { label: 'Compareceu',      color: 'text-green-400', bg: 'bg-green-500/10', border: 'border-green-500/25' },
  cancelled: { label: 'Cancelada',       color: 'text-stone-500', bg: 'bg-stone-800/40', border: 'border-stone-700/40' },
  no_show:   { label: 'Não compareceu',  color: 'text-red-400',   bg: 'bg-red-500/10',   border: 'border-red-500/25' },
}

function todayISO() {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

function toDatetimeLocalValue(iso: string): string {
  const d = new Date(iso)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

function fromDatetimeLocalValue(value: string): string {
  return new Date(value).toISOString()
}

function timeOf(iso: string): string {
  return new Date(iso).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })
}

// ── Modal: Nova/Editar reserva ───────────────────────────────────────────────

function ReservationModal({ editing, defaultTableId, tables, onClose, onSaved }: {
  editing: Reservation | null
  defaultTableId?: string
  tables: Table[]
  onClose: () => void
  onSaved: (r: Reservation) => void
}) {
  const [tableId, setTableId] = useState(editing?.table_id ?? defaultTableId ?? tables[0]?.id ?? '')
  const [customerName, setCustomerName] = useState(editing?.customer_name ?? '')
  const [customerPhone, setCustomerPhone] = useState(editing?.customer_phone ?? '')
  const [partySize, setPartySize] = useState(String(editing?.party_size ?? 2))
  const [reservedAt, setReservedAt] = useState(
    editing ? toDatetimeLocalValue(editing.reserved_at) : ''
  )
  const [notes, setNotes] = useState(editing?.notes ?? '')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      const data = {
        table_id: tableId,
        customer_name: customerName.trim(),
        customer_phone: customerPhone.trim() || null,
        party_size: Number(partySize),
        reserved_at: fromDatetimeLocalValue(reservedAt),
        notes: notes.trim() || null,
      }
      const saved = editing ? await updateReservation(editing.id, data) : await createReservation(data)
      onSaved(saved)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro ao salvar reserva')
    } finally {
      setLoading(false)
    }
  }

  return (
    <ModalOverlay onClose={onClose}>
      <h2 className="text-stone-100 text-base font-bold mb-5">{editing ? 'Reagendar reserva' : 'Nova reserva'}</h2>

      {error && <ErrorBanner message={error} />}

      <form onSubmit={handleSubmit} className="space-y-3.5">
        <Field label="Mesa">
          <select value={tableId} onChange={e => setTableId(e.target.value)} required className={inputCls}>
            {tables.length === 0 && <option value="">Nenhuma mesa ativa</option>}
            {tables.map(t => <option key={t.id} value={t.id}>{t.label} ({t.capacity} lugares)</option>)}
          </select>
        </Field>

        <Field label="Data e hora">
          <input type="datetime-local" required value={reservedAt}
            onChange={e => setReservedAt(e.target.value)} className={inputCls} />
        </Field>

        <div className="grid grid-cols-2 gap-3">
          <Field label="Nome do cliente">
            <input type="text" required value={customerName} onChange={e => setCustomerName(e.target.value)}
              placeholder="ex: João Silva" className={inputCls} />
          </Field>
          <Field label="Nº de pessoas">
            <input type="number" min={1} max={100} required value={partySize}
              onChange={e => setPartySize(e.target.value)} className={inputCls} />
          </Field>
        </div>

        <Field label="Telefone (opcional)">
          <input type="tel" value={customerPhone} onChange={e => setCustomerPhone(e.target.value)}
            placeholder="(11) 99999-9999" className={inputCls} />
        </Field>

        <Field label="Observações (opcional)">
          <input type="text" value={notes} onChange={e => setNotes(e.target.value)}
            placeholder="…" className={inputCls} />
        </Field>

        <div className="flex gap-2 pt-1">
          <button type="button" onClick={onClose}
            className="flex-1 py-2.5 rounded-xl text-sm font-semibold text-stone-400
                       border border-stone-700/60 hover:bg-stone-800/50 transition-colors">
            Cancelar
          </button>
          <button type="submit" disabled={loading || !tableId}
            className="flex-1 py-2.5 rounded-xl text-sm font-semibold bg-amber-500 hover:bg-amber-400
                       text-stone-900 disabled:opacity-40 transition-colors">
            {loading ? 'Salvando…' : editing ? 'Salvar' : 'Reservar'}
          </button>
        </div>
      </form>
    </ModalOverlay>
  )
}

// ── Linha de reserva ──────────────────────────────────────────────────────────

function ReservationRow({ reservation, onCheckIn, onCancel, onEdit }: {
  reservation: Reservation
  onCheckIn: () => void
  onCancel: () => void
  onEdit: () => void
}) {
  const cfg = STATUS_CFG[reservation.status]
  const active = reservation.status === 'confirmed'

  return (
    <div className="flex items-center justify-between gap-3 px-4 py-3 border-b border-stone-800/30 last:border-0">
      <div className="min-w-0 flex items-center gap-3">
        <div className="text-center shrink-0 w-12">
          <p className="text-stone-100 text-sm font-bold leading-none">{timeOf(reservation.reserved_at)}</p>
        </div>
        <div className="min-w-0">
          <div className="flex items-center gap-1.5">
            <p className="text-stone-200 text-sm font-medium truncate">{reservation.customer_name}</p>
            <span className={['shrink-0 text-[9px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded-full border', cfg.color, cfg.bg, cfg.border].join(' ')}>
              {cfg.label}
            </span>
          </div>
          <p className="text-stone-600 text-xs mt-0.5">
            {reservation.table_label} · {reservation.party_size} {reservation.party_size === 1 ? 'pessoa' : 'pessoas'}
            {reservation.customer_phone && ` · ${reservation.customer_phone}`}
            {reservation.notes && ` · ${reservation.notes}`}
          </p>
        </div>
      </div>
      {active && (
        <div className="flex items-center gap-1.5 shrink-0">
          <button onClick={onCheckIn}
            className="px-2.5 py-1.5 rounded-lg text-xs font-semibold text-green-400
                       border border-green-500/30 hover:bg-green-500/10 transition-colors">
            Check-in
          </button>
          <button onClick={onEdit}
            className="px-2.5 py-1.5 rounded-lg text-xs font-semibold text-stone-400
                       border border-stone-700/60 hover:bg-stone-800/50 transition-colors">
            Reagendar
          </button>
          <button onClick={onCancel}
            className="p-1.5 rounded-lg text-stone-600 hover:text-red-400 hover:bg-red-500/10 transition-colors"
            title="Cancelar reserva">
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.9}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
      )}
    </div>
  )
}

// ── Página ────────────────────────────────────────────────────────────────────

type Modal = { type: 'new' } | { type: 'edit'; reservation: Reservation }

export default function ReservasPage() {
  const [day, setDay] = useState(todayISO())
  const [reservations, setReservations] = useState<Reservation[]>([])
  const [tables, setTables] = useState<Table[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [modal, setModal] = useState<Modal | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [res, ts] = await Promise.all([fetchReservations({ day }), fetchTables()])
      setReservations(res)
      setTables(ts.filter(t => t.is_active))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro ao carregar reservas')
    } finally {
      setLoading(false)
    }
  }, [day])

  useEffect(() => { load() }, [load])

  async function handleCheckIn(r: Reservation) {
    try {
      const updated = await checkInReservation(r.id)
      setReservations(prev => prev.map(x => x.id === updated.id ? updated : x))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro ao fazer check-in')
    }
  }

  async function handleCancel(r: Reservation) {
    if (!confirm(`Cancelar a reserva de ${r.customer_name}?`)) return
    try {
      await cancelReservation(r.id)
      load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro ao cancelar reserva')
    }
  }

  return (
    <div className="h-full overflow-y-auto">
      <div className="max-w-3xl mx-auto px-4 sm:px-6 py-6">

        {/* Cabeçalho */}
        <div className="flex items-center justify-between gap-3 mb-4 flex-wrap">
          <div>
            <h1 className="text-stone-100 text-xl font-bold leading-tight">Reservas</h1>
            <p className="text-stone-500 text-sm mt-1">
              {reservations.filter(r => r.status === 'confirmed').length} confirmadas nesse dia
            </p>
          </div>
          <div className="flex items-center gap-2">
            <input type="date" value={day} onChange={e => setDay(e.target.value)}
              className="rounded-xl px-3 py-2 text-sm border border-stone-800/60 text-stone-200
                         focus:outline-none focus:border-amber-500/40 transition-all"
              style={{ background: 'var(--color-app-surface)' }} />
            <button onClick={() => setModal({ type: 'new' })}
              className="flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-semibold
                         bg-amber-500 hover:bg-amber-400 text-stone-900 transition-colors">
              <span className="text-base leading-none">+</span>
              Nova
            </button>
          </div>
        </div>

        {error && <ErrorBanner message={error} onRetry={load} />}

        {loading ? (
          <Spinner />
        ) : reservations.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-center">
            <p className="text-stone-400 text-sm font-medium">Nenhuma reserva nesse dia</p>
            <p className="text-stone-600 text-xs mt-1">Clique em "Nova" para reservar uma mesa</p>
          </div>
        ) : (
          <div className="rounded-2xl border border-stone-800/60 overflow-hidden"
               style={{ background: 'var(--color-app-surface)' }}>
            {reservations.map(r => (
              <ReservationRow
                key={r.id}
                reservation={r}
                onCheckIn={() => handleCheckIn(r)}
                onCancel={() => handleCancel(r)}
                onEdit={() => setModal({ type: 'edit', reservation: r })}
              />
            ))}
          </div>
        )}
      </div>

      {modal && (
        <ReservationModal
          editing={modal.type === 'edit' ? modal.reservation : null}
          tables={tables}
          onClose={() => setModal(null)}
          onSaved={() => { setModal(null); load() }}
        />
      )}
    </div>
  )
}
