# BarrioERP — Arquitetura do Backend

> Documentação viva. Atualizar conforme o sistema evolui.

---

## Índice

1. [Visão Geral](#1-visão-geral)
2. [Estrutura de Pastas](#2-estrutura-de-pastas)
3. [Camadas da Arquitetura](#3-camadas-da-arquitetura)
4. [Banco de Dados e Models](#4-banco-de-dados-e-models)
5. [Mixins — Comportamentos Reutilizáveis](#5-mixins--comportamentos-reutilizáveis)
6. [Alembic — Controle de Versão do Banco](#6-alembic--controle-de-versão-do-banco)
7. [Configuração e Ambiente](#7-configuração-e-ambiente)
8. [Segurança — JWT e Senhas](#8-segurança--jwt-e-senhas)
9. [Schemas — Contratos da API](#9-schemas--contratos-da-api)
10. [Repositories — Acesso ao Banco](#10-repositories--acesso-ao-banco)
11. [Services — Lógica de Negócio](#11-services--lógica-de-negócio)
12. [API — Endpoints e Dependências](#12-api--endpoints-e-dependências)
13. [Fluxo Completo de uma Requisição](#13-fluxo-completo-de-uma-requisição)
14. [Fluxo de Autenticação JWT](#14-fluxo-de-autenticação-jwt)
15. [Multi-Tenancy — Como Funciona](#15-multi-tenancy--como-funciona)
16. [Docker e Infraestrutura](#16-docker-e-infraestrutura)
17. [Decisões Arquiteturais](#17-decisões-arquiteturais)
18. [Comandos do Dia-a-Dia](#18-comandos-do-dia-a-dia)

---

## 1. Visão Geral

O BarrioERP é um **SaaS** (Software as a Service) para gestão de restaurantes.

**SaaS** significa que vários restaurantes usam o mesmo sistema ao mesmo tempo, cada um com seus dados isolados. Isso é chamado de **multi-tenancy** (múltiplos inquilinos).

```
Restaurante A  ──┐
Restaurante B  ──┼──▶  BarrioERP (um único sistema)  ──▶  Banco de dados compartilhado
Restaurante C  ──┘
```

### Stack tecnológica

| Ferramenta | Papel |
|-----------|-------|
| **Python 3.14** | Linguagem principal |
| **FastAPI** | Framework web — recebe requisições HTTP |
| **SQLAlchemy 2.0** | ORM — traduz Python para SQL |
| **PostgreSQL 16** | Banco de dados relacional |
| **Alembic** | Controle de versão do banco |
| **asyncpg** | Driver async para PostgreSQL |
| **Pydantic v2** | Validação de dados e schemas |
| **python-jose** | Geração e decodificação de JWT |
| **passlib + bcrypt** | Hashing de senhas |
| **Docker** | Containerização do banco |

### Por que async?

O FastAPI e o SQLAlchemy são usados em modo **assíncrono** (`async/await`).

Pensa assim: um garçom síncrono leva o pedido à cozinha e **fica parado esperando** o prato ficar pronto. Um garçom assíncrono leva o pedido, vai atender outra mesa enquanto espera, e busca o prato quando estiver pronto.

No backend: enquanto o banco de dados processa uma query, o servidor pode atender outras requisições. Resultado: **muito mais performance** sem precisar de mais servidores.

---

## 2. Estrutura de Pastas

```
BarrioERP/
│
├── ARCHITECTURE.md          ← Este arquivo
├── LEARNING.md              ← Anotações de aprendizado
├── Makefile                 ← Atalhos de comandos
├── docker-compose.yml       ← Define os serviços Docker
│
└── backend/
    ├── .env                 ← Variáveis de ambiente (nunca versionar!)
    ├── .env.example         ← Modelo do .env para novos devs
    ├── requirements.txt     ← Dependências Python
    ├── alembic.ini          ← Configuração do Alembic
    │
    ├── alembic/
    │   ├── env.py           ← Como o Alembic conecta ao banco
    │   ├── script.py.mako   ← Template para novas migrations
    │   └── versions/        ← Histórico de mudanças no banco
    │       └── 12586000cd36_initial.py
    │
    └── app/
        ├── main.py          ← Ponto de entrada do FastAPI
        │
        ├── core/            ← Configurações e utilitários globais
        │   ├── config.py    ← Lê variáveis de ambiente
        │   ├── security.py  ← JWT e bcrypt
        │   └── exceptions.py ← Exceções de domínio
        │
        ├── database/        ← Infraestrutura do banco
        │   ├── base.py      ← Classes base e mixins dos models
        │   └── session.py   ← Engine e sessão async
        │
        ├── models/          ← Representação das tabelas do banco
        │   ├── __init__.py  ← Importa todos os models
        │   ├── company.py
        │   ├── establishment.py
        │   ├── user.py
        │   ├── table.py
        │   ├── menu.py
        │   ├── order.py
        │   ├── payment.py
        │   ├── print_job.py
        │   └── audit_log.py
        │
        ├── schemas/         ← Contratos de entrada/saída da API
        │   ├── common.py    ← Schemas base reutilizáveis
        │   └── auth.py      ← Schemas de autenticação
        │
        ├── repositories/    ← Acesso ao banco de dados
        │   ├── base.py      ← CRUD genérico
        │   └── user_repository.py
        │
        ├── services/        ← Lógica de negócio
        │   ├── base.py      ← Service com contexto de tenant
        │   └── auth_service.py
        │
        └── api/
            ├── deps.py      ← Dependências do FastAPI (injeção)
            └── v1/
                ├── router.py ← Registra todos os endpoints
                └── endpoints/
                    └── auth.py  ← POST /auth/login, GET /auth/me
```

---

## 3. Camadas da Arquitetura

O backend segue uma arquitetura em **camadas** (layered architecture). Cada camada tem uma responsabilidade única e só conversa com a camada imediatamente abaixo.

```
┌─────────────────────────────────────────────┐
│            CLIENTE (celular, browser)        │
└────────────────────┬────────────────────────┘
                     │ HTTP Request
┌────────────────────▼────────────────────────┐
│           API LAYER (endpoints)              │  ← Recebe e valida a requisição
│         app/api/v1/endpoints/               │    Usa schemas Pydantic
│         app/api/deps.py                     │    Retorna a resposta HTTP
└────────────────────┬────────────────────────┘
                     │ chama
┌────────────────────▼────────────────────────┐
│           SERVICE LAYER (serviços)           │  ← Contém as regras de negócio
│         app/services/                       │    "Um usuário só pode logar se estiver ativo"
│                                             │    "Uma mesa só pode ter uma comanda aberta"
└────────────────────┬────────────────────────┘
                     │ chama
┌────────────────────▼────────────────────────┐
│         REPOSITORY LAYER (repositórios)      │  ← Faz queries no banco
│         app/repositories/                  │    Isola o SQL do resto do código
│                                             │    "SELECT * FROM users WHERE email = ?"
└────────────────────┬────────────────────────┘
                     │ usa
┌────────────────────▼────────────────────────┐
│           DATABASE LAYER (banco)             │  ← PostgreSQL
│         app/database/ + app/models/         │    Models = representação das tabelas
└─────────────────────────────────────────────┘
```

### Por que separar em camadas?

**Sem camadas** (código espaguete):
```python
# O endpoint faz TUDO: valida, acessa banco, aplica regra, formata resposta
@app.post("/login")
async def login(email: str, password: str, db = Depends(get_db)):
    result = await db.execute(f"SELECT * FROM users WHERE email = '{email}'")  # SQL injection!
    user = result.first()
    if not user or user.password != password:  # sem bcrypt!
        return {"error": "invalid"}
    token = jwt.encode({"sub": user.id}, "secret")
    return {"token": token}
```

**Com camadas** (código organizado):
- O endpoint só sabe que existe um `AuthService` e chama `auth_service.login()`
- O `AuthService` só sabe as regras: verificar senha, gerar token
- O `UserRepository` só sabe como buscar usuários no banco
- Se precisar trocar PostgreSQL por MongoDB amanhã, só muda o repository

---

## 4. Banco de Dados e Models

### O que é um Model?

Um **model** é uma classe Python que representa uma tabela do banco de dados. Cada atributo da classe vira uma coluna na tabela.

```python
# Esta classe Python...
class Company(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "companies"
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(60), unique=True)

# ...gera esta tabela no PostgreSQL:
# CREATE TABLE companies (
#   id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
#   name VARCHAR(200) NOT NULL,
#   slug VARCHAR(60) UNIQUE,
#   created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
#   ...
# );
```

### Relacionamentos entre tabelas

Os models usam **relacionamentos** (`relationship`) para navegar entre tabelas sem escrever SQL manualmente:

```python
# Sem relacionamento (jeito antigo):
company_id = user.company_id
result = await db.execute(select(Company).where(Company.id == company_id))
company = result.scalar_one()

# Com relacionamento (jeito moderno):
await db.refresh(user, ["company"])
company = user.company  # SQLAlchemy faz o JOIN automaticamente
```

### Diagrama de relacionamentos

```
Company (empresas)
  │
  ├── Establishment (filiais) ──── User (funcionários)
  │         │                          │
  │         ├── Table (mesas)          └── Order (como garçom)
  │         │      │
  │         │      └── Order (comandas) ──── OrderItem (itens)
  │         │                    │
  │         ├── MenuCategory      ├── Payment (pagamentos)
  │         │      │              └── PrintJob (impressão)
  │         │      └── MenuItem ──── OrderItem
  │         │
  │         └── Order (establishment_id)
  │
  └── AuditLog (log de tudo)
```

### Regras de deleção em cascata

Quando você deleta uma `Company`, o banco deleta automaticamente tudo que depende dela:

```
Company deletada
  ├── Establishments → deletados (CASCADE)
  │     ├── Tables → deletados (CASCADE)
  │     ├── MenuCategories → deletadas (CASCADE)
  │     │     └── MenuItems → deletados (CASCADE)
  │     └── Orders → deletados (CASCADE)
  │           ├── OrderItems → deletados (CASCADE)
  │           └── Payments → deletados (CASCADE)
  └── Users → deletados (CASCADE)
        └── Orders.waiter_id → vira NULL (SET NULL)  ← não apaga a comanda!
```

`SET NULL` é usado quando a relação é "opcional" — a comanda continua existindo mesmo sem garçom.

---

## 5. Mixins — Comportamentos Reutilizáveis

**Mixin** é um padrão de programação onde você separa comportamentos em classes pequenas e as combina por herança múltipla.

```python
# Em vez de copiar/colar em cada model:
class User(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin):
    pass
```

### UUIDMixin — Chave primária como UUID

```python
class UUIDMixin:
    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,                      # Python gera o UUID
        server_default=text("gen_random_uuid()"),  # Banco também pode gerar
    )
```

**Por que UUID e não inteiro autoincrement?**

Com inteiros (1, 2, 3...), você expõe informações do negócio:
- `GET /orders/1` → "Este restaurante tem pelo menos 1 pedido"
- `GET /orders/99999` → "Eles têm pelo menos 100k pedidos"

Com UUIDs (`3f2504e0-4f89-11d3-9a0c-0305e82c3301`), nada é previsível. Além disso, UUIDs podem ser gerados pelo cliente sem pedir ao banco — útil em sistemas distribuídos.

### TimestampMixin — Auditoria temporal

```python
class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),   # Banco define na inserção
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),         # SQLAlchemy atualiza a cada UPDATE
        nullable=False,
    )
```

`timezone=True` é crítico — sem timezone, você não sabe se `2026-01-01 12:00` é em São Paulo, London ou Tokyo.

### SoftDeleteMixin — Deleção suave

```python
class SoftDeleteMixin:
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
```

**Por que não deletar de verdade?**

Em um sistema de restaurante, deletar uma comanda ou usuário seria catastrófico para auditoria e relatórios. Em vez disso, apenas marcamos `deleted_at = now()` e filtramos nos queries: `WHERE deleted_at IS NULL`.

### VersionMixin — Optimistic Locking

```python
class VersionMixin:
    version: Mapped[int] = mapped_column(
        default=1,
        server_default=text("1"),
        nullable=False,
    )
```

**Problema que resolve:** Dois garçons editam a mesma comanda ao mesmo tempo.

1. Garçom A lê comanda com `version=1`
2. Garçom B lê comanda com `version=1`
3. Garçom A salva → banco atualiza para `version=2`
4. Garçom B tenta salvar com `version=1` → **ERRO**: versão desatualizada!

O SQLAlchemy detecta isso automaticamente e lança `StaleDataError`, que convertemos para `OptimisticLockError` (HTTP 409).

---

## 6. Alembic — Controle de Versão do Banco

O Alembic funciona como um **Git para o banco de dados**.

```
Versão inicial  →  Adiciona coluna  →  Cria índice  →  Renomeia tabela
(12586000cd36)    (próxima migr.)      (próxima...)     (futura...)
```

### Como funciona

```
app/models/ (Python)
      │
      ▼
alembic revision --autogenerate   ← Compara models com banco atual
      │
      ▼
alembic/versions/xxxxx_initial.py ← Gera o script de mudança
      │
      ▼
alembic upgrade head              ← Executa o script no banco
```

### O arquivo env.py

```python
# alembic/env.py — configura como o Alembic acessa o banco

# Importa TODOS os models para que o Alembic os "veja"
import app.models  # sem este import, as tabelas seriam ignoradas!

target_metadata = Base.metadata  # o mapa de todas as tabelas
```

**Por que importar todos os models?**

O Alembic precisa conhecer todos os models para comparar com o estado atual do banco. Se um model não for importado, o Alembic pensa que a tabela não existe e tenta deletá-la!

### O arquivo versions/12586000cd36_initial.py

É o roteiro da migration inicial. Contém:
- `upgrade()` → cria todas as tabelas, índices e enums
- `downgrade()` → desfaz tudo (para reverter se necessário)

---

## 7. Configuração e Ambiente // PAREI AQUI

### O arquivo .env

```bash
# backend/.env — NUNCA faça commit deste arquivo!
SECRET_KEY=sua-chave-super-secreta-aqui
POSTGRES_USER=barrio
POSTGRES_PASSWORD=barrio_dev
POSTGRES_DB=barrio
```

O `.env` contém segredos que não devem estar no código-fonte. Em produção, essas variáveis são injetadas pelo servidor.

### app/core/config.py — Lendo o .env

```python
class Settings(BaseSettings):
    # Pydantic lê automaticamente do .env e valida os tipos
    SECRET_KEY: str          # obrigatório — quebra na inicialização se faltar
    POSTGRES_HOST: str = "localhost"  # tem valor padrão
    DATABASE_POOL_SIZE: int = 10      # converte string "10" para int automaticamente

    @property
    def database_url(self) -> str:
        # Monta a URL de conexão async (asyncpg)
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:..."

    @property
    def database_url_sync(self) -> str:
        # URL síncrona para o Alembic (psycopg2)
        return f"postgresql+psycopg2://{self.POSTGRES_USER}:..."
```

**Por que duas URLs?**

O Alembic roda em modo síncrono (tradicional), mas o FastAPI usa modo assíncrono. Precisamos de drivers diferentes: `asyncpg` para async, `psycopg2` para sync.

```
FastAPI (async) ──── asyncpg ──── PostgreSQL
Alembic (sync)  ──── psycopg2 ── PostgreSQL
```

### O @lru_cache

```python
@lru_cache          # cache em memória — lê o .env apenas uma vez
def get_settings() -> Settings:
    return Settings()

settings = get_settings()  # instância global usada em todo o projeto
```

---

## 8. Segurança — JWT e Senhas

### Como o bcrypt funciona

```python
# Senha original: "minha_senha_123"
hash = hash_password("minha_senha_123")
# hash: "$2b$12$xKzA3...oq4p2" ← resultado diferente a cada chamada!

# Para verificar:
verify_password("minha_senha_123", hash)  # True
verify_password("senha_errada", hash)      # False
```

**Por que não guardar a senha em texto puro?**

Se o banco for invadido, o invasor não consegue as senhas reais. O bcrypt é proposital mente lento — dificulta ataques de força bruta.

**Por que o hash muda a cada vez?**

O bcrypt usa um **salt** aleatório embutido no hash. Mesmo que dois usuários tenham a mesma senha, os hashes serão diferentes. Isso impede ataques de "rainbow table".

### Como o JWT funciona

JWT = JSON Web Token. É um "crachá digital" que prova quem você é.

```
HEADER          PAYLOAD               SIGNATURE
eyJhbGci...  .  eyJzdWIiOiIxM...  .  SflKxwRJSMeKKF2...
```

O payload contém os dados do usuário em Base64 (não criptografado, apenas codificado):

```json
{
  "sub": "3f2504e0-4f89-...",    ← ID do usuário
  "company_id": "a1b2c3...",    ← ID da empresa (multi-tenant!)
  "role": "MANAGER",            ← Cargo
  "exp": 1716307200,            ← Expira em (timestamp Unix)
  "iat": 1716303600,            ← Emitido em
  "type": "access"              ← Tipo do token
}
```

A **assinatura** garante que o token não foi adulterado. Se alguém mudar `"role": "OWNER"` no payload, a assinatura não vai bater e o token será rejeitado.

```python
def create_access_token(subject: UUID, extra: dict | None = None) -> str:
    payload = {
        "sub": str(subject),  # subject = quem é o dono do token
        "exp": datetime.now(UTC) + timedelta(minutes=60),
        "type": "access",     # distingue de refresh tokens
    }
    # jwt.encode assina com SECRET_KEY usando HS256
    return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")

def decode_token(token: str) -> dict:
    # jwt.decode verifica a assinatura E a expiração automaticamente
    # Lança JWTError se inválido ou expirado
    return jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
```

---

## 9. Schemas — Contratos da API

**Schema** = o "contrato" entre o cliente e o servidor. Define exatamente o que entra e o que sai.

```
Cliente envia JSON  →  Pydantic valida  →  Python usa os dados
Python monta dados  →  Pydantic serializa  →  Cliente recebe JSON
```

### Por que schemas separados dos models?

Os **models** representam o banco de dados (incluem colunas internas como `password_hash`).
Os **schemas** representam o que a API expõe (nunca expomos `password_hash`!).

```python
# Model tem tudo:
class User(Base):
    email: str
    password_hash: str  ← NUNCA deve sair na API!
    company_id: UUID
    ...

# Schema expõe apenas o necessário:
class UserMeResponse(UUIDSchema, TimestampSchema):
    email: str
    name: str
    role: UserRole
    company_id: UUID
    # password_hash não está aqui → nunca será retornado
```

### model_config = ConfigDict(from_attributes=True)

```python
class BaseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)
```

Isso permite criar um schema a partir de um model SQLAlchemy diretamente:

```python
user_orm = await repo.get(user_id)  # retorna objeto SQLAlchemy
user_schema = UserMeResponse.model_validate(user_orm)  # converte para schema
return user_schema  # FastAPI serializa para JSON
```

Sem `from_attributes=True`, o Pydantic não conseguiria ler os atributos do objeto ORM.

---

## 10. Repositories — Acesso ao Banco

O **Repository Pattern** isola todo o código SQL em um único lugar. Se precisar trocar o banco de dados, só muda o repository.

### BaseRepository — CRUD genérico

```python
class BaseRepository(Generic[ModelT]):
    model: type[ModelT]  # qual Model este repository gerencia

    async def get(self, id: UUID) -> ModelT | None:
        # session.get é o jeito mais eficiente de buscar por PK
        # SQLAlchemy usa o identity map (cache interno) antes de ir ao banco
        return await self.session.get(self.model, id)

    async def list(self, *filters, limit=20, offset=0) -> list[ModelT]:
        # select() constrói a query
        # .where(*filters) adiciona condições WHERE
        # .limit() e .offset() fazem paginação
        stmt = select(self.model).where(*filters).limit(limit).offset(offset)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def add(self, obj: ModelT) -> ModelT:
        self.session.add(obj)     # adiciona ao contexto da sessão
        await self.session.flush() # envia ao banco MAS não faz commit
        await self.session.refresh(obj)  # recarrega para pegar server_defaults
        return obj
```

**flush vs commit:**
- `flush()` envia as mudanças ao banco dentro da transação atual (ainda pode ser revertido)
- `commit()` finaliza a transação permanentemente (não pode ser revertido)
- O commit acontece automaticamente no `get_db()` quando o endpoint termina sem erros

### Queries com SQLAlchemy

```python
# SELECT * FROM users WHERE email = 'joao@bar.com' AND deleted_at IS NULL
stmt = (
    select(User)
    .where(
        User.email == email,          # condição de igualdade
        User.deleted_at.is_(None),    # IS NULL — use .is_(None), não == None
    )
)
result = await session.execute(stmt)
user = result.scalar_one_or_none()  # retorna um objeto ou None

# scalar_one()         → retorna um ou lança exceção
# scalar_one_or_none() → retorna um ou None (seguro)
# scalars().all()      → retorna lista
```

---

## 11. Services — Lógica de Negócio

O **Service Layer** contém as regras de negócio. Não fala com o banco diretamente — delega ao repository.

### BaseService — Contexto de Tenant

```python
class BaseService:
    def __init__(
        self,
        session: AsyncSession,
        company_id: UUID,           # qual empresa está ativa
        establishment_id: UUID | None = None,
        user_id: UUID | None = None,
    ) -> None:
        self.session = session
        self.company_id = company_id
```

**Por que carregar o `company_id` no service?**

Em um sistema multi-tenant, toda operação deve estar "dentro" de uma empresa. Ao inicializar o service com `company_id`, garantimos que nenhuma query acidentalmente vaze dados de uma empresa para outra.

### Separação entre Service e Repository

```
Service (REGRAS):             Repository (DADOS):
─────────────────             ──────────────────
"Usuário está ativo?"   →     SELECT * FROM users WHERE id = ?
"Senha correta?"
"Gerar token JWT"
"Lançar erro se inválido"
```

---

## 12. API — Endpoints e Dependências

### O que é Dependency Injection (DI)?

Em vez de criar objetos manualmente em cada endpoint, o FastAPI **injeta** automaticamente o que você precisar.

```python
# Sem DI (repetitivo e propenso a erros):
@router.get("/me")
async def me():
    session = AsyncSession(engine)  # criando manualmente
    token = request.headers.get("Authorization")  # extraindo manualmente
    ...

# Com DI (o FastAPI cuida de tudo):
@router.get("/me")
async def me(
    session: DBSession,          # ← FastAPI cria e fecha a sessão
    current_user: CurrentUser,   # ← FastAPI decodifica o JWT e busca o usuário
):
    return current_user
```

### app/api/deps.py

```python
# DBSession: cria sessão, injeta, fecha no final
DBSession = Annotated[AsyncSession, Depends(get_db)]

# CurrentUser: extrai token → decodifica JWT → busca usuário no banco
CurrentUser = Annotated[User, Depends(get_current_user)]

# CurrentUserId: apenas o UUID do usuário (sem query no banco — mais leve)
CurrentUserId = Annotated[UUID, Depends(get_current_user_id)]
```

### OAuth2PasswordBearer

```python
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")
```

Isso diz ao FastAPI que os endpoints que usam este scheme esperam um `Authorization: Bearer <token>` no header. O Swagger UI (`/docs`) automaticamente mostra um botão "Authorize" para facilitar os testes.

### Como um endpoint usa tudo isso

```python
@router.get("/me", response_model=UserMeResponse)
async def me(current_user: CurrentUser) -> UserMeResponse:
    # current_user já foi:
    # 1. extraído do header Authorization
    # 2. validado pelo JWT
    # 3. buscado no banco de dados
    # Tudo isso automático pela dependência CurrentUser
    return UserMeResponse.model_validate(current_user)
```

---

## 13. Fluxo Completo de uma Requisição

Exemplo: `GET /api/v1/auth/me` com token JWT válido.

```
1. Cliente envia:
   GET /api/v1/auth/me
   Authorization: Bearer eyJhbGci...

2. FastAPI recebe a requisição
   └── Chama a função me() do endpoint

3. FastAPI resolve as dependências:
   a) DBSession:
      └── Cria AsyncSession
      └── Abre transação no banco
   b) CurrentUser (depende de DBSession):
      └── OAuth2PasswordBearer extrai o token do header
      └── decode_token() verifica assinatura e expiração
      └── Extrai user_id do payload
      └── UserRepository.get(user_id) → SELECT FROM users WHERE id = ?
      └── Verifica se user.is_active == True
      └── Retorna objeto User

4. FastAPI executa a função me():
   └── me(current_user=<User object>)
   └── UserMeResponse.model_validate(current_user) ← converte para schema
   └── return UserMeResponse

5. FastAPI serializa a resposta:
   └── Pydantic converte UserMeResponse para dict
   └── FastAPI serializa para JSON
   └── HTTP 200 {"id": "...", "email": "...", ...}

6. FastAPI finaliza:
   └── DBSession: commit() (sem erros) ou rollback() (com erros)
   └── Fecha a sessão
```

---

## 14. Fluxo de Autenticação JWT

### Login

```
POST /auth/login
{"email": "joao@bar.com", "password": "senha123"}
         │
         ▼
AuthService.login()
         │
         ├── UserRepository.get_by_email(email)
         │   └── SELECT * FROM users WHERE email = ? AND deleted_at IS NULL
         │
         ├── verify_password(password, user.password_hash)
         │   └── bcrypt compara senha com hash
         │
         ├── Se inválido → raise AuthenticationError → HTTP 401
         │
         └── create_access_token(user.id, {company_id, role})
             └── JWT assinado com SECRET_KEY
             └── Retorna {"access_token": "eyJ...", "token_type": "bearer"}
```

### Requisições autenticadas

```
GET /auth/me
Authorization: Bearer eyJhbGci...
         │
         ▼
get_current_user (dependency)
         │
         ├── decode_token(token)
         │   ├── Verifica assinatura com SECRET_KEY
         │   ├── Verifica expiração (exp)
         │   └── Extrai payload → {sub, company_id, role, ...}
         │
         ├── UserRepository.get(UUID(payload["sub"]))
         │
         ├── Se não encontrado ou inativo → HTTP 401
         │
         └── Retorna objeto User
             └── FastAPI injeta em current_user no endpoint
```

### Segurança do JWT

```
Token = HEADER.PAYLOAD.SIGNATURE

PAYLOAD (Base64, legível):
{"sub": "uuid...", "role": "MANAGER", "exp": 1716307200}

SIGNATURE (HMAC-SHA256):
HMAC(base64(HEADER) + "." + base64(PAYLOAD), SECRET_KEY)
```

**O token NÃO é criptografado** — apenas assinado. Qualquer um pode ler o payload fazendo `base64.decode()`. **Nunca coloque senhas ou dados sensíveis no JWT.**

O que garante a segurança é a **assinatura**: sem o `SECRET_KEY`, é impossível criar ou modificar um token válido.

---

## 15. Multi-Tenancy — Como Funciona

Todo dado no sistema pertence a uma `Company`. Isso garante que o Restaurante A nunca veja os dados do Restaurante B.

```
Company A (id: aaa-111)
  ├── users WHERE company_id = 'aaa-111'
  ├── establishments WHERE company_id = 'aaa-111'
  └── (todos os dados filtrados por company_id)

Company B (id: bbb-222)
  ├── users WHERE company_id = 'bbb-222'
  └── (completamente separado)
```

O `company_id` viaja no JWT. Assim, o service sabe automaticamente de qual empresa a requisição pertence sem precisar perguntar ao banco todas as vezes.

```python
# O token carrega o company_id
payload = decode_token(token)
company_id = UUID(payload["company_id"])

# O service é inicializado com o contexto do tenant
service = OrderService(session, company_id=company_id)

# Toda query do service filtra por company_id automaticamente
orders = await service.list_open_orders()
# → SELECT * FROM orders WHERE establishment_id IN (
#     SELECT id FROM establishments WHERE company_id = 'aaa-111'
#   )
```

---

## 16. Docker e Infraestrutura

### docker-compose.yml

```yaml
services:
  db:           # PostgreSQL
    image: postgres:16-alpine
    ports: ["5432:5432"]     # expõe a porta para o host (localhost:5432)
    healthcheck:             # só marca como "healthy" quando aceitar conexões
      test: ["CMD-SHELL", "pg_isready -U barrio"]

  api:          # FastAPI (quando rodar tudo em Docker)
    depends_on:
      db:
        condition: service_healthy  # só sobe depois do banco estar pronto
    environment:
      POSTGRES_HOST: db    # dentro do Docker, o banco é "db", não "localhost"
```

**Por que `POSTGRES_HOST: db` no container?**

Dentro da rede Docker, cada serviço tem seu próprio `localhost`. O serviço `api` não pode usar `localhost:5432` — o banco não está lá. O Docker cria uma rede interna onde cada serviço é acessível pelo seu nome (`db`).

```
Host (sua máquina):     localhost:5432 → redireciona para → Container db:5432
Container api:          db:5432 → acessa diretamente pela rede Docker
```

---

## 17. Decisões Arquiteturais

### Por que SQLAlchemy 2.0 com Mapped/mapped_column?

A sintaxe nova do SQLAlchemy 2.0 usa **type hints** nativos do Python:

```python
# Sintaxe antiga (1.x) — sem type hints:
class User(Base):
    name = Column(String(200), nullable=False)

# Sintaxe nova (2.0) — com type hints:
class User(Base):
    name: Mapped[str] = mapped_column(String(200), nullable=False)
```

Benefícios: IDEs entendem os tipos, mypy pode verificar erros, código mais legível.

### Por que `expire_on_commit=False`?

```python
AsyncSessionLocal = async_sessionmaker(
    expire_on_commit=False,  # ← por quê?
    ...
)
```

Por padrão, após um `commit()`, o SQLAlchemy "expira" todos os atributos dos objetos (marca como "precisa recarregar"). No modo async, tentar acessar um atributo expirado gera um erro porque não há conexão aberta.

Com `expire_on_commit=False`, os objetos mantêm seus valores após o commit, evitando erros inesperados.

### Por que `autoflush=False`?

```python
async_sessionmaker(autoflush=False)
```

Com `autoflush=True`, o SQLAlchemy enviaria automaticamente as mudanças ao banco antes de cada query. No modo async, isso pode causar comportamentos inesperados. Preferimos controle explícito com `session.flush()`.

### Por que `Numeric(12, 2)` para dinheiro e não `float`?

```python
price: Mapped[Decimal] = mapped_column(Numeric(12, 2))  # ← correto
price: Mapped[float] = mapped_column(Float)              # ← NUNCA para dinheiro!
```

`float` tem imprecisão binária:
```python
>>> 0.1 + 0.2
0.30000000000000004  # não é 0.30!
```

`Numeric(12, 2)` armazena exatamente 2 casas decimais. `R$ 99.99` é sempre `99.99`, nunca `99.98999...`.

---

## 18. Comandos do Dia-a-Dia

```bash
# Banco de dados
make db-up          # sobe o PostgreSQL no Docker
make db-down        # para e remove os containers
make db-shell       # abre psql interativo

# Migrations
make migrate-gen    # gera nova migration (pede um nome)
make migrate-up     # aplica todas as migrations pendentes
make migrate-down   # reverte a última migration
make migrate-history # lista o histórico de migrations

# Backend
make dev            # inicia o servidor FastAPI com hot-reload
make validate-models # verifica imports e tabelas dos models
make validate-db    # testa conexão com o banco

# Comandos diretos (quando Makefile não for suficiente)
cd backend
python3 -m alembic revision --autogenerate -m "add_column_x"
python3 -m alembic upgrade head
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

---

## 19. Módulo de Mesas (Tables)

Primeiro módulo CRUD completo do BarrioERP. Implementado em 2026-05-21.

### Endpoints

| Método | URL | Descrição | Auth |
|--------|-----|-----------|------|
| `POST` | `/api/v1/tables/` | Criar mesa | Sim |
| `GET` | `/api/v1/tables/` | Listar mesas do estabelecimento | Sim |
| `GET` | `/api/v1/tables/{id}` | Buscar mesa específica | Sim |
| `PATCH` | `/api/v1/tables/{id}` | Atualizar campos da mesa | Sim |
| `DELETE` | `/api/v1/tables/{id}` | Desativar mesa (soft delete) | Sim |

### Arquivos criados

```
backend/app/
├── schemas/table.py            # TableCreate, TableUpdate, TableResponse
├── repositories/table_repository.py  # SQL isolado nesta camada
├── services/table_service.py   # Regras de negócio
└── api/v1/endpoints/tables.py  # Endpoints HTTP
```

### Decisões de design

**Soft delete via `is_active`**

O modelo `Table` não usa `SoftDeleteMixin` (que tem `deleted_at`). Em vez disso, usa `is_active: bool`. Motivo: mesas podem ser **reativadas** — sem necessidade de registrar o timestamp de "quando foi desativada". A coluna `deleted_at` é para quando a data de exclusão importa (ex: usuários deletados precisam de auditoria).

O `DELETE /tables/{id}` não deleta fisicamente. Seta `is_active = False`. O registro continua no banco para preservar o histórico de comandas.

**Multi-tenancy por `establishment_id`**

Toda query de mesa inclui `WHERE establishment_id = ?`. O `establishment_id` vem do JWT do usuário logado — não do corpo da requisição. Isso garante isolamento: um garçom do Restaurante A nunca vê as mesas do Restaurante B, mesmo que tente forçar um ID na URL.

O `TableRepository.get_by_establishment()` filtra por `id` E `establishment_id` juntos. Se o `table_id` pertencer a outro tenant, o resultado é `None` → `NotFoundError` → HTTP 404.

**Locking otimista no PATCH**

O campo `version` é obrigatório no `TableUpdate`. O fluxo correto é:

```
1. GET /tables/uuid           → recebe mesa com version=3
2. Usuário edita na interface
3. PATCH /tables/uuid         → envia {"label": "...", "version": 3}
4. Service: data.version (3) == table.version (3) → OK
5. Banco incrementa version para 4 automaticamente
```

Se outro usuário editou no meio do caminho (version virou 4):
- `data.version (3) ≠ table.version (4)` → `OptimisticLockError` → HTTP 409

O cliente deve recarregar o recurso e tentar novamente.

**PATCH parcial com `model_dump(exclude_unset=True)`**

O Pydantic v2 distingue entre "campo não enviado" e "campo enviado como null":

```json
{"label": "Mesa 5", "version": 3}      → só label é atualizado
{"section": null, "version": 3}         → section é limpo (NULL)
{"label": "Mesa 5", "section": null, "version": 3}  → ambos
```

`model_dump(exclude_unset=True)` retorna só os campos explicitamente enviados. Assim o PATCH não sobrescreve campos que o cliente não mencionou.

**`TenantError` para usuário sem estabelecimento**

`User.establishment_id` é nullable. Um usuário OWNER pode não estar vinculado a um estabelecimento específico. Para listar mesas, precisamos saber de qual estabelecimento — se `establishment_id` for `None`, lançamos `TenantError` (HTTP 400).

**Unicidade de número por estabelecimento**

O número da mesa (ex: "Mesa 5") deve ser único dentro de cada estabelecimento. Isso é garantido em dois níveis:

1. **Código**: `get_by_number()` verifica antes do INSERT → mensagem de erro amigável
2. **Banco**: índice único `(establishment_id, number)` → proteção contra race conditions

Se dois requests simultâneos passarem pela verificação #1, o banco rejeita o segundo com `IntegrityError`, que é capturado e convertido em `ConflictError` (HTTP 409).

**Regra de negócio no DELETE**

Mesa com `status = OCCUPIED` não pode ser desativada — pode ter comanda aberta. O Service verifica e lança `BusinessRuleError` (HTTP 422) com mensagem explicativa. Mesas em outros status (FREE, RESERVED, BLOCKED, BILL_REQUESTED) podem ser desativadas.

---

## 20. Módulo de Comandas (Orders)

Segundo módulo CRUD do BarrioERP. Implementado em 2026-05-21.
Introduz relacionamentos 1:N, transações multi-tabela, snapshot de preço e locking otimista.

### Endpoints

| Método | URL | Descrição | Auth |
|--------|-----|-----------|------|
| `POST` | `/api/v1/orders/` | Abrir comanda para uma mesa | Sim |
| `GET` | `/api/v1/orders/open` | Listar comandas abertas | Sim |
| `GET` | `/api/v1/orders/{id}` | Detalhes da comanda com itens | Sim |
| `POST` | `/api/v1/orders/{id}/items` | Adicionar item à comanda | Sim |
| `PATCH` | `/api/v1/orders/{id}/close` | Fechar comanda | Sim |

### Arquivos criados

```
backend/app/
├── schemas/order.py              # OrderCreate, OrderItemAdd, OrderClose, OrderResponse, OrderItemResponse
├── repositories/order_repository.py  # get_open_by_table, get_with_items, list_open, get_available_menu_item
├── services/order_service.py     # open_order, list_open, get, add_item, close_order
└── api/v1/endpoints/orders.py    # 5 endpoints HTTP
```

### Modelo de dados: Order vs OrderItem

```
orders (cabeçalho da comanda — uma linha por comanda)
───────────────────────────────────────────────────────
id | establishment_id | table_id | status | total | closed_at | version
A1 |      estab1      |  mesa5   |  open  | 87.00 |   null    |    3

order_items (produtos pedidos — N linhas por comanda)
───────────────────────────────────────────────────────
id | order_id | item_name          | unit_price | qty | subtotal
B1 |    A1    | Cerveja Heineken   |   12.00    |  1  |  12.00
B2 |    A1    | Frango com Fritas  |   27.00    |  2  |  54.00
B3 |    A1    | Suco de laranja    |    9.00    |  1  |   9.00
```

Isso é um **relacionamento 1:N**: uma Order tem muitos OrderItems.

### Decisões de design

**Snapshot de preço no OrderItem**

`OrderItem` armazena `item_name` e `unit_price` como **snapshot** — uma cópia dos valores no momento do pedido. Mesmo que o cardápio mude de preço ou nome amanhã, o histórico de comandas permanece correto. Isso é obrigatório em sistemas financeiros.

**Total calculado pelo servidor**

O cliente nunca envia preços — apenas `menu_item_id` e `quantity`. O servidor busca o preço no banco e calcula o subtotal. Regra de ouro: nunca confie em cálculos financeiros do cliente.

**Fórmula de totais:**
```
item.subtotal = item.unit_price × item.quantity
order.subtotal = Σ subtotais dos itens ativos (não cancelados)
order.total = order.subtotal + order.service_fee - order.discount
```

**Transação multi-tabela ao abrir comanda**

Ao abrir uma comanda, duas tabelas são modificadas na mesma transação:
1. `INSERT INTO orders` — cria a comanda
2. `UPDATE tables SET status = 'occupied'` — ocupa a mesa

Se qualquer operação falhar → `rollback()` → nenhuma mudança persiste.

Ao fechar a comanda, o inverso:
1. `UPDATE orders SET status = 'closed', closed_at = now()` — fecha
2. `UPDATE tables SET status = 'free'` — libera a mesa

**Locking otimista no fechamento**

`OrderClose` exige `version` — o número de versão atual da comanda. Se dois usuários tentarem fechar ao mesmo tempo, apenas o primeiro tem sucesso. O segundo recebe `HTTP 409 Conflict` e deve recarregar a comanda.

`version` NÃO é exigido ao adicionar itens — append é uma operação segura para concorrência. O `StaleDataError` do SQLAlchemy ainda protege contra atualizações conflitantes no total.

**Eager loading com selectinload**

Como SQLAlchemy async não suporta lazy loading fora de contexto, todo acesso a `order.items` exige eager loading explícito:

```python
.options(selectinload(Order.items))
```

Isso gera 2 queries (nunca N+1):
- Query 1: busca as orders
- Query 2: busca todos os items de uma vez com `WHERE order_id IN (ids...)`

**Rota estática antes de rota dinâmica**

`GET /orders/open` deve ser registrado **antes** de `GET /orders/{order_id}`. FastAPI usa first-match — se `/{order_id}` viesse primeiro, "open" seria tratado como UUID e daria erro de validação.

**Verificação de tenant no MenuItem**

`MenuItem` não tem `establishment_id` direto. O vínculo é `MenuItem → MenuCategory → Establishment`. O `get_available_menu_item()` faz JOIN com `menu_categories` para validar o tenant antes de usar o item.

**Dois modos para adicionar item**

1. **Via cardápio** (`menu_item_id` informado): preço e nome vêm do banco (snapshot)
2. **Manual** (`menu_item_id` = null): `item_name` e `unit_price` obrigatórios

O schema usa `model_validator(mode="after")` para validação cruzada entre campos.

---

## 21. Módulo de Pagamentos (Payments)

Terceiro módulo do BarrioERP. Implementado em 2026-05-21.
Introduz aritmética financeira com Decimal, verificação de saldo, pagamentos parciais e finalização com garantia de integridadade.

### Endpoints

| Método | URL | Descrição | Auth |
|--------|-----|-----------|------|
| `POST` | `/api/v1/payments` | Registrar pagamento | Sim |
| `GET` | `/api/v1/orders/{id}/payments` | Listar pagamentos da comanda | Sim |
| `PATCH` | `/api/v1/orders/{id}/finish` | Finalizar comanda (com verificação financeira) | Sim |

### Arquivos criados

```
backend/app/
├── schemas/payment.py             # PaymentCreate, PaymentResponse, OrderFinish
├── repositories/payment_repository.py  # list_by_order, sum_confirmed_by_order
├── services/payment_service.py    # register, list_for_order, finish
└── api/v1/endpoints/payments.py   # 3 endpoints HTTP (prefixos mistos)
```

### Por que float QUEBRA sistemas financeiros

```python
# Float (errado):
0.1 + 0.2 = 0.30000000000000004   ← erro de ponto flutuante binário
33.33 * 3 = 99.99000000000001     ← centavo extra!

# Decimal (correto):
Decimal("0.1") + Decimal("0.2") = Decimal("0.3")
Decimal("33.33") * 3 = Decimal("99.99")
```

Regra absoluta: dinheiro → `Decimal`, banco → `NUMERIC(12,2)`, nunca `float`.

### Fluxo financeiro completo

```
1. POST /orders                    → comanda aberta, total=0
2. POST /orders/{id}/items × N     → itens adicionados, total calculado
3. POST /payments                  → pagamento parcial (se necessário)
   POST /payments                  → mais pagamentos até cobrir o total
4. PATCH /orders/{id}/finish       → verifica total_pago >= total → CLOSED + mesa FREE
```

### Invariantes financeiras garantidas

| Invariante | Como é garantida |
|------------|-----------------|
| `total_pago ≤ total_comanda` | Verificação no `register()` antes do INSERT |
| Comanda só fecha se paga | Verificação no `finish()` antes do UPDATE |
| Pagamentos são imutáveis | Sem endpoint DELETE, sem campo de edição |
| Atomicidade de finish | Mesma `session` → mesmo commit para order + table |

### sum_confirmed_by_order — a query financeira central

```python
SELECT SUM(amount) FROM payments
WHERE order_id = ? AND status = 'confirmed'
```

- Retorna `Decimal("0")` (não `None`) quando não há pagamentos — tratado explicitamente
- Filtra apenas `CONFIRMED` — ignora PENDING, FAILED, REFUNDED
- Usado em `register()` (verificar saldo) e `finish()` (verificar suficiência)

### Roteamento misto sem prefixo

O payments router é registrado **sem prefix** para suportar URLs em dois domínios:
- `POST /payments` — criação de pagamento
- `GET /orders/{id}/payments` — pagamentos de uma comanda (semanticamente ligado à Order)
- `PATCH /orders/{id}/finish` — finalização com verificação financeira

```python
api_router.include_router(payments.router, tags=["payments"])  # sem prefix
```

### Dois caminhos de fechamento (design intencional)

| Endpoint | Service | Verifica pagamento? | Quando usar |
|----------|---------|--------------------|-|
| `PATCH /orders/{id}/close` | OrderService | Não | Override do gerente, cancelamento |
| `PATCH /orders/{id}/finish` | PaymentService | Sim | Fluxo normal de pagamento |

### Campos de dinheiro no Payment

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `amount` | `Numeric(12,2)` | Valor APLICADO à comanda — nunca excede saldo devedor |
| `amount_tendered` | `Numeric(12,2)` | Para cash: quanto o cliente entregou fisicamente |
| `change_given` | `Numeric(12,2)` | Para cash: troco calculado pelo servidor |

### Limitação documentada: race condition no saldo

Dois caixas registrando o último pagamento exatamente ao mesmo tempo podem ambos passar pela verificação de saldo. Solução completa seria `SELECT FOR UPDATE` (pessimistic locking) na comanda durante o registro. Não implementado nesta versão — documentado para evolução futura.

---

---

## 22. Módulo de Cardápio (Menu)

Quarto módulo do BarrioERP. Implementado em 2026-05-21.
Introduz dados de catálogo, soft delete com cascade manual e relacionamentos indiretos de multi-tenancy.

### Endpoints

| Método | URL | Descrição |
|--------|-----|-----------|
| `POST` | `/api/v1/menu/categories` | Criar categoria |
| `GET` | `/api/v1/menu/categories` | Listar categorias |
| `PATCH` | `/api/v1/menu/categories/{id}` | Atualizar categoria |
| `DELETE` | `/api/v1/menu/categories/{id}` | Soft-delete categoria (+ cascade itens) |
| `POST` | `/api/v1/menu/items` | Criar item |
| `GET` | `/api/v1/menu/items` | Listar itens com filtros |
| `GET` | `/api/v1/menu/items/{id}` | Buscar item específico |
| `PATCH` | `/api/v1/menu/items/{id}` | Atualizar item |
| `DELETE` | `/api/v1/menu/items/{id}` | Soft-delete item |

### Arquivos criados

```
backend/app/
├── schemas/menu.py            # CategoryCreate/Update/Response, MenuItemCreate/Update/Response
├── repositories/menu_repository.py  # MenuCategoryRepository + MenuItemRepository
├── services/menu_service.py   # 9 métodos de negócio em 2 grupos
└── api/v1/endpoints/menu.py   # 9 endpoints HTTP com query params
```

### Catálogo vs Transação — dois mundos diferentes

| Característica | Catálogo (Menu) | Transação (Order, Payment) |
|----------------|-----------------|---------------------------|
| Frequência de mudança | Raramente | Muito frequente |
| VersionMixin | Não | Sim |
| Concorrência | Baixa | Alta |
| Impacto de conflito | Baixo | Financeiro |
| Soft delete | Sim | Não se aplica |
| Histórico via snapshot | Não | Sim (OrderItem) |

### Multi-tenancy indireta via JOIN

`MenuItem` não tem `establishment_id`. O vínculo é:
```
MenuItem.category_id → MenuCategory.id → MenuCategory.establishment_id
```

Para verificar tenant de um item, todas as queries fazem JOIN:
```sql
SELECT menu_items.* FROM menu_items
JOIN menu_categories ON menu_items.category_id = menu_categories.id
WHERE menu_items.id = ?
  AND menu_categories.establishment_id = ?
```

### Cascade soft delete manual (Categoria → Itens)

Ao deletar uma categoria, o service executa em sequência dentro da mesma transação:
1. `item_repo.soft_delete_all_in_category(category_id)` → todos os itens recebem `deleted_at`
2. `category.soft_delete()` → categoria recebe `deleted_at`
3. `session.flush()` → ambas as operações são enviadas atomicamente

O `ON DELETE CASCADE` do banco só funciona para DELETE físico — soft delete é lógica de aplicação.

### Por que produtos nunca são deletados fisicamente

`OrderItem.menu_item_id` usa `ondelete="SET NULL"`. Se um MenuItem fosse fisicamente deletado:
- `menu_item_id` nos `OrderItems` viraria `NULL` automaticamente
- O snapshot (`item_name`, `unit_price`) ainda preservaria os dados financeiros
- Mas a referência ao cardápio seria perdida para análise histórica

Soft delete preserva o registro completo — pedidos históricos ainda apontam para o item correto.

### Atualização de preço — não retroativa

Quando `PATCH /menu/items/{id}` altera `price`:
- `MenuItem.price` é atualizado para pedidos futuros
- `OrderItem.unit_price` de pedidos passados **não muda** (snapshot imutável)
- Isso é a proteção da integridade financeira histórica

### is_active vs is_available

| Flag | Significado | Quem altera | Quando |
|------|-------------|-------------|--------|
| `is_active` | Item existe no cardápio | Gerente | Decisão permanente |
| `is_available` | Item pode ser pedido agora | Garçom/Gerente | Esgotou hoje |

### Filtros combinados no GET /menu/items

```
GET /menu/items?available_only=true          → para garçom tomar pedido
GET /menu/items?active_only=false            → gerente vê tudo
GET /menu/items?category_id=uuid             → por categoria
GET /menu/items?category_id=uuid&page=2      → paginado
```

Construção condicional de query no SQLAlchemy:
```python
stmt = base_query
if category_id: stmt = stmt.where(...)
if active_only: stmt = stmt.where(...)
```

*Última atualização: 2026-05-21*
