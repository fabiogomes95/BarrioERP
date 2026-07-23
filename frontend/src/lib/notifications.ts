import { useEffect, useRef, useState } from 'react'
import { getToken, getUser } from './api'

export interface BillRequestAlert {
  id: string
  orderId: string
  tableNumber: number | null
  tableLabel: string
  tableId: string | null
}

function beep() {
  try {
    const ctx = new AudioContext()
    const osc = ctx.createOscillator()
    const gain = ctx.createGain()
    osc.connect(gain)
    gain.connect(ctx.destination)
    osc.type = 'sine'
    osc.frequency.value = 880
    gain.gain.setValueAtTime(0.15, ctx.currentTime)
    gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.5)
    osc.start()
    osc.stop(ctx.currentTime + 0.5)
    // segundo bipe, um tom acima
    setTimeout(() => {
      const osc2 = ctx.createOscillator()
      const gain2 = ctx.createGain()
      osc2.connect(gain2)
      gain2.connect(ctx.destination)
      osc2.type = 'sine'
      osc2.frequency.value = 1108.73
      gain2.gain.setValueAtTime(0.15, ctx.currentTime)
      gain2.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.5)
      osc2.start()
      osc2.stop(ctx.currentTime + 0.5)
    }, 180)
  } catch {
    // Web Audio indisponível (raro) — só perde o som, o toast visual continua
  }
}

/**
 * Escuta o canal de eventos em tempo real (SSE) e mantém uma fila de alertas
 * de "mesa solicitou a conta" pra exibir como toast + som.
 *
 * Só conecta pra quem lida com pagamento (owner/manager/cashier) — garçom e
 * cozinha não precisam saber quando alguém pede a conta.
 */
export function useBillRequestAlerts() {
  const [alerts, setAlerts] = useState<BillRequestAlert[]>([])
  const sourceRef = useRef<EventSource | null>(null)

  useEffect(() => {
    const user = getUser()
    const token = getToken()
    if (!user || !token) return
    if (user.role === 'waiter' || user.role === 'kitchen') return

    const source = new EventSource(`/api/v1/notifications/stream?token=${encodeURIComponent(token)}`)
    sourceRef.current = source

    source.onmessage = (evt) => {
      try {
        const data = JSON.parse(evt.data)
        if (data.type === 'table.bill_requested') {
          beep()
          setAlerts(prev => [
            ...prev,
            {
              id: `${data.order_id}-${Date.now()}`,
              orderId: data.order_id,
              tableNumber: data.table_number,
              tableLabel: data.table_label,
              tableId: data.table_id,
            },
          ])
        }
      } catch {
        // ignora mensagens malformadas
      }
    }

    return () => {
      source.close()
      sourceRef.current = null
    }
  }, [])

  function dismiss(id: string) {
    setAlerts(prev => prev.filter(a => a.id !== id))
  }

  return { alerts, dismiss }
}
