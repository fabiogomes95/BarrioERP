"""
app/schemas/menu.py

Schemas Pydantic para o módulo de cardápio (menu).

═══════════════════════════════════════════════════════════════
CONCEITO — Catálogo vs Transação: dois mundos diferentes
═══════════════════════════════════════════════════════════════

No BarrioERP existem dois tipos de dados muito diferentes:

DADOS TRANSACIONAIS (orders, payments):
    - Criados com frequência (dezenas por hora)
    - Representam EVENTOS que aconteceram
    - Imutáveis após confirmação
    - Exigem locking, transações, auditoria rigorosa
    - Exemplo: "Mesa 5 pediu 2 hamburgueres às 19h32"

DADOS DE CATÁLOGO (menu, tables, users):
    - Criados raramente (uma vez, depois raramente mudam)
    - Representam ESTADO ATUAL do negócio
    - Podem ser editados sem comprometer histórico
    - Menos rigor transacional necessário
    - Exemplo: "Hambúrguer artesanal custa R$ 28,00"

O cardápio é CATÁLOGO. Isso muda como pensamos sobre ele:
    - Não precisamos de VersionMixin (edições concorrentes são raras)
    - Podemos soft-delete sem locking otimista
    - O histórico financeiro é preservado pelo OrderItem (snapshot)

═══════════════════════════════════════════════════════════════
CONCEITO — Por que produtos são "desativados" ao invés de deletados
═══════════════════════════════════════════════════════════════

Imagine que o restaurante serviu "Risoto de Cogumelos" por 3 anos.
Hoje decidiram tirar do cardápio.

DELETAR FISICAMENTE o MenuItem quebraria:
    - Todos os OrderItems históricos têm menu_item_id apontando para ele
    - O banco faria ON DELETE SET NULL → menu_item_id vira NULL em todos
    - Relatórios históricos perdiam a referência ao item
    - "Qual foi o item mais vendido em 2024?" → impossível de responder

SOFT DELETE preserva tudo:
    - MenuItem continua no banco (deleted_at = now())
    - Não aparece no cardápio (filtrado por deleted_at IS NULL)
    - OrderItems históricos ainda apontam para ele
    - Relatórios históricos funcionam perfeitamente

MAS o OrderItem também guarda snapshot (item_name, unit_price).
Mesmo que o MenuItem seja fisicamente deletado algum dia,
os dados do pedido histórico estão preservados no OrderItem.
Camadas duplas de proteção = dados financeiros seguros.

═══════════════════════════════════════════════════════════════
CONCEITO — Diferença entre is_active e is_available
═══════════════════════════════════════════════════════════════

is_active:
    "Este item existe no cardápio?" — decisão do GERENTE
    False = item removido do cardápio (temporária ou permanentemente)
    Ex: "Caldeirada de peixe" fora do cardápio de inverno

is_available:
    "Este item pode ser pedido AGORA?" — estado operacional
    False = item existe mas não pode ser pedido no momento
    Ex: "Acabou o camarão para hoje"

Por que duas flags?
    Um prato pode estar ATIVO (existe no cardápio) mas INDISPONÍVEL
    (acabou no estoque hoje). O garçom vê o prato mas não pode pedilo.
    Isso é diferente de o prato não existir no cardápio.

No futuro com controle de estoque, is_available pode ser
atualizado automaticamente. Por enquanto é manual.

═══════════════════════════════════════════════════════════════
CONCEITO — sort_order: ordenação manual pelo gerente
═══════════════════════════════════════════════════════════════

Por que não ordenar alfabeticamente?
    - "Cerveja" apareceria antes de "Hambúrguer" na categoria Pratos
    - O gerente sabe que hambúrguer vende mais e quer ele no topo
    - A ordenação é decisão de negócio, não técnica

sort_order = 0 → aparece primeiro (menor número = maior prioridade)
sort_order = 99 → aparece por último

Quando dois itens têm o mesmo sort_order, ordenamos por nome
(para garantir resultado estável e previsível).
"""

from decimal import Decimal
from uuid import UUID

from pydantic import Field, field_validator

from app.schemas.common import BaseSchema, TimestampSchema, UUIDSchema


# ══════════════════════════════════════════════════════════════
# CATEGORIAS
# ══════════════════════════════════════════════════════════════


class CategoryCreate(BaseSchema):
    """
    Dados para criar uma categoria do cardápio.

    Usado em: POST /api/v1/menu/categories

    A `establishment_id` NÃO aparece aqui — vem do JWT do usuário logado.
    Isso garante que o usuário só pode criar categorias no próprio tenant.

    `sort_order` controla a posição da categoria na interface.
    Categorias com sort_order menor aparecem primeiro.
    """

    name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Nome da categoria (ex: 'Bebidas', 'Pratos Principais', 'Sobremesas').",
    )
    description: str | None = Field(
        default=None,
        max_length=500,
        description="Descrição opcional da categoria.",
    )
    sort_order: int = Field(
        default=0,
        ge=0,
        le=9999,
        description="Posição na interface. Menor número = aparece primeiro.",
    )

    @field_validator("name")
    @classmethod
    def name_strip(cls, v: str) -> str:
        return v.strip()


class CategoryUpdate(BaseSchema):
    """
    Dados para atualizar uma categoria.

    Usado em: PATCH /api/v1/menu/categories/{id}

    Todos os campos são opcionais — PATCH parcial.
    Apenas os campos enviados são atualizados.

    Não tem `version` porque MenuCategory não tem VersionMixin.
    Categorias são atualizadas raramente e concorrência não é problema.
    """

    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    sort_order: int | None = Field(default=None, ge=0, le=9999)
    is_active: bool | None = None


class CategoryResponse(UUIDSchema, TimestampSchema):
    """
    Representação de uma categoria para o cliente.

    NÃO inclui `deleted_at` — campo interno de controle.
    NÃO inclui `items` — evita lazy loading e payloads gigantes.
    Para listar itens de uma categoria: GET /menu/items?category_id=X
    """

    establishment_id: UUID
    name: str
    description: str | None
    sort_order: int
    is_active: bool


# ══════════════════════════════════════════════════════════════
# ITENS DO CARDÁPIO
# ══════════════════════════════════════════════════════════════


class MenuItemCreate(BaseSchema):
    """
    Dados para criar um item do cardápio.

    Usado em: POST /api/v1/menu/items

    O Service verifica que `category_id` pertence ao estabelecimento
    do usuário logado. Isso garante multi-tenancy: não é possível
    criar um item numa categoria de outro restaurante.
    """

    category_id: UUID = Field(description="Categoria a que o item pertence.")
    name: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Nome do item (ex: 'Hambúrguer Artesanal', 'Coca-Cola 350ml').",
    )
    description: str | None = Field(
        default=None,
        max_length=1000,
        description="Descrição do item. Opcional — boa para cardápio digital.",
    )
    price: Decimal = Field(
        ...,
        gt=Decimal("0"),
        description="Preço de venda. Deve ser positivo. Use Decimal para precisão.",
    )
    sort_order: int = Field(
        default=0,
        ge=0,
        le=9999,
        description="Posição dentro da categoria. Menor número = aparece primeiro.",
    )
    complementos: list[str] = Field(
        default_factory=list,
        description=(
            "Opções obrigatórias na hora do pedido (ex: cortes do churrasco, "
            "sabores de suco). Vazio = item sem complemento."
        ),
    )

    @field_validator("name")
    @classmethod
    def name_strip(cls, v: str) -> str:
        return v.strip()

    @field_validator("complementos")
    @classmethod
    def clean_complementos(cls, v: list[str]) -> list[str]:
        # Remove espaços e descarta vazios/duplicados preservando a ordem
        seen: set[str] = set()
        out: list[str] = []
        for raw in v:
            s = raw.strip()
            if s and s.lower() not in seen:
                seen.add(s.lower())
                out.append(s)
        return out

    @field_validator("price")
    @classmethod
    def price_two_decimals(cls, v: Decimal) -> Decimal:
        """
        Arredonda para 2 casas decimais — padrão monetário.

        R$ 28.999 → R$ 29.00
        R$ 28.001 → R$ 28.00

        Por que arredondar no schema e não no banco?
            O banco (NUMERIC 12,2) também trunca/arredonda.
            Fazer aqui garante que o cliente vê o valor real que será salvo.
            Sem surpresas: "cadastrei 28.999, por que aparece 29.00?"
        """
        return round(v, 2)


class MenuItemUpdate(BaseSchema):
    """
    Dados para atualizar um item do cardápio.

    Usado em: PATCH /api/v1/menu/items/{id}

    Permite:
    - Alterar nome, descrição, preço, posição
    - Ativar/desativar o item (is_active)
    - Marcar como disponível/indisponível (is_available)
    - Mover para outra categoria (category_id)

    IMPORTANTE sobre alteração de preço:
        Alterar o preço do MenuItem NÃO afeta pedidos já feitos.
        OrderItems existentes têm snapshot (unit_price guardado na hora).
        O novo preço só vale para pedidos futuros.

    Não tem `version` — MenuItems são catálogo, não transações.
    """

    category_id: UUID | None = Field(
        default=None,
        description="Mover para outra categoria. O Service verifica que a nova categoria pertence ao mesmo tenant.",
    )
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=1000)
    price: Decimal | None = Field(default=None, gt=Decimal("0"))
    sort_order: int | None = Field(default=None, ge=0, le=9999)
    is_active: bool | None = None
    is_available: bool | None = None
    complementos: list[str] | None = Field(
        default=None,
        description="Substitui a lista de complementos. Envie [] para remover todos.",
    )

    @field_validator("complementos")
    @classmethod
    def clean_complementos(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return None
        seen: set[str] = set()
        out: list[str] = []
        for raw in v:
            s = raw.strip()
            if s and s.lower() not in seen:
                seen.add(s.lower())
                out.append(s)
        return out


class MenuItemResponse(UUIDSchema, TimestampSchema):
    """
    Representação de um item do cardápio para o cliente.

    Inclui `category_id` (UUID da categoria).
    NÃO inclui `deleted_at` — campo interno de controle.
    NÃO inclui `cost` — custo do produto é informação sensível.
    NÃO inclui objetos aninhados (categoria completa) — evita queries extras.
    """

    category_id: UUID
    name: str
    description: str | None
    price: Decimal
    sort_order: int
    is_active: bool
    is_available: bool
    complementos: list[str] = []
