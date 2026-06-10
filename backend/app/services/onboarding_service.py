"""
app/services/onboarding_service.py

Lógica de negócio do onboarding — criação do primeiro acesso ao sistema.

═══════════════════════════════════════════════════════════════
CONCEITO — Por que este service NÃO herda BaseService?
═══════════════════════════════════════════════════════════════

O `BaseService` recebe `company_id` no construtor porque pressupõe
que o tenant já existe — ele opera dentro de um contexto de empresa.

O OnboardingService é o oposto: seu único propósito é CRIAR o tenant
pela primeira vez. Quando ele começa a executar, não existe nenhum
company_id para passar como contexto.

Padrão similar: `AuthService` também não herda BaseService pelo mesmo
motivo — o login ocorre antes de saber a qual empresa o usuário pertence.

═══════════════════════════════════════════════════════════════
CONCEITO — Atomicidade no SQLAlchemy async
═══════════════════════════════════════════════════════════════

Toda operação neste service ocorre dentro da mesma `AsyncSession`
injetada pelo FastAPI via `get_db()`. A sessão gerencia uma única
transação de banco de dados.

O fluxo é:
    session.add(company)        → registra na sessão (só memória)
    await session.flush()       → envia INSERT ao banco (na transação)
    await session.refresh()     → recarrega com valores gerados (id, timestamps)

    ... (mesmo para establishment e user) ...

    COMMIT automático ao final do endpoint (em get_db())

Se qualquer `flush()` falhar (ex: slug duplicado, constraint de e-mail),
uma exceção é lançada e o SQLAlchemy faz ROLLBACK automático.
Nenhum dado parcial fica no banco: ou tudo é criado, ou nada é criado.

═══════════════════════════════════════════════════════════════
CONCEITO — Por que usar session diretamente e não BaseRepository?
═══════════════════════════════════════════════════════════════

`BaseRepository` exige uma subclasse com `model = AlgumModel`.
Para usar BaseRepository com Company e Establishment, seria necessário
criar `CompanyRepository` e `EstablishmentRepository` — dois arquivos
novos que conteriam apenas `model = Company` e `model = Establishment`.

Esses repositories seriam usados SOMENTE aqui, sem nenhuma query
específica além das herdadas. O custo da abstração supera o benefício.

A alternativa: chamar `session.add()` + `flush()` + `refresh()` diretamente.
É exatamente o que `BaseRepository.add()` faz internamente — sem abstração
desnecessária para um caso de uso único.

UserRepository continua sendo usado para verificar unicidade do e-mail,
pois já tem o método `get_by_email()` que precisamos reutilizar.
"""

import re
import unicodedata

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError
from app.core.security import create_access_token, hash_password
from app.models.company import Company
from app.models.establishment import Establishment
from app.models.user import User, UserRole
from app.repositories.user_repository import UserRepository
from app.schemas.onboarding import OnboardingRequest, OnboardingResponse
from app.schemas.user import UserResponse

# Nome padrão da unidade principal de cada empresa.
# Constante no nível de módulo para ser fácil de alterar se necessário.
_DEFAULT_ESTABLISHMENT_NAME = "Matriz"
_DEFAULT_ESTABLISHMENT_SLUG = "matriz"


class OnboardingService:
    """
    Serviço de onboarding — registra um novo estabelecimento no sistema.

    Responsabilidades:
        1. Validar unicidade global do e-mail
        2. Gerar slug único para a Company
        3. Criar Company, Establishment e User OWNER em uma transação
        4. Gerar e retornar JWT para login imediato

    NÃO herda BaseService — não existe tenant ainda quando este serviço executa.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        # UserRepository: reutilizamos o método get_by_email() para verificar
        # se o e-mail já está em uso em qualquer empresa do sistema.
        self._user_repo = UserRepository(session)

    # ══════════════════════════════════════════════════════════════════════
    # MÉTODO PÚBLICO — ponto de entrada do service
    # ══════════════════════════════════════════════════════════════════════

    async def register(self, data: OnboardingRequest) -> OnboardingResponse:
        """
        Executa o registro completo do primeiro acesso.

        SEQUÊNCIA (toda dentro de uma única transação):
            1. Verifica se o e-mail já existe no sistema
            2. Gera um slug único a partir do nome do bar
            3. Cria a Company
            4. Cria o Establishment "Matriz" vinculado à Company
            5. Cria o usuário OWNER vinculado a ambos
            6. Gera o JWT (token de acesso imediato)
            7. Monta e retorna OnboardingResponse

        Por que essa ordem importa?
            Establishment precisa do company.id (criado no passo 3).
            User precisa do company.id e do establishment.id (criados nos passos 3 e 4).
            Slug é gerado antes de criar a Company para detectar colisões cedo.
        """
        # ── Passo 1: e-mail único globalmente ─────────────────────────────
        await self._ensure_email_available(data.email.lower())

        # ── Passo 2: slug único para a Company ────────────────────────────
        company_slug = await self._unique_company_slug(
            self._slugify(data.bar_name)
        )

        # ── Passo 3: criar a Company ───────────────────────────────────────
        company = Company(
            name=data.bar_name.strip(),
            slug=company_slug,
            email=data.email.lower(),     # e-mail de contato da empresa
            phone=data.phone,             # opcional — pode ser None
            plan="starter",               # plano padrão ao criar
        )
        self._session.add(company)
        await self._session.flush()
        await self._session.refresh(company)
        # Após o flush+refresh, company.id está preenchido (gerado pelo banco).
        # O refresh recarrega o objeto para capturar valores server-side:
        # id (gen_random_uuid()), created_at, updated_at.

        # ── Passo 4: criar o Establishment "Matriz" ───────────────────────
        # O slug do establishment é único POR EMPRESA (constraint: company_id + slug).
        # Para a primeira filial "Matriz", o slug sempre será "matriz"
        # — não há risco de colisão porque cada empresa começa do zero.
        establishment = Establishment(
            company_id=company.id,
            name=_DEFAULT_ESTABLISHMENT_NAME,   # "Matriz"
            slug=_DEFAULT_ESTABLISHMENT_SLUG,   # "matriz"
            address=data.address,               # opcional — endereço físico
            timezone="America/Sao_Paulo",       # fuso padrão para bares brasileiros
        )
        self._session.add(establishment)
        await self._session.flush()
        await self._session.refresh(establishment)

        # ── Passo 5: criar o usuário OWNER ────────────────────────────────
        user = User(
            company_id=company.id,
            establishment_id=establishment.id,  # OWNER vinculado à Matriz
            name=data.owner_name.strip(),
            email=data.email.lower(),            # mesmo e-mail informado no form
            phone=data.phone,
            password_hash=hash_password(data.password),
            role=UserRole.OWNER,                 # sempre OWNER no onboarding
            is_active=True,
        )
        self._session.add(user)
        await self._session.flush()
        await self._session.refresh(user)

        # ── Passo 6: gerar JWT ─────────────────────────────────────────────
        # Replicamos exatamente o mesmo padrão do AuthService.login()
        # para garantir que o token gerado aqui é idêntico ao gerado
        # no fluxo de login normal.
        token_extra = {
            "company_id": str(user.company_id),
            "role": user.role.value,   # "owner" (string, não o enum)
            "name": user.name,
        }
        access_token = create_access_token(subject=user.id, extra=token_extra)

        # ── Passo 7: montar e retornar o response ─────────────────────────
        # model_validate(user) converte o objeto ORM para o schema Pydantic.
        # Funciona porque UserResponse tem from_attributes=True (herdado de BaseSchema).
        return OnboardingResponse(
            access_token=access_token,
            token_type="bearer",
            user=UserResponse.model_validate(user),
            establishment_name=establishment.name,  # "Matriz"
        )

    # ══════════════════════════════════════════════════════════════════════
    # MÉTODOS PRIVADOS — helpers internos
    # ══════════════════════════════════════════════════════════════════════

    async def _ensure_email_available(self, email: str) -> None:
        """
        Verifica se o e-mail já está em uso em qualquer empresa do sistema.

        POR QUE VERIFICAR GLOBALMENTE E NÃO POR EMPRESA?
        ─────────────────────────────────────────────────
        A constraint do banco é (company_id, email) — único por empresa.
        Tecnicamente, o mesmo e-mail poderia existir em duas empresas.

        Porém, o fluxo de login atual usa `get_by_email()` sem filtrar
        por empresa — ele retorna o primeiro usuário com aquele e-mail.
        Se dois donos de bares diferentes usarem o mesmo e-mail,
        o login seria ambíguo.

        A checagem global evita essa ambiguidade até que o login
        seja atualizado para diferenciar por empresa (company_slug no payload).

        NÃO usa UserRepository.get_by_email() porque ele filtra apenas
        usuários ativos (is_active=True). Aqui queremos bloquear o e-mail
        mesmo se o usuário existente estiver inativo — evita cadastro duplo
        de um mesmo dono que desativou o contrato e tenta se recadastrar.

        QUERY:
            SELECT COUNT(*) FROM users WHERE email = :email AND deleted_at IS NULL
        """
        stmt = (
            select(func.count())
            .select_from(User)
            .where(
                User.email == email,
                User.deleted_at.is_(None),  # exclui soft-deletados (removidos de verdade)
            )
        )
        result = await self._session.execute(stmt)
        count = result.scalar_one()

        if count > 0:
            # ConflictError → handler em main.py → HTTP 409 Conflict
            raise ConflictError(f"E-mail '{email}' já está em uso no sistema.")

    async def _unique_company_slug(self, base_slug: str) -> str:
        """
        Gera um slug único para a Company, adicionando sufixo numérico se necessário.

        PROBLEMA:
            Slugs de Company são únicos globalmente (constraint: UNIQUE em companies.slug).
            Se dois bares tiverem o mesmo nome, o segundo teria conflito:
                "Bar do João" → "bar-do-joao"     (1º bar: OK)
                "Bar do João" → "bar-do-joao"     (2º bar: CONFLITO!)

        SOLUÇÃO — sufixo incremental:
            Tenta "bar-do-joao"   → existe? → tenta "bar-do-joao-2"
            "bar-do-joao-2" → existe? → tenta "bar-do-joao-3"
            ... até encontrar um livre.

        Por que verificar no banco em vez de usar UUID no slug?
            Slugs são legíveis: aparecem em URLs, logs, identificação visual.
            "bar-do-joao" é melhor que "bar-do-joao-a3f9b2c1".
            Para 2 bares, colisão é rara. O loop termina na 1ª ou 2ª tentativa.

        QUERY (por iteração):
            SELECT COUNT(*) FROM companies WHERE slug = :slug AND deleted_at IS NULL
        """
        candidate = base_slug
        counter = 2  # se o slug base colidir, começa em "-2" (não "-1")

        while True:
            stmt = (
                select(func.count())
                .select_from(Company)
                .where(
                    Company.slug == candidate,
                    Company.deleted_at.is_(None),
                )
            )
            result = await self._session.execute(stmt)
            exists = result.scalar_one() > 0

            if not exists:
                return candidate  # slug livre encontrado

            # Colisão: adiciona ou atualiza o sufixo numérico
            candidate = f"{base_slug}-{counter}"
            counter += 1

    @staticmethod
    def _slugify(text: str) -> str:
        """
        Converte um nome livre em slug URL-safe.

        EXEMPLOS:
            "Bar do João"       → "bar-do-joao"
            "Restaurante São Paulo" → "restaurante-sao-paulo"
            "O Bêbado & Cia!!"  → "o-bebado-cia"

        PROCESSO (passo a passo):
            1. Normaliza Unicode NFD → separa letras de acentos
               "ã" → "a" + combinador de til (dois caracteres)
            2. Descarta os combinadores (categoria Mn = Mark, Nonspacing)
               "a" + til → apenas "a"
            3. Converte para ASCII puro (encode/decode)
            4. Converte para minúsculas
            5. Substitui espaços e separadores por hífen
            6. Remove qualquer caractere que não seja letra, número ou hífen
            7. Colapsa hífens múltiplos em um único
            8. Remove hífens no início e fim

        POR QUE `unicodedata` E NÃO UMA BIBLIOTECA EXTERNA?
            Para slugify básico, a stdlib é suficiente e evita dependência.
            Bibliotecas como `python-slugify` tratam mais edge cases
            (caracteres chineses, árabe, etc.) — desnecessário para nomes
            de bares brasileiros.
        """
        # Passo 1-2: remove acentos via normalização NFD + filtro de categoria
        nfkd = unicodedata.normalize("NFD", text)
        ascii_text = "".join(
            c for c in nfkd
            if unicodedata.category(c) != "Mn"  # Mn = Mark, Nonspacing (acentos)
        )

        # Passo 3-4: ASCII puro, minúsculas
        ascii_text = ascii_text.encode("ascii", "ignore").decode("ascii").lower()

        # Passo 5: espaços e underscores → hífen
        ascii_text = re.sub(r"[\s_]+", "-", ascii_text)

        # Passo 6: remove tudo que não é letra, número ou hífen
        ascii_text = re.sub(r"[^a-z0-9-]", "", ascii_text)

        # Passo 7-8: limpa hífens múltiplos e bordas
        ascii_text = re.sub(r"-{2,}", "-", ascii_text).strip("-")

        return ascii_text or "estabelecimento"
        # fallback "estabelecimento" para nomes que viram string vazia
        # após remoção dos caracteres especiais (raro, mas defensivo)
