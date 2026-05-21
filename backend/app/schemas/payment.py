"""
app/schemas/payment.py

Schemas Pydantic para o módulo de pagamentos.

═══════════════════════════════════════════════════════════════
CONCEITO — Por que float QUEBRA sistemas financeiros
═══════════════════════════════════════════════════════════════

Esta é uma das lições mais importantes de desenvolvimento de software.

Computadores armazenam números reais em BINÁRIO. O problema é que
a maioria das frações decimais comuns NÃO TEM representação exata em binário.

Experimento no Python:

    >>> 0.1 + 0.2
    0.30000000000000004        ← ERRADO! Não é 0.3

    Isso acontece porque 0.1 em binário é uma dízima periódica:
    0.1 (decimal) = 0.0001100110011... (binário, infinito)

    O computador armazena uma aproximação finita.
    Na soma, os erros se acumulam.

Em sistemas financeiros isso é DESASTROSO:
    Comanda: 3 itens de R$33.33
    float: 33.33 × 3 = 99.99000000000001 ← centavo extra!

    Em milhares de transações por dia:
    - Relatório fechado com valor diferente do real
    - Diferença de caixa no fim do dia
    - Auditoria impossível de fechar

A SOLUÇÃO é usar Decimal (módulo `decimal` do Python):

    >>> from decimal import Decimal
    >>> Decimal("0.1") + Decimal("0.2")
    Decimal("0.3")             ← CORRETO!

    Decimal usa aritmética BASE 10 exata — sem erros de arredondamento.

REGRA ABSOLUTA:
    Dinheiro → Decimal, NUNCA float.
    Banco de dados → NUMERIC(12,2), NUNCA FLOAT ou REAL.
    API → strings "87.00", NUNCA 87.0 (float JSON).
    Python → Decimal("87.00"), NUNCA 87.0.

═══════════════════════════════════════════════════════════════
CONCEITO — Diferença entre pagamento parcial e fechamento
═══════════════════════════════════════════════════════════════

Em sistemas de PDV (Ponto de Venda), o pagamento é um PROCESSO, não um ato único.

FLUXO TÍPICO:
    1. Mesa 5 pede a conta (ordem: OPEN → BILL_REQUESTED)
    2. Mesa tem 4 pessoas. Cada uma paga separado:
       - Pessoa A paga R$25,00 em dinheiro
       - Pessoa B paga R$15,00 no débito
       - Pessoa C paga R$20,00 no crédito
       - Pessoa D paga R$27,00 em dinheiro
       Total pago: R$87,00 = R$87,00 da comanda ✓
    3. FINISH: verifica que o total pago cobre o total da comanda
    4. Comanda fecha, mesa fica FREE

PAGAMENTO PARCIAL:
    Quando total_pago < total_comanda.
    A comanda continua OPEN — não fechamos até estar quitada.
    Isso é intencional: o cliente pode pagar em múltiplas parcelas.

SUPERARRECADAÇÃO (proibida):
    total_pago > total_comanda é um ERRO.
    Nunca devemos registrar mais do que o saldo devedor.
    (Para cash, o troco compensa — mas o amount registrado deve ser exato)

═══════════════════════════════════════════════════════════════
CONCEITO — amount vs amount_tendered vs change_given
═══════════════════════════════════════════════════════════════

Estes três campos são para pagamentos em dinheiro:

    Comanda total: R$ 87,00
    Cliente já pagou R$ 60,00 (débito)
    Restante: R$ 27,00

    Cliente entrega uma nota de R$ 50,00 em dinheiro:
        amount          = 27.00  ← o que vai ser registrado na comanda
        amount_tendered = 50.00  ← o que o cliente entregou fisicamente
        change_given    = 23.00  ← troco = 50.00 - 27.00

    O campo `amount` nunca deve exceder o saldo devedor.
    O `amount_tendered` pode ser maior (cliente deu nota maior).
    O `change_given` é calculado automaticamente pelo servidor.

Por que o servidor calcula o troco?
    Evitar que o caixa cometa erro de matemática.
    Garantir que o troco é sempre = amount_tendered - amount.
    Registro preciso para auditoria de caixa.
"""

from decimal import Decimal
from uuid import UUID

from pydantic import Field, model_validator

from app.models.payment import PaymentMethod, PaymentStatus
from app.schemas.common import BaseSchema, TimestampSchema, UUIDSchema


# ── Schemas de Entrada ────────────────────────────────────────────────────────


class PaymentCreate(BaseSchema):
    """
    Dados para registrar um pagamento.

    Usado em: POST /api/v1/payments

    CAMPOS:
        order_id        → qual comanda está sendo paga
        method          → forma de pagamento (cash, credit_card, debit_card, pix, voucher)
        amount          → valor EXATO aplicado à comanda (não pode exceder saldo devedor)
        amount_tendered → apenas para CASH: quanto o cliente entregou fisicamente
        reference       → código de transação (ex: NSU do cartão, txid do PIX)

    O campo `status` NÃO aparece aqui porque o servidor define automaticamente.
    Em nossa implementação simplificada, todos os pagamentos são auto-confirmados.
    Em produção, pagamentos de cartão/PIX ficariam PENDING até confirmação do gateway.
    """

    order_id: UUID = Field(description="ID da comanda a ser paga.")
    method: PaymentMethod = Field(description="Forma de pagamento.")
    amount: Decimal = Field(
        ...,
        gt=Decimal("0"),
        description=(
            "Valor aplicado à comanda. "
            "Deve ser maior que zero e não pode exceder o saldo devedor."
        ),
    )
    amount_tendered: Decimal | None = Field(
        default=None,
        ge=Decimal("0"),
        description=(
            "Apenas para dinheiro: valor entregue pelo cliente. "
            "Deve ser >= amount. O troco é calculado automaticamente."
        ),
    )
    reference: str | None = Field(
        default=None,
        max_length=200,
        description="Código de referência da transação (NSU, txid PIX, etc.). Opcional.",
    )

    @model_validator(mode="after")
    def validate_cash_payment(self) -> "PaymentCreate":
        """
        Valida regras específicas de pagamento em dinheiro.

        Esta é uma validação CRUZADA: verifica a RELAÇÃO entre campos.
        O Pydantic v2 executa model_validators depois de validar cada campo.

        REGRA: se o método é CASH e amount_tendered foi fornecido,
        amount_tendered deve ser >= amount.
        (Não faz sentido o cliente dar menos do que o valor a pagar.)
        """
        if (
            self.method == PaymentMethod.CASH
            and self.amount_tendered is not None
            and self.amount_tendered < self.amount
        ):
            raise ValueError(
                f"Para pagamento em dinheiro, o valor entregue (amount_tendered={self.amount_tendered}) "
                f"não pode ser menor que o valor do pagamento (amount={self.amount})."
            )
        return self


class OrderFinish(BaseSchema):
    """
    Dados para finalizar uma comanda (fechar com verificação de pagamento).

    Usado em: PATCH /api/v1/orders/{order_id}/finish

    DIFERENÇA entre finish e close:
        close (OrderService):   fecha sem verificar pagamentos — override do gerente
        finish (PaymentService): fecha APENAS se total pago >= total da comanda

    O `version` é obrigatório para locking otimista.
    Se alguém modificou a comanda entre o GET e o PATCH, HTTP 409.
    """

    version: int = Field(
        ...,
        gt=0,
        description="Versão atual da comanda. Obtenha via GET e envie de volta.",
    )


# ── Schemas de Saída ──────────────────────────────────────────────────────────


class PaymentResponse(UUIDSchema, TimestampSchema):
    """
    Representação completa de um pagamento.

    Retornado em: POST /payments, GET /orders/{id}/payments

    Inclui `change_given` calculado pelo servidor — nunca pelo cliente.
    O `cashier_id` registra QUEM fez o pagamento (para auditoria de caixa).
    """

    order_id: UUID
    cashier_id: UUID | None            # quem registrou (do JWT)
    method: PaymentMethod
    status: PaymentStatus
    amount: Decimal                    # valor aplicado à comanda
    amount_tendered: Decimal | None    # para cash: o que o cliente entregou
    change_given: Decimal | None       # para cash: troco calculado pelo servidor
    reference: str | None             # NSU, txid, etc.
