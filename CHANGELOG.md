# BarrioERP — Changelog de Desenvolvimento

> Registro cronológico de tudo que foi implementado, decisão por decisão.
> Atualizar a cada sessão de trabalho.

---

## [v0.4.0] — Equipe, Pagamentos (Caixa) e Dashboard

### Frontend — Página de Equipe (EquipePage.tsx)

**Arquivo:** `frontend/src/pages/EquipePage.tsx` — commit `ceb01f9`

CRUD completo de membros da equipe consumindo o módulo de Usuários do backend:

- Listagem de membros com `fetchUsers`, avatar com iniciais e badge de cargo
- Criar membro (nome, e-mail, senha, telefone, cargo)
- Editar membro (PATCH parcial), ativar/desativar (soft delete)
- Resetar senha de um membro (`resetUserPassword`)
- RBAC no frontend: ações de gestão visíveis conforme o cargo do usuário logado

---

### Frontend — Pagamentos / Caixa (PaymentModal na PedidosPage)

**Arquivos modificados:**
- `frontend/src/lib/api.ts` — funções e tipos de pagamento
- `frontend/src/pages/PedidosPage.tsx` — `PaymentModal` + integração no `OrderDetail`

**Camada de API adicionada (`api.ts`):**

| Função | Endpoint | Descrição |
|--------|----------|-----------|
| `fetchOrderPayments(orderId)` | `GET /orders/{id}/payments` | Lista pagamentos da comanda |
| `registerPayment(data)` | `POST /payments` | Registra um pagamento |
| `finishOrder(orderId, version)` | `PATCH /orders/{id}/finish` | Finaliza com cheque financeiro |

- Tipos `Payment` e `PaymentMethod` (`cash`, `credit_card`, `debit_card`, `pix`, `voucher`, `other`)
- **Valores enviados como string** (`amount.toFixed(2)`) — preserva precisão decimal, seguindo a regra "API → strings, nunca float" do schema do backend

**Fluxo do `PaymentModal`:**
1. Ao abrir, busca pagamentos já registrados e calcula `total`, `pago`, `falta`
2. Seletor de forma de pagamento (5 métodos com ícone)
3. Valor pré-preenchido com o saldo devedor; suporta **pagamento dividido** (vários pagamentos parciais)
4. Para dinheiro: campo "Recebido" com cálculo de **troco** ao vivo
5. Para cartão/Pix: campo de referência (NSU/txid) opcional
6. Quando `falta = 0` → botão **"Finalizar comanda e liberar mesa"** (`finishOrder`)

**Integração no `OrderDetail`:**
- Botão primário **"Receber R$ X"** abre o modal
- "Fechar sem pagamento (override)" mantido como ação discreta do gerente (`closeOrder`, sem cheque financeiro)
- Correção de tipo: `OrderItem` ganhou o campo `order_id` (o backend já o retornava; o tipo estava incompleto e quebrava o `tsc`)

---

### Frontend — Dashboard / Início (DashboardPage.tsx)

**Arquivos:**
- `frontend/src/pages/DashboardPage.tsx` (novo)
- `frontend/src/App.tsx` — rota `/dashboard` + index passa a redirecionar para ela
- `frontend/src/components/Layout.tsx` — item de nav "Início" (`IconHome`) no topo

Visão **ao vivo** da operação, calculada no cliente a partir de `fetchOpenOrders` + `fetchTables` (sem novos endpoints):

- **Cards de métrica:** total em aberto, ticket médio, contas pedidas, ocupação (%)
- **Comandas abertas há mais tempo:** top 5 por antiguidade, com atalho para Pedidos
- Saudação por horário, atalhos de navegação nos cards, skeleton de carregamento

> Observação: métricas de faturamento histórico (fechamento de caixa diário) dependem de endpoints de relatório no backend ainda não existentes — ficam como próximo passo.

---

## [v0.3.0] — Frontend SaaS completo (Mesas, Pedidos, Cardápio)

### Frontend — Layout SaaS (Layout.tsx reescrito)

**Arquivo modificado:** `frontend/src/components/Layout.tsx`

Reescrita completa do shell de navegação. Abandonado o modelo de abas no topo em favor de layout SaaS moderno:

- **Desktop (md+):** sidebar fixa de 56 (224 px) com marca, 4 itens de nav e perfil/logout no rodapé
- **Mobile (<768 px):** header fixo com marca + avatar dropdown + nav inferior fixa com 4 ícones
- Item ativo na sidebar: fundo `amber-500/10`, texto `amber-400` e ponto dourado à esquerda
- Item ativo no nav inferior: texto `amber-400` + glow drop-shadow + linha dourada abaixo
- Avatar: círculo com iniciais do usuário (`bg-amber-500/15`, borda `amber-500/25`)
- Logout: `clearToken()` + `navigate('/login', { replace: true })`
- Paleta: fundo `#0d0b08`, surface `#161210`, deep `#0f0d0a`, acento amber-500

---

### Frontend — LoginPage redesenhada

**Arquivo modificado:** `frontend/src/pages/LoginPage.tsx`

- Fundo escuro `#0d0b08` com gradiente radial âmbar sutil no topo
- Card centralizado (`max-w-[340px]`) com borda `stone-800/70` e fundo `#121009`
- Inputs com bordas `stone-800/80`, `focus:ring-amber-500/20`
- Botão `bg-amber-500` → `hover:bg-amber-400`
- Ícone SVG de alerta no card de erro

---

### Frontend — Página de Mesas (MesasPage.tsx)

**Arquivo criado:** `frontend/src/pages/MesasPage.tsx` — commit `c75ac06`

**Funcionalidades:**
- Dados reais da API (`fetchTables`)
- Filtros por status com chips clicáveis (Todas / Livre / Ocupada / Conta / Reservada / Bloqueada)
- Grid responsivo: `grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5`
- `TableCard`: barra de acento colorida à esquerda, número, badge de status, seção e capacidade
- `SkeletonCard`: placeholder animado durante carregamento
- Mapa de status → cor/label/hex para todas as 5 variantes

**Modais:**
- `NewTableModal`: criar mesa (número, label, capacidade, seção)
- `OpenOrderModal`: abrir comanda em mesa livre (contagem de pessoas + nome do cliente)
- `OccupiedModal`: mesa ocupada → navega para `/pedidos` com filtro pela mesa
- `ModalOverlay`: fecha com Escape + backdrop blur

---

### Frontend — Página de Pedidos (PedidosPage.tsx)

**Arquivo criado:** `frontend/src/pages/PedidosPage.tsx` — commit `ae4465a`

**Funcionalidades:**
- Layout split-pane: lista `w-full md:w-80` + detalhe `flex-1`
- Mobile: toggle entre lista e detalhe via estado `mobileDetail`
- `OrderCard`: número da mesa, nome do cliente, tempo (`timeAgo`), total, badge de status
- Botão flutuante "Nova Comanda" na lista
- `OrderDetail`: visão completa com itens, totais detalhados (subtotal / taxa / desconto / total) e ações

**Ações em itens:**
- Cancelar item com campo de motivo (inline, sem modal separado)
- Após cancelar: atualiza estado local imediatamente sem recarregar tudo

**AddItemModal (dois modos):**
1. **Do cardápio**: chips de categoria → lista de itens → etapa de quantidade/notas
2. **Manual**: nome, preço, quantidade, notas (para itens fora do cardápio)

**Fluxo de fechamento:**
- `handleClosed`: remove comanda da lista, limpa selecionado, reseta `mobileDetail`
- `handleUpdated`: sincroniza comanda atualizada em `orders[]` e `selected`

---

### Frontend — Página de Cardápio (CardapioPage.tsx)

**Arquivo criado:** `frontend/src/pages/CardapioPage.tsx` — commit `2eaba0f`

**Funcionalidades:**
- Layout split-pane: categorias `w-64` + itens `flex-1`
- Mobile: toggle entre lista de categorias e grid de itens
- RBAC: `canEdit = user.role === 'owner' || user.role === 'manager'`

**Gerenciamento de categorias:**
- Lista lateral com hover revealing edit/delete (opacity-0 → group-hover:opacity-100)
- `CategoryModal`: nome, descrição (opcional), ordem, toggle is_active (edição)
- Soft delete com confirmação inline

**Gerenciamento de itens:**
- Grid: itens ativos + seção "Inativos" separada
- `ItemCard`: header nome+preço, descrição, toggle disponibilidade (verde/vermelho), editar, desativar
- `ItemModal`: seletor de categoria, nome, descrição, preço (suporte a vírgula decimal), ordem, is_available, is_active
- `handleToggleAvailable` / `handleToggleActive`: atualiza estado local instantaneamente (sem reload)
- Componente `Toggle` reutilizável (22 px de altura)

---

### Bug Fix — Logout inesperado ao acessar Cardápio

**Arquivo modificado:** `frontend/src/lib/api.ts` — commit `c886359`

**Causa raiz 1 — URL com barra antes de query string:**

URLs como `/menu/categories/?page_size=100` acionam `redirect_slashes=True` do FastAPI, gerando um redirect 307. O proxy Vite ao seguir o redirect não inclui o header `Authorization` na nova requisição → backend retorna 401 → `clearToken()` → logout automático.

**Causa raiz 2 — tipo de resposta errado em `fetchCategories`:**

`GET /api/v1/menu/categories` retorna `list[CategoryResponse]` diretamente (não paginado). O código usava `request<PaginatedResponse<Category>>` e tentava `.items`, que era `undefined` → TypeError.

**Correções aplicadas:**

| Função | Antes (buggy) | Depois (correto) |
|--------|---------------|------------------|
| `fetchCategories` | `PaginatedResponse<Category>` + `.items` + URL com `/?` | `Category[]` direto, URL `/menu/categories` |
| `fetchMenuItems` | `/menu/items/?page_size=200` | `/menu/items?page_size=200` |
| `createCategory` | `/menu/categories/` | `/menu/categories` |
| `createMenuItem` | `/menu/items/` | `/menu/items` |

**Regra derivada:** endpoints no router do menu usam rotas sem barra (`"/categories"`, `"/items"`). Rotas registradas com `"/"` (tabelas e pedidos) ficam em `/tables/` e `/orders/` — estes estavam corretos.

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
| Dashboard | `/dashboard` | ✅ Visão ao vivo (métricas + comandas) |
| Mesas | `/mesas` | ✅ Completa (CRUD + modais) |
| Pedidos | `/pedidos` | ✅ Completa (split-pane + AddItem + pagamento + finish) |
| Cardápio | `/cardapio` | ✅ Completa (CRUD categorias + itens, RBAC) |
| Equipe | `/equipe` | ✅ Completa (CRUD membros + reset senha, RBAC) |

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
