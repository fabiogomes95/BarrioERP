"""
app/api/v1/endpoints/onboarding.py

Endpoint do primeiro acesso — criação de Company + Establishment + OWNER.

═══════════════════════════════════════════════════════════════
CONCEITO — Endpoint público vs. autenticado
═══════════════════════════════════════════════════════════════

Todos os outros endpoints deste sistema exigem um JWT válido:
    current_user: CurrentUser → Depends(get_current_user) → valida Bearer token

Este endpoint NÃO TEM essa dependência — ele é público.
É o único ponto de entrada que não exige autenticação prévia,
porque é justamente o momento de criar as credenciais pela primeira vez.

Isso cria um risco: qualquer pessoa na internet poderia acessar
este endpoint e criar empresas no servidor.

PROTEÇÃO — X-Onboarding-Secret:
    O endpoint exige um header customizado com um segredo configurado
    no .env. O frontend que vai disparar este endpoint precisa conhecer
    o segredo (compartilhado pelo desenvolvedor com o cliente).

    Sem o header ou com valor errado → HTTP 403 imediatamente,
    antes de qualquer operação de banco de dados.

    Essa é a "Opção A" do planejamento arquitetural: simples, eficaz,
    zero infraestrutura extra para o cenário de 2 bares.

═══════════════════════════════════════════════════════════════
CONCEITO — Por que Header e não body ou query param?
═══════════════════════════════════════════════════════════════

Headers são o lugar semântico correto para metadados de autenticação/autorização.
O corpo (body) é para os dados do recurso sendo criado.
Query params ficam na URL — segredos em URL aparecem em logs de servidor.

Analogia com padrões conhecidos:
    Authorization: Bearer <jwt>           → autenticação padrão
    X-API-Key: <chave>                    → APIs públicas com chave
    X-Onboarding-Secret: <segredo>        → nosso caso (header customizado)

O prefixo "X-" indica header não-padrão (extensão customizada).
"""

from fastapi import APIRouter, Header, HTTPException, status

from app.api.deps import DBSession
from app.core.config import settings
from app.schemas.onboarding import OnboardingRequest, OnboardingResponse
from app.services.onboarding_service import OnboardingService

router = APIRouter()


# ══════════════════════════════════════════════════════════════════════════════
# POST /onboarding/register — Registrar primeiro acesso
# ══════════════════════════════════════════════════════════════════════════════


@router.post(
    "/register",
    response_model=OnboardingResponse,
    status_code=201,
    summary="Registrar primeiro acesso",
    description=(
        "Cria uma nova empresa (Company), unidade principal (Establishment 'Matriz') "
        "e usuário proprietário (OWNER) em uma única operação atômica. "
        "Retorna token de acesso imediato — o usuário entra no sistema direto. "
        "Requer o header X-Onboarding-Secret com a chave configurada no servidor."
    ),
)
async def register(
    data: OnboardingRequest,
    session: DBSession,
    x_onboarding_secret: str | None = Header(
        default=None,
        description=(
            "Chave secreta de onboarding configurada no servidor. "
            "Obtenha com o administrador do sistema."
        ),
        alias="x-onboarding-secret",
    ),
) -> OnboardingResponse:
    """
    Registra um novo estabelecimento no sistema.

    PARÂMETROS — como o FastAPI injeta cada um:
        data                 → JSON do corpo da requisição (OnboardingRequest)
        session              → Depends(get_db) → AsyncSession gerenciada pelo FastAPI
        x_onboarding_secret  → Header "X-Onboarding-Secret" da requisição HTTP

    POR QUE `str | None` E NÃO `str` (obrigatório)?
        Se declarássemos `x_onboarding_secret: str = Header(...)`, o FastAPI
        retornaria HTTP 422 (Unprocessable Entity) para header ausente,
        expondo que existe um header de validação com aquele nome.

        Com `str | None = Header(default=None)`, um header ausente chega
        como None — e a lógica abaixo retorna HTTP 403 com mensagem genérica.
        O comportamento externo é idêntico para quem não tem o segredo:
        sempre HTTP 403. Não vaza o nome ou existência do header.

    VERIFICAÇÃO DO SEGREDO — feita no endpoint, não no service:
        O service (OnboardingService) não sabe que está sendo chamado via HTTP.
        Ele não conhece headers, não conhece settings.
        A verificação de segredo é uma preocupação da camada HTTP → fica aqui.

        Analogia: o porteiro verifica o convite na porta.
        O anfitrião dentro da festa não precisa saber como funciona o porteiro.

    FLUXO COMPLETO:
        1. FastAPI extrai o header X-Onboarding-Secret
        2. Comparamos com settings.ONBOARDING_SECRET
        3. Se diferente (ou None) → HTTP 403, encerrado aqui
        4. Se igual → chama OnboardingService.register(data)
        5. Service cria Company + Establishment + User (transação única)
        6. Retorna OnboardingResponse com token + dados do tenant criado
        7. FastAPI faz commit da transação (via get_db context manager)
        8. HTTP 201 Created
    """
    # Verificação de segredo — primeira barreira, antes de qualquer query
    if x_onboarding_secret != settings.ONBOARDING_SECRET:
        # Mesma mensagem para "header ausente" e "valor errado"
        # Não revelamos se o header existe, se o valor é próximo, etc.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso negado.",
        )

    service = OnboardingService(session=session)
    return await service.register(data)
