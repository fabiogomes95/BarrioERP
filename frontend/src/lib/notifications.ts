import { useEffect, useRef, useState } from 'react'
import { getToken, getUser, fetchOrder, fetchTables } from './api'
import { printComanda } from './print'

export interface BillRequestAlert {
  id: string
  orderId: string
  tableNumber: number | null
  tableLabel: string
  tableId: string | null
}

// ── Estação de impressão ────────────────────────────────────────────────────
// A impressora térmica está ligada por cabo a um único PC. Qualquer outro
// dispositivo (celular do garçom, etc.) não tem como imprimir localmente —
// precisa mandar a impressão pra quem tem. Essa flag é por dispositivo
// (localStorage), não por usuário: quem liga é quem está fisicamente no PC
// do caixa, uma vez só.

const PRINT_STATION_KEY = 'barrio_print_station'

export function isPrintStation(): boolean {
  return localStorage.getItem(PRINT_STATION_KEY) === '1'
}

export function setPrintStation(value: boolean): void {
  if (value) localStorage.setItem(PRINT_STATION_KEY, '1')
  else localStorage.removeItem(PRINT_STATION_KEY)
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

async function handleRemotePrint(orderId: string) {
  try {
    const [order, tables] = await Promise.all([fetchOrder(orderId), fetchTables()])
    const table = tables.find(t => t.id === order.table_id)
    const barName = getUser()?.company_name ?? 'BarrioERP'
    printComanda(order, table, barName)
  } catch {
    // Se a comanda não existir mais (foi fechada nesse meio tempo, etc.),
    // simplesmente não imprime — não há usuário esperando um retorno aqui.
  }
}

/**
 * Escuta o canal de eventos em tempo real (SSE): alertas de "mesa solicitou
 * a conta" (toast + som) e pedidos de impressão remota (quando este
 * dispositivo está marcado como a impressora do bar — ver isPrintStation()).
 *
 * Só conecta pra quem lida com pagamento (owner/manager/cashier) — garçom e
 * cozinha não precisam saber quando alguém pede a conta, e não são quem
 * teria a impressora física conectada.
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
        if (data.type === 'print.request' && isPrintStation()) {
          handleRemotePrint(data.order_id)
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
