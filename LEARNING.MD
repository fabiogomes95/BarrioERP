# LEARNING.md

# BarrioERP — Diário de aprendizado

## Dia 1 - 20/04/2026 — Fundação do backend

Hoje comecei oficialmente a estrutura backend do BarrioERP.

A ideia do projeto é criar um sistema SaaS para gerenciamento de bares/restaurantes, começando pelo backend profissional desde o início ao invés de fazer tudo improvisado.

Hoje focamos totalmente no backend + banco.

---

# Tecnologias escolhidas

## FastAPI

FastAPI é basicamente quem recebe as requisições e devolve respostas.

Exemplo:
- abrir mesa
- criar pedido
- fazer login

Tudo passa pelo FastAPI.

---

## PostgreSQL

Escolhi PostgreSQL ao invés de SQLite porque o sistema terá múltiplos garçons mexendo ao mesmo tempo nas comandas. (Irei migrar o HMPCF System para os PostgreSQL no futuro tbm)

SQLite seria simples no começo mas provavelmente viraria problema depois.

---

## Docker

Ao invés de instalar PostgreSQL diretamente no Linux ou nas maquinas que o sistema vai rodar, ele vai rodar dentro de um container separado.

Peguei um probleminha besta, mas que foi bom para saber logo no começo:

Dentro do Docker:
localhost = o próprio container

Então para o backend falar com o PostgreSQL no docker-compose, o host correto era:

```env
POSTGRES_HOST=db
``` 

## Alembic

Utilizando o alembic 

## ORM (SQLAlchemy)

Ainda estou aprendendo ORM.

Mas entendi que ele funciona como um tradutor entre Python e SQL.

Exemplo:

```python
user = await session.get(User, user_id)
```

vira SQL automaticamente no banco.

Também comecei a entender que:

- models = tabelas
- colunas = atributos da classe
- relationship = ligação entre tabelas

---

## Alembic / migrations

Essa foi uma das coisas mais importantes que aprendi hoje.

Migration é basicamente um histórico de mudanças do banco.

Ao invés de:

- apagar banco
- recriar tudo

o Alembic gera scripts que alteram apenas o necessário sem perder os dados.

Tipo uma “reforma” no banco.

Fluxo que aprendi:

1. mudar model
2. gerar migration
3. aplicar migration
4. banco atualizado

Comandos:

```bash
alembic revision --autogenerate -m "mensagem"
alembic upgrade head
```

---

## Estrutura criada

Backend atual:

```text
backend/
  app/
    api/
    core/
    database/
    models/
    repositories/
    services/
    schemas/
```

Comecei a entender melhor o papel de cada camada:

### models

Estrutura do banco.

---

### repositories

Consultas ao banco.

---

### services

Regras de negócio.

---

### endpoints

Rotas HTTP/FastAPI.

---

## Conceitos importantes aprendidos

### UUID

As tabelas usam UUID ao invés de ID incremental.

Achei interessante porque:

- evita enumeração simples
- melhor para SaaS
- mais seguro externamente

---

### Optimistic Locking

Isso protege contra dois garçons alterando a mesma comanda ao mesmo tempo.

Cada registro possui uma coluna `version`.

Achei MUITO interessante porque nunca tinha pensado nesse problema antes.

---

### Soft Delete

Ao invés de apagar registros definitivamente:

- adiciona `deleted_at`
- o registro fica “desativado”

Bom para auditoria e histórico.

---

## Problemas que corrigimos

### Problema do localhost no Docker

Backend não conseguia acessar PostgreSQL porque localhost dentro do container apontava para ele mesmo.

Corrigido usando:

```env
POSTGRES_HOST=db
```

---

### Problema do relacionamento de mesas

Uma mesa precisava:

- ter todas as comandas
- mas também visualizar apenas comandas abertas

Foi separado em:

- `orders`
- `open_orders`

---

## Estado atual do projeto

✅ PostgreSQL funcionando no Docker  
✅ FastAPI funcionando  
✅ Swagger funcionando  
✅ ORM validado  
✅ 11 tabelas criadas  
✅ migrations funcionando  
✅ arquitetura organizada  

Ainda NÃO existe:

- autenticação
- endpoints reais
- lógica de negócio

Mas a fundação está pronta.

---

## Impressão geral

Hoje comecei a entender que backend profissional é muito mais sobre:

- organização
- separação de responsabilidades
- evolução segura
- arquitetura

do que simplesmente “fazer funcionar”.

Também percebi que muita coisa que parecia exagero faz sentido quando penso que vários estabelecimentos vão usar o sistema ao mesmo tempo.



## Dia 2 - 21/04/2026