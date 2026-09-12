import { useState, useEffect, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { type Order, type Table, fetchOrder, fetchTables } from '../lib/api'
import { OrderDetail } from '../components/OrderDetailView'

export default function ComandaPage() {
  const { orderId } = useParams<{ orderId: string }>()
  const navigate = useNavigate()
  const [order, setOrder] = useState<Order | null>(null)
  const [table, setTable] = useState<Table | undefined>(undefined)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    if (!orderId) return
    setLoading(true)
    setError(null)
    try {
      const [o, ts] = await Promise.all([fetchOrder(orderId), fetchTables()])
      setOrder(o)
      setTable(ts.find(t => t.id === o.table_id))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro ao carregar comanda')
    } finally {
      setLoading(false)
    }
  }, [orderId])

  useEffect(() => { load() }, [load])

  // Auto-refresh silencioso — sem isso, uma comanda fechada/alterada em
  // outro aparelho (o garçom no celular, outro caixa) só aparecia aqui
  // depois de um F5 manual. 15s (mais rápido que o padrão de 30s do resto
  // do app) porque essa é a tela onde dinheiro troca de mão — vale a pena
  // ela ficar um pouco mais em dia com a realidade.
  useEffect(() => {
    if (!orderId) return
    const id = setInterval(async () => {
      try {
        const [o, ts] = await Promise.all([fetchOrder(orderId), fetchTables()])
        setOrder(o)
        setTable(ts.find(t => t.id === o.table_id))
      } catch {
        // Silencioso de propósito: um erro passageiro de rede aqui não deve
        // atrapalhar quem já está com a comanda aberta na tela.
      }
    }, 15_000)
    return () => clearInterval(id)
  }, [orderId])

  function goBack() {
    // Volta para a tela anterior (Mesas ou Pedidos); se não houver, vai para Pedidos
    if (window.history.length > 1) navigate(-1)
    else navigate('/pedidos', { replace: true })
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full text-stone-600 text-sm">
        Carregando comanda…
      </div>
    )
  }

  if (error || !order) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-center p-8 gap-3">
        <p className="text-stone-400 text-sm">{error ?? 'Comanda não encontrada'}</p>
        <button onClick={goBack}
          className="px-4 py-2 rounded-xl text-sm font-semibold bg-amber-500 hover:bg-amber-400 text-stone-900 transition-colors">
          Voltar
        </button>
      </div>
    )
  }

  return (
    <div className="h-full">
      <OrderDetail
        order={order}
        table={table}
        onUpdated={setOrder}
        onClosed={goBack}
        onBack={goBack}
      />
    </div>
  )
}
