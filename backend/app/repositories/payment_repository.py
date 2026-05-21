"""
app/repositories/payment_repository.py

Acesso ao banco para o modelo Payment.

═══════════════════════════════════════════════════════════════
CONCEITO — Integridade financeira no banco de dados
═══════════════════════════════════════════════════════════════

Em sistemas financeiros, a integridade dos dados no banco é SAGRADA.
Algumas estratégias que usamos:

1. TIPO CORRETO: `Numeric(12, 2)` no banco — armazenamento exato.
   NUNCA `Float` ou `Double Precision` (perda de precisão).

2. NUNCA DELETE: pagamentos NUNCA são deletados fisicamente.
   O modelo Payment não tem SoftDeleteMixin, mas também não tem
   um endpoint de DELETE. Pagamentos são registros históricos imutáveis.
   Se houve um pagamento errado, cria-se um pagamento de ESTORNO/REFUND.

3. STATUS COMO RASTREAMENTO:
   PENDING → aguardando confirmação do gateway
   CONFIRMED → pagamento efetivado
   FAILED → falhou no gateway
   REFUNDED → estornado
   Em nossa implementação simplificada, auto-confirmamos (CONFIRMED).

4. AUDITORIA:
   cashier_id registra quem fez o registro.
   created_at registra quando.
   Isso permite auditar "quem registrou pagamentos às 3h da manhã?"

═══════════════════════════════════════════════════════════════
CONCEITO — func.sum() do SQLAlchemy e o problema do NULL
═══════════════════════════════════════════════════════════════

Uma query de soma SQL:
    SELECT SUM(amount) FROM payments
    WHERE order_id = ? AND status = 'confirmed'

Quando NÃO HÁ pagamentos, o SQL retorna NULL, não zero.
É o comportamento padrão de funções de agregação em SQL:
    SUM de nenhuma linha = NULL (indefinido)
    COUNT de nenhuma linha = 0

Em Python, se não tratarmos: `result.scalar_one()` retorna `None`.
Se tentarmos fazer `None + Decimal("50")` → TypeError!

SOLUÇÃO: verificar se o resultado é None e retornar Decimal("0"):

    raw = result.scalar_one()
    return raw if raw is not None else Decimal("0")

Alternativa com COALESCE no SQL (retorna 0 se NULL):
    SELECT COALESCE(SUM(amount), 0) FROM payments WHERE ...

SQLAlchemy: func.coalesce(func.sum(Payment.amount), 0)

Ambas as abordagens funcionam. Usamos a verificação Python
por ser mais explícita e fácil de entender.
"""

from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select

from app.models.payment import Payment, PaymentStatus
from app.repositories.base import BaseRepository


class PaymentRepository(BaseRepository[Payment]):
    """
    Repository para operações financeiras com pagamentos.

    Herda operações genéricas de BaseRepository[Payment]:
        add()  → INSERT + flush + refresh
        get()  → busca por PK

    Adiciona queries financeiras específicas:
        list_by_order()           → lista pagamentos de uma comanda
        sum_confirmed_by_order()  → soma total pago para verificar saldo

    Nota sobre delete():
        O BaseRepository tem um método delete() para deleção física.
        Para pagamentos, NÃO USAMOS delete(). Pagamentos são imutáveis.
        Se um pagamento precisar ser desfeito, criamos um REFUND (estorno).
    """

    model = Payment

    async def list_by_order(self, order_id: UUID) -> list[Payment]:
        """
        Lista todos os pagamentos de uma comanda, ordenados por data.

        MULTI-TENANCY: a verificação de tenant é feita no SERVICE antes
        de chamar este método. O service primeiro valida que a comanda
        pertence ao estabelecimento, então pede os pagamentos.

        Por que não incluímos `establishment_id` aqui?
            Payment não tem `establishment_id` — ele tem `order_id`.
            A cadeia de tenant é: Payment → Order → Establishment.
            Validar o tenant em Payment exigiria um JOIN com orders,
            tornando a query mais complexa sem benefício adicional
            (o service já garantiu que a comanda é do tenant correto).

        ORDENAÇÃO por created_at: pagamentos em ordem cronológica.
        Importante para o caixa entender o histórico da conta.
        """
        stmt = (
            select(Payment)
            .where(Payment.order_id == order_id)
            .order_by(Payment.created_at)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def sum_confirmed_by_order(self, order_id: UUID) -> Decimal:
        """
        Soma o total de pagamentos CONFIRMADOS de uma comanda.

        Esta é a query financeira mais crítica do sistema.
        Responde a pergunta: "quanto já foi pago desta comanda?"

        Usada em dois contextos:
            1. Ao REGISTRAR um pagamento: verificar se não vai ultrapassar o total
            2. Ao FINALIZAR: verificar se o pagamento é suficiente

        POR QUE SOMENTE CONFIRMED:
            PENDING → ainda não confirmado (ex: aguardando gateway)
            FAILED → não foi efetivado, não conta no total pago
            REFUNDED → foi estornado, não deve contar no total pago
            CONFIRMED → único status que efetivamente quita a comanda

        RETORNA: Decimal("0.00") se não houver pagamentos confirmados.
        NUNCA retorna None — garante aritmética segura no service.
        """
        stmt = select(func.sum(Payment.amount)).where(
            Payment.order_id == order_id,
            Payment.status == PaymentStatus.CONFIRMED,
        )
        result = await self.session.execute(stmt)
        raw = result.scalar_one()

        # SUM de nenhuma linha = NULL no SQL → convertemos para Decimal("0")
        return raw if raw is not None else Decimal("0")
