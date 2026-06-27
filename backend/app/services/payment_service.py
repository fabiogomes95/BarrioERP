"""
app/services/payment_service.py

Regras de negócio financeiras para o módulo de pagamentos.

═══════════════════════════════════════════════════════════════
CONCEITO — O que é integridade financeira?
═══════════════════════════════════════════════════════════════

Integridade financeira é a garantia de que os dados monetários
do sistema estão sempre em estado válido e consistente.

Em termos práticos, para o BarrioERP:

    INVARIANTE 1: total_pago ≤ total_comanda
        Nunca devemos registrar mais pagamento do que o valor da conta.

    INVARIANTE 2: comanda fechada ↔ total_pago ≥ total_comanda
        Uma comanda SÓ pode ser marcada como CLOSED se foi paga integralmente.
        Uma comanda ABERTA não pode ter total_pago > total_comanda.

    INVARIANTE 3: pagamentos são imutáveis
        Uma vez CONFIRMED, um pagamento nunca é editado ou deletado.
        Erros são corrigidos com novos registros (REFUND, ajuste).

    INVARIANTE 4: cada operação é atômica
        Registrar pagamento + verificar saldo = mesma transação.
        Finalizar + liberar mesa = mesma transação.

Por que essas invariantes são importantes?
    - AUDITORIA: qualquer inconsistência é detectável
    - CONFIANÇA: o caixa confia nos números do sistema
    - LEGAL: relatórios fiscais precisam ser exatos
    - NEGÓCIO: diferença de caixa = prejuízo real

═══════════════════════════════════════════════════════════════
CONCEITO — Por que operações financeiras precisam de mais proteção?
═══════════════════════════════════════════════════════════════

Comparando dois tipos de operações:

OPERAÇÃO OPERACIONAL (ex: mudar o label de uma mesa):
    - Se der errado: garçom tenta de novo
    - Impacto: zero — nenhum dano permanente
    - Rollback é trivial

OPERAÇÃO FINANCEIRA (ex: registrar pagamento):
    - Se der errado no meio: estado inconsistente com impacto real
    - Impacto: cliente pode pagar duas vezes ou não pagar
    - Rollback pode ser juridicamente complexo

Por isso, operações financeiras precisam de:
    1. LOCKING OTIMISTA (version): previne edições concorrentes
    2. TRANSAÇÃO ATÔMICA: rollback automático em caso de erro
    3. VALIDAÇÃO ANTES DO COMMIT: verificar saldo ANTES de registrar
    4. LOGS/AUDITORIA: registrar quem fez o quê e quando
    5. IDEMPOTÊNCIA: re-enviar a mesma operação não deve duplicar

Em nossa implementação, usamos 1, 2, 3 e 4.
O item 5 (idempotência) é para um nível mais avançado.

═══════════════════════════════════════════════════════════════
CONCEITO — Diferença entre finish e close
═══════════════════════════════════════════════════════════════

O sistema tem DOIS caminhos para fechar uma comanda:

1. OrderService.close_order() — PATCH /orders/{id}/close:
    - NÃO verifica se foi paga
    - Usado para: cancelar conta, override do gerente, mesas vazias
    - Sem verificação financeira

2. PaymentService.finish() — PATCH /orders/{id}/finish:
    - VERIFICA se total_pago >= total_comanda
    - Rejeita se insuficiente (BusinessRuleError)
    - Caminho normal de fechamento com pagamento

Por que ter os dois?
    - O gerente precisa poder cancelar uma conta sem pagamento
    - O fluxo normal garante integridade financeira
    - Flexibilidade sem abrir mão de segurança no caminho padrão

═══════════════════════════════════════════════════════════════
CONCEITO — Como o backend protege contra dupla cobrança
═══════════════════════════════════════════════════════════════

PROBLEMA: o caixa clica "registrar pagamento" duas vezes.

PROTEÇÃO 1 — Verificação de saldo:
    Ao registrar o 2º pagamento, verificamos:
        total_pago_atual + novo_pagamento <= total_comanda
    Se a comanda já está quitada, retornamos BusinessRuleError:
        "Esta comanda já está totalmente paga."

PROTEÇÃO 2 — Saldo disponível:
    Se o saldo restante for R$ 0, qualquer valor > 0 é rejeitado.
    O caixa vê claramente que a comanda já está quitada.

PROTEÇÃO 3 — Locking otimista no finish:
    Dois caixas tentando finalizar ao mesmo tempo:
        → Um tem version=5 e consegue
        → O outro tem version=5 mas o banco já tem version=6
        → StaleDataError → OptimisticLockError → HTTP 409

LIMITAÇÃO CONHECIDA (documentada):
    Race condition na verificação de saldo (ver comentário em `register`).
    Duas requisições simultâneas EXATAMENTE ao mesmo tempo poderiam
    ambas passar pela verificação e causar ligeiro excesso.
    Solução completa: SELECT FOR UPDATE (pessimistic locking).
    Para nosso nível atual: verificação + tratamento de StaleDataError.
"""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm.exc import StaleDataError

from app.core.exceptions import (
    BusinessRuleError,
    NotFoundError,
    OptimisticLockError,
    TenantError,
)
from app.models.order import OrderStatus
from app.models.payment import Payment, PaymentStatus
from app.models.table import TableStatus
from app.repositories.order_repository import OrderRepository
from app.repositories.payment_repository import PaymentRepository
from app.repositories.table_repository import TableRepository
from app.schemas.order import OrderResponse
from app.schemas.payment import OrderFinish, PaymentCreate, PaymentResponse
from app.services.base import BaseService
from sqlalchemy.ext.asyncio import AsyncSession


class PaymentService(BaseService):
    """
    Service financeiro — registra pagamentos e finaliza comandas.

    Usa TRÊS repositories na mesma sessão (mesma transação):
        _payment_repo → INSERT de pagamentos, SUM de valores
        _order_repo   → fetch de comandas, fechamento via status
        _table_repo   → liberar mesa ao finalizar

    Este é um exemplo de Service que ORQUESTRA múltiplos repositories.
    A atomicidade é garantida pela sessão compartilhada.
    """

    def __init__(
        self,
        session: AsyncSession,
        company_id: UUID,
        establishment_id: UUID | None = None,
        user_id: UUID | None = None,
    ) -> None:
        super().__init__(session, company_id, establishment_id, user_id)
        self._payment_repo = PaymentRepository(session)
        self._order_repo = OrderRepository(session)
        self._table_repo = TableRepository(session)

    # ── Helper ────────────────────────────────────────────────────────────────

    def _require_establishment(self) -> UUID:
        """Exige que o usuário esteja vinculado a um estabelecimento."""
        if self.establishment_id is None:
            raise TenantError(
                "Usuário não está vinculado a um estabelecimento. "
                "Vincule o usuário para registrar pagamentos."
            )
        return self.establishment_id

    # ── Operações financeiras ─────────────────────────────────────────────────

    async def register(self, data: PaymentCreate) -> PaymentResponse:
        """
        Registra um pagamento para uma comanda.

        FLUXO COMPLETO:
            1. Verifica tenant (establishment_id do JWT)
            2. Busca a comanda e verifica tenant
            3. Verifica que a comanda está em estado pagável (OPEN ou BILL_REQUESTED)
            4. Calcula saldo devedor: total_comanda - total_já_pago
            5. Verifica que o novo pagamento não excede o saldo
            6. Calcula troco (se for dinheiro com amount_tendered)
            7. Cria o Payment com status=CONFIRMED
            8. Flush dentro da transação
            9. Retorna PaymentResponse

        CONCEITO — Verificação ANTES do INSERT (não depois):
            A verificação de saldo acontece ANTES de inserir o pagamento.
            Isso evita inserir um pagamento inválido e ter que fazer rollback.

            Ordem: validar → inserir → confirmar (via commit)
            NÃO:   inserir → validar → rollback se inválido

        CONCEITO — Auto-confirmação simplificada:
            Em produção, um pagamento com cartão/PIX passaria por:
                1. Criar Payment com status=PENDING
                2. Chamar gateway de pagamento
                3. Gateway retorna sucesso → PATCH /payments/{id} → CONFIRMED
                4. Gateway retorna falha → PATCH /payments/{id} → FAILED

            Para nossa implementação educacional, simplificamos:
                Criar Payment com status=CONFIRMED diretamente.
                Cash, débito, crédito, PIX — todos auto-confirmados.

        RACE CONDITION DOCUMENTADA:
            Dois caixas registram o último R$20 ao mesmo tempo:
                Ambos lêem saldo_restante = R$20
                Ambos calculam: R$20 <= R$20 → OK
                Ambos tentam inserir

            Resultado possível: dois pagamentos de R$20, total pago = R$40
            (mas a comanda era de apenas R$20 + algo já pago).

            Proteção disponível mas não implementada aqui:
                SELECT FOR UPDATE na comanda antes de verificar saldo.
                Isso bloquearia a 2ª requisição até a 1ª commitar.

            Para aprender: essa limitação existe e é documentada.
            Para produção: adicionar SELECT FOR UPDATE.

        LANÇA:
            TenantError (400)        → usuário sem estabelecimento
            NotFoundError (404)      → comanda não encontrada
            BusinessRuleError (422)  → comanda não pagável
            BusinessRuleError (422)  → comanda já quitada
            BusinessRuleError (422)  → valor excede saldo devedor
        """
        establishment_id = self._require_establishment()

        # 1. Busca e valida a comanda (verificação de tenant via establishment_id)
        # Usamos get_with_items porque ele filtra por establishment_id
        order = await self._order_repo.get_with_items(data.order_id, establishment_id)
        if order is None:
            raise NotFoundError("Order", data.order_id)

        # 2. Verifica status pagável
        # CLOSED é permitido para quitação de fiado; CANCELLED não aceita pagamento
        if order.status not in (OrderStatus.OPEN, OrderStatus.BILL_REQUESTED, OrderStatus.CLOSED):
            raise BusinessRuleError(
                f"Não é possível registrar pagamento em comanda com status "
                f"'{order.status.value}'."
            )

        # 3. Calcula saldo devedor (quanto ainda falta pagar)
        # Buscamos via SQL SUM — preciso, sem depender de estado em memória
        total_pago = await self._payment_repo.sum_confirmed_by_order(order.id)
        saldo_devedor = order.total - total_pago

        # 4. Verifica se comanda já está quitada
        if saldo_devedor <= Decimal("0"):
            raise BusinessRuleError(
                f"Esta comanda já está totalmente paga "
                f"(R$ {total_pago:.2f} de R$ {order.total:.2f})."
            )

        # 5. Verifica que o novo pagamento não excede o saldo
        if data.amount > saldo_devedor:
            raise BusinessRuleError(
                f"Valor do pagamento (R$ {data.amount:.2f}) excede o saldo devedor "
                f"(R$ {saldo_devedor:.2f}). "
                f"Registre no máximo R$ {saldo_devedor:.2f}."
            )

        # 6. Calcula troco para pagamentos em dinheiro
        # change_given = o que o cliente entregou MENOS o que foi registrado
        # Ex: entregou R$50, pagamento de R$27 → troco R$23
        change_given: Decimal | None = None
        if (
            data.amount_tendered is not None
            and data.amount_tendered > Decimal("0")
        ):
            change_given = data.amount_tendered - data.amount

        # 7. Cria o pagamento
        # SIMPLIFIED: status=CONFIRMED direto (sem gateway de pagamento)
        payment = Payment(
            order_id=order.id,
            cashier_id=self.user_id,         # quem registrou (do JWT)
            method=data.method,
            status=PaymentStatus.CONFIRMED,   # auto-confirmado
            amount=data.amount,
            amount_tendered=data.amount_tendered,
            change_given=change_given,
            reference=data.reference,
        )
        payment = await self._payment_repo.add(payment)
        return PaymentResponse.model_validate(payment)

    async def list_for_order(self, order_id: UUID) -> list[PaymentResponse]:
        """
        Lista todos os pagamentos de uma comanda.

        VERIFICAÇÃO DE TENANT:
            Primeiro buscamos a comanda para verificar o tenant.
            Se a comanda não pertencer ao estabelecimento → NotFoundError.
            Só então listamos os pagamentos.

            Por que dois steps em vez de um JOIN?
                Clareza: a lógica fica explícita
                Reuso: get_with_items() já faz a verificação de tenant
                Custo baixo: payment_repo.list_by_order() é query simples

        RETORNA: lista vazia [] se a comanda existe mas não tem pagamentos.
        LANÇA: NotFoundError (404) se a comanda não existir ou for de outro tenant.
        """
        establishment_id = self._require_establishment()

        # Verifica que a comanda pertence ao tenant
        order = await self._order_repo.get_with_items(order_id, establishment_id)
        if order is None:
            raise NotFoundError("Order", order_id)

        payments = await self._payment_repo.list_by_order(order_id)
        return [PaymentResponse.model_validate(p) for p in payments]

    async def finish(self, order_id: UUID, data: OrderFinish) -> OrderResponse:
        """
        Finaliza uma comanda após verificar que foi totalmente paga.

        FLUXO:
            1. Busca a comanda (com itens para retornar OrderResponse completo)
            2. Verifica status (deve ser OPEN ou BILL_REQUESTED)
            3. Verifica versão (locking otimista)
            4. Calcula total pago via SQL SUM
            5. Verifica suficiência: total_pago >= order.total
            6. Fecha a comanda: status=CLOSED, closed_at=now()
            7. Libera a mesa: table.status=FREE
            8. Flush na transação
            9. Busca estado final para retornar

        CONCEITO — Por que `finish` não é automático?
            Poderíamos fechar a comanda automaticamente quando o
            último pagamento for registrado em `register`.
            Mas isso seria:
                1. Assumir que o pagamento cobriu EXATAMENTE o saldo
                2. Não dar ao caixa controle sobre o momento do fechamento
                3. Misturar responsabilidades (registro de pagamento ≠ fechamento)

            Separação de responsabilidades:
                POST /payments  → registra o fato financeiro
                PATCH /finish   → ato explícito de fechamento

            O caixa confirma explicitamente: "estou encerrando esta conta agora".

        CONCEITO — Dois fluxos de fechamento:
            close  (OrderService):   fecha sem checar pagamento → override
            finish (PaymentService): fecha com verificação financeira → normal

            Ambos fazem:
                order.status = CLOSED
                order.closed_at = now()
                table.status = FREE

            A diferença é a VERIFICAÇÃO DE PAGAMENTO antes de fechar.

        INVARIANTE GARANTIDA:
            Após `finish` com sucesso:
                order.status = CLOSED
                total_pago (via sum) >= order.total
                table.status = FREE

            Esses três estados são consistentes e imutáveis após o commit.

        LANÇA:
            NotFoundError (404)     → comanda não encontrada
            BusinessRuleError (422) → comanda não fechável (já closed/cancelled)
            OptimisticLockError (409) → conflito de versão
            BusinessRuleError (422) → pagamento insuficiente
        """
        establishment_id = self._require_establishment()

        # Busca com itens — necessário para retornar OrderResponse completo
        order = await self._order_repo.get_with_items(order_id, establishment_id)
        if order is None:
            raise NotFoundError("Order", order_id)

        # Verifica estado pagável
        if order.status not in (OrderStatus.OPEN, OrderStatus.BILL_REQUESTED):
            raise BusinessRuleError(
                f"Não é possível finalizar comanda com status '{order.status.value}'. "
                "Apenas comandas ABERTAS ou com CONTA SOLICITADA podem ser finalizadas."
            )

        # Locking otimista: versão deve bater
        if order.version != data.version:
            raise OptimisticLockError("Order")

        # Verifica suficiência do pagamento
        total_pago = await self._payment_repo.sum_confirmed_by_order(order.id)

        if total_pago < order.total:
            falta = order.total - total_pago
            raise BusinessRuleError(
                f"Pagamento insuficiente para finalizar a conta. "
                f"Total da comanda: R$ {order.total:.2f} | "
                f"Total pago: R$ {total_pago:.2f} | "
                f"Faltam: R$ {falta:.2f}."
            )

        # Fecha a comanda
        order.status = OrderStatus.CLOSED
        order.closed_at = datetime.now(UTC)

        # Libera a mesa (mesma transação)
        if order.table_id is not None:
            table = await self._table_repo.get_by_establishment(
                order.table_id, establishment_id
            )
            if table is not None:
                table.status = TableStatus.FREE

        try:
            await self.session.flush()
        except StaleDataError:
            # Race condition: alguém editou a comanda entre o GET e o flush
            raise OptimisticLockError("Order")

        # Re-busca estado final do banco (inclui items para OrderResponse)
        order_final = await self._order_repo.get_with_items(order.id, establishment_id)
        return OrderResponse.model_validate(order_final)
