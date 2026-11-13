import { type Order, fetchOrder, isConflictError } from '../../lib/api'

// ── Helpers ───────────────────────────────────────────────────────────────────

/**
 * Fecha/finaliza uma comanda tolerando o conflito de versão mais comum em
 * produção: outro dispositivo (garçom, outro caixa) mexeu na comanda — um
 * item novo, desconto, etc. — entre a tela ter carregado e o clique em
 * "Fechar"/"Finalizar". Isso bate o version local contra um version mais
 * novo no banco e o backend responde 409 (OPTIMISTIC_LOCK).
 *
 * Antes disso o usuário via só "Erro ao fechar comanda" e precisava sair e
 * reabrir a comanda manualmente pra pegar a versão atual e tentar de novo.
 * Aqui, no primeiro 409 buscamos a comanda fresca e tentamos UMA vez a mais
 * com o version certo — o mesmo que o usuário faria manualmente. Se ainda
 * assim falhar (ex: comanda foi cancelada nesse meio tempo), o erro real
 * sobe normalmente pra tela.
 */
export async function closeOrFinish(
  orderId: string,
  currentVersion: number,
  action: (orderId: string, version: number) => Promise<Order>,
): Promise<Order> {
  try {
    return await action(orderId, currentVersion)
  } catch (err) {
    if (!isConflictError(err)) throw err
    const fresh = await fetchOrder(orderId)
    return action(orderId, fresh.version)
  }
}
