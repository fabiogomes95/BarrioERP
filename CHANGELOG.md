# BarrioERP — Changelog de Desenvolvimento

> Registro cronológico de tudo que foi implementado, decisão por decisão.
> Atualizar a cada sessão de trabalho.

---

## [v0.2.0] — Módulos de Usuários, Onboarding e Frontend base

### Backend — Módulo de Usuários

**Arquivos criados:**
- `backend/app/schemas/user.py`
- `backend/app/services/user_service.py`
- `backend/app/api/v1/endpoints/users.py`

**Arquivos modificados:**
- `backend/app/repositories/user_repository.py` — 4 métodos novos adicionados

**Endpoints adicionados (`/api/v1/users`):**

| Método | Rota | Descrição |
|--------|------|-----------|
| POST | `/users/` | Criar usuário |
| GET | `/users/` | Listar com filtros e paginação |
| GET | `/users/{id}` | Buscar por ID |
| PATCH | `/users/{id}` | Atualizar parcialmente (PATCH) |
| DELETE | `/users/{id}` | Soft delete |
| PATCH | `/users/{id}/password` | Trocar/resetar senha |

**Funcionalidades:**
- RBAC completo: OWNER > MANAGER > CASHIER/WAITER/KITCHEN
- MANAGER não pode criar/editar/deletar OWNERs
- Proteção do último owner: empresa nunca fica sem administrador
- Auto-troca de senha (requer senha atual) vs reset por gestor (sem senha atual)
- Multi-tenancy: todos os métodos filtram por `company_id`

**Métodos adicionados ao `UserRepository`:**
- `get_by_company(user_id, company_id)` — busca segura para multi-tenant
- `count_active_owners(company_id)` — proteção do último owner
- `email_taken_in_company(email, company_id, *, exclude_user_id)` — unicidade de e-mail
- `list_by_company(...)` — filtros por role, establishment_id, active_only

---

### Backend — Módulo de Onboarding (primeiro acesso)

**Arquivos criados:**
- `backend/app/schemas/onboarding.py`
- `backend/app/services/onboarding_service.py`
- `backend/app/api/v1/endpoints/onboarding.py`

**Arquivo modificado:**
- `backend/app/core/config.py` — adicionado `ONBOARDING_SECRET`
- `backend/.env` — adicionado `ONBOARDING_SECRET`
- `backend/app/api/v1/router.py` — registrado o novo router

**Endpoint adicionado:**

| Método | Rota | Descrição |
|--------|------|-----------|
| POST | `/api/v1/onboarding/register` | Cadastro do primeiro acesso |

**Fluxo do onboarding:**
1. Usuário preenche: nome do bar, nome do dono, e-mail, senha, telefone, endereço
2. Backend cria em transação atômica: `Company` + `Establishment("Matriz")` + `User(OWNER)`
3. Retorna JWT imediatamente — usuário já entra autenticado

**Decisões de design:**
- Endpoint público (sem JWT) protegido por header `X-Onboarding-Secret`
- `OnboardingService` não herda `BaseService` (tenant ainda não existe)
- Establishment criado automaticamente como "Matriz" — usuário não precisa saber dessa divisão interna
- Slug gerado via `unicodedata` (sem dependência externa): "Bar do João" → "bar-do-joao"
- Slug com sufixo incremental se colidir: "bar-do-joao-2", "bar-do-joao-3"...

---

### Backend — Gaps corrigidos

#### Gap 1 — Cancelar item da comanda
**Arquivos modificados:**
- `backend/app/repositories/order_repository.py` — adicionado `get_item(item_id, order_id)`
- `backend/app/services/order_service.py` — adicionado `cancel_item(...)`
- `backend/app/api/v1/endpoints/orders.py` — adicionado endpoint
- `backend/app/schemas/order.py` — adicionados `cancelled_at` e `cancelled_reason` no `OrderItemResponse`

**Endpoint adicionado:**

| Método | Rota | Descrição |
|--------|------|-----------|
| DELETE | `/orders/{id}/items/{item_id}` | Cancela item com motivo opcional |

**Regras de negócio:**
- Comanda deve estar OPEN ou BILL_REQUESTED
- Item não pode estar CANCELLED (já cancelado)
- Item não pode estar SERVED (já foi entregue — requer estorno manual)
- Total da comanda recalculado automaticamente após cancelamento
- Motivo opcional via query param: `?reason=Pedido+errado`

#### Gap 2 — Token de longa duração
- `ACCESS_TOKEN_EXPIRE_MINUTES` alterado de 60 para **10080** (7 dias)
- Justificativa: sistema usado em rede local, turnos de 8-12 horas inviabilizam tokens curtos

#### Gap 3 — Filtro por mesa em `GET /orders/open`
**Arquivos modificados:**
- `backend/app/repositories/order_repository.py` — `list_open` aceita `table_id` opcional
- `backend/app/services/order_service.py` — `list_open` aceita `table_id` opcional
- `backend/app/api/v1/endpoints/orders.py` — query param `?table_id=uuid`

**Uso:**
```
GET /api/v1/orders/open              → todas as comandas abertas
GET /api/v1/orders/open?table_id=uuid → comanda da mesa específica
```

#### Outras correções
- Mensagem de erro de login traduzida: `"Invalid credentials"` → `"E-mail ou senha incorretos"`

---

### Frontend — Criação do projeto

**Stack:**
- Vite 8 + React 19 + TypeScript
- Tailwind CSS v4 (plugin `@tailwindcss/vite`)
- React Router DOM v7

**Estrutura criada:**
```
frontend/
├── src/
│   ├── lib/
│   │   └── api.ts           # Camada de comunicação com o backend
│   ├── components/
│   │   └── Layout.tsx       # Shell: barra de abas + menu suspenso
│   ├── pages/
│   │   ├── LoginPage.tsx    # Tela de login funcional
│   │   ├── MesasPage.tsx    # Placeholder
│   │   ├── PedidosPage.tsx  # Placeholder
│   │   ├── CardapioPage.tsx # Placeholder
│   │   └── EquipePage.tsx   # Placeholder
│   ├── App.tsx              # Routing + ProtectedRoute
│   ├── index.css            # @import "tailwindcss"
│   └── main.tsx             # Ponto de entrada React
├── vite.config.ts           # Plugin Tailwind + proxy /api → :8000
└── package.json
```

**Funcionalidades implementadas:**

1. **Tela de Login**
   - Formulário com e-mail e senha
   - Chamada real à API (`POST /api/v1/auth/login`)
   - Token salvo no `localStorage` como `barrio_token`
   - Dados do usuário decodificados do JWT (sem biblioteca, via `atob`)
   - Mensagem de erro em vermelho para credenciais inválidas
   - Redirect automático para `/mesas` após login

2. **Proteção de rotas**
   - `ProtectedRoute` redireciona para `/login` se não há token
   - Todas as rotas dentro de `/` são protegidas

3. **Layout com abas**
   - Barra de abas no topo: **Pedidos** e **Mesas** (aba ativa com borda inferior roxa)
   - Menu suspenso `≡` no canto esquerdo: Cardápio, Equipe, nome do usuário, Sair
   - Abre direto em `/mesas` após login
   - URL reflete a aba ativa (navegação com React Router)

4. **Proxy de API**
   - Vite configurado com proxy: `/api` → `http://localhost:8000`
   - Sem CORS em desenvolvimento, sem URL hardcodada no código

---

## [v0.1.0] — Versão inicial do backend

> Commit inicial com toda a API REST do backend implementada.

**Módulos:**
- Auth (login, /me)
- Tables — CRUD completo de mesas
- Orders — Abrir comanda, adicionar itens, fechar, finalizar
- Payments — Registrar pagamento, listar por comanda
- Menu — Categorias e itens do cardápio

**Infraestrutura:**
- FastAPI + SQLAlchemy 2.0 async + PostgreSQL 16 + Alembic
- JWT com HS256, bcrypt para senhas
- Multi-tenancy: Company → Establishment → Users/Tables/Orders
- Soft delete, Optimistic Locking (VersionMixin), RBAC

---

## Estado atual do sistema

### Backend — 32 endpoints

| Módulo | Endpoints | Status |
|--------|-----------|--------|
| Auth | 2 | ✅ |
| Onboarding | 1 | ✅ |
| Tables | 5 | ✅ |
| Orders | 7 | ✅ |
| Payments | 3 | ✅ |
| Menu | 8 | ✅ |
| Users | 6 | ✅ |

### Frontend — Páginas

| Página | Rota | Status |
|--------|------|--------|
| Login | `/login` | ✅ Funcional |
| Mesas | `/mesas` | 🔲 Placeholder |
| Pedidos | `/pedidos` | 🔲 Placeholder |
| Cardápio | `/cardapio` | 🔲 Placeholder |
| Equipe | `/equipe` | 🔲 Placeholder |

---

## Como rodar o projeto

```bash
# Backend
cd backend
uvicorn app.main:app --reload

# Frontend
cd frontend
npm run dev
```

Acessar: `http://localhost:5173`

**Primeiro acesso (criar estabelecimento):**
```bash
curl -X POST http://localhost:8000/api/v1/onboarding/register \
  -H "Content-Type: application/json" \
  -H "X-Onboarding-Secret: dev-onboarding-secret-altere-em-producao" \
  -d '{
    "bar_name": "Meu Bar",
    "owner_name": "Seu Nome",
    "email": "voce@seubar.com",
    "password": "senha123",
    "phone": "(11) 99999-0000"
  }'
```
