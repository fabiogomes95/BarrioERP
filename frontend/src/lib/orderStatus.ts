// Rótulo e cores de cada status de comanda (lista de pedidos, detalhe).

export const ORDER_STATUS = {
  open:            { label: 'Aberta',  color: 'text-green-400',  bg: 'bg-green-500/10',  border: 'border-green-500/25' },
  bill_requested:  { label: 'Conta',   color: 'text-orange-400', bg: 'bg-orange-500/10', border: 'border-orange-500/25' },
  closed:          { label: 'Fechada', color: 'text-stone-500',  bg: 'bg-stone-800/40',  border: 'border-stone-700/40' },
  finalized:       { label: 'Final.',  color: 'text-stone-500',  bg: 'bg-stone-800/40',  border: 'border-stone-700/40' },
} as Record<string, { label: string; color: string; bg: string; border: string }>
