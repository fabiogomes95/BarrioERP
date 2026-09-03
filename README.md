# BarrioERP

Sistema SaaS de gestão de restaurantes com arquitetura multi-tenancy, onde múltiplos estabelecimentos operam no mesmo sistema com dados completamente isolados.

## Visão Geral

O BarrioERP foi projetado para atender desde pequenos bares até restaurantes com múltiplas filiais, oferecendo controle completo sobre operações do dia-a-dia: mesas, comandas, cardápio, pagamentos, caixa, estoque, reservas e equipe.

## Stack Tecnológica

| Camada | Tecnologia |
|--------|------------|
| Backend | Python 3.14, FastAPI, SQLAlchemy 2.0 (async) |
| Banco de Dados | PostgreSQL 16, Alembic (migrations) |
| Frontend | React 19, TypeScript, TailwindCSS 4, Vite |
| Infraestrutura | Docker, Docker Compose |
| Autenticação | JWT (python-jose), bcrypt |
| Testes | pytest, pytest-asyncio, httpx |

## Funcionalidades

### Módulos do Sistema

- **Autenticação & RBAC** — Login JWT com controle de acesso por papéis (Owner, Manager, Waiter, Cashier)
- **Dashboard** — Visão geral em tempo real do estabelecimento
- **Mesas** — Gestão completa com status (Livre, Ocupada, Reservada, Aguardando Conta)
- **Comandas** — Abertura, adição de itens, fechamento com locking otimista
- **Cardápio** — Categorias e itens com cascade de soft delete
- **Pagamentos** — Múltiplos métodos, pagamentos parciais, verificação financeira
- **Caixa** — Sessões de caixa, abertura/fechamento, movimentações
- **Estoque** — Controle de insumos, vinculação com itens do cardápio
- **Reservas** — Agendamento de mesas com validação de conflitos
- **Equipe** — Gestão de funcionários e permissões
- **Relatórios** — Métricas de vendas e desempenho
- **Auditoria** — Log completo de todas as ações do sistema
- **KDS (Kitchen Display System)** — Tela da cozinha para pedidos
- **Fiado** — Controle de clientes e pagamentos pendentes
- **Onboarding** — Fluxo de setup inicial para novos restaurantes

### Destaques Técnicos

- **Multi-tenancy** — Isolamento total de dados por empresa via JWT
- **Arquitetura em camadas** — Schema → Repository → Service → Endpoint
- **Async/Await** — Backend assíncrono para alta performance
- **Soft Delete** — Preservação de histórico para auditoria
- **Optimistic Locking** — Controle de concorrência via campo `version`
- **Aritmética Financeira** — `Decimal(12,2)` para precisão em valores monetários
- **Snapshot de Preço** — Itens preservam preço e nome no momento do pedido
- **RBAC** — Controle de acesso baseado em papéis por rota

## Pré-requisitos

- Python 3.14+
- Node.js 18+
- Docker e Docker Compose
- PostgreSQL 16 (ou via Docker)

## Instalação

### 1. Clonar o repositório

```bash
git clone https://github.com/seu-usuario/BarrioERP.git
cd BarrioERP
```

### 2. Configurar variáveis de ambiente

```bash
cp backend/.env.example backend/.env
# Edite o .env com suas configurações
```

### 3. Iniciar o banco de dados

```bash
make db-up
```

### 4. Instalar dependências do backend

```bash
make install
```

### 5. Aplicar migrations

```bash
make migrate-up
```

### 6. Iniciar o backend

```bash
make dev
```

### 7. Iniciar o frontend (em outro terminal)

```bash
cd frontend
npm install
npm run dev
```

Acesse:
- Frontend: `http://localhost:5173`
- API: `http://localhost:8000`
- Swagger UI: `http://localhost:8000/docs`

## Comandos Úteis

| Comando | Descrição |
|---------|-----------|
| `make db-up` | Sobe o PostgreSQL no Docker |
| `make db-down` | Para e remove os containers |
| `make db-shell` | Abre psql interativo |
| `make migrate-gen` | Gera nova migration |
| `make migrate-up` | Aplica migrations pendentes |
| `make migrate-down` | Reverte última migration |
| `make dev` | Inicia backend com hot-reload |
| `make validate-models` | Verifica models e tabelas |

## Estrutura do Projeto

```
BarrioERP/
├── backend/
│   ├── app/
│   │   ├── api/v1/endpoints/   # Endpoints HTTP
│   │   ├── core/               # Configurações e segurança
│   │   ├── database/           # Sessão e base do banco
│   │   ├── models/             # Models SQLAlchemy
│   │   ├── repositories/       # Acesso ao banco
│   │   ├── schemas/            # Contratos Pydantic
│   │   └── services/           # Lógica de negócio
│   └── alembic/                # Migrations
├── frontend/
│   ├── src/
│   │   ├── components/         # Componentes React
│   │   ├── pages/              # Páginas da aplicação
│   │   └── lib/                # Utilitários e API
│   └── ...
├── docker-compose.yml
├── Makefile
└── ARCHITECTURE.md
```

## Licença

Projeto privado.
