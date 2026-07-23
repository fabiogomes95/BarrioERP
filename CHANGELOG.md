# BarrioERP — Changelog de Desenvolvimento

> Registro cronológico de tudo que foi implementado, decisão por decisão.
> Atualizar a cada sessão de trabalho.

---

## Próximos passos

- Avaliar se `kitchen` precisa de alguma visão própria simplificada (hoje usa as
  mesmas restrições do `waiter`).
- **Sem "esqueci minha senha" no login** — só um manager/owner consegue resetar a
  senha de outro usuário (tela Equipe). Se sobrar um único owner e ele esquecer a
  senha, não tem saída pela interface.
- **`ARCHITECTURE.md` desatualizado** desde 2026-06-10 — cash, reports e audit já
  existem no código mas não estão documentados lá (só o changelog está em dia).
- Gaps de produto ainda não avaliados: controle de estoque/insumos, reservas de
  mesa com data/hora, relatórios por período (hoje só por dia), emissão fiscal
  (NFC-e), gestão de múltiplos estabelecimentos pela UI.

---

## [v0.9.0] — Identidade visual oficial + modo claro/escuro

Rebrand completo do frontend a partir do cardápio físico do bar
(`Cardápio Recanto da Barra`) — ícone oficial, paleta de cores extraída do
material impresso, e o app ganhou modo claro (novo) além do escuro que já
existia.

### Ícone oficial

**Arquivos:** `frontend/public/icon-recanto*.png`, `favicon.png`,
`assets/icon-recanto.png`, `assets/icon-recanto.ico`

O ícone provisório (palmeira simplificada) foi substituído pelo logo real —
recortado do arquivo `icon-recanto.jpeg` do cardápio (círculo com duas
palmeiras, gaivotas e ondas), com fundo transformado de branco em
transparente (o JPEG original não suporta alpha). Gerado em 512×512, 192×192
e 64×64 a partir do mesmo recorte, todos em alta qualidade.

### Paleta de cores — extraída do cardápio físico

Cores exatas obtidas por amostragem de pixel das artes reais (`export/
cardapio-pagina-*.png`, `cardapio-whatsapp*.png`):

| Papel | Hex | Onde aparece no cardápio |
|---|---|---|
| Fundo | `#FCF6ED` | papel |
| Título/cabeçalhos | `#743200` | "RECANTO", nomes de seção |
| Categoria/destaque | `#8E3D00` | "LONG NECK", subtítulo |
| Texto principal | `#231107` | nomes dos itens |
| Preço | `#600000` | valores em R$ |
| Acento dourado | `#C28F62` | círculo da logo |
| Creme claro | `#FFE3BC` | anel externo da logo |

### Arquitetura do tema — sem editar cada página

**Arquivo:** `frontend/src/index.css`

Em vez de editar manualmente as ~15 páginas do app, a troca de identidade
inteira foi feita redefinindo a paleta no Tailwind via `@theme`:

- As escalas `amber-*` (acento) e `stone-*` (neutros/texto) do Tailwind foram
  **remapeadas** pros tons do cardápio — toda classe já existente no código
  (`bg-amber-500`, `text-stone-400`, `border-stone-800/60`, etc.) herdou a
  nova cara automaticamente, sem tocar em nenhuma página
- Tailwind v4 gera as classes utilitárias referenciando `var(--color-*)` em
  vez de valores fixos — por isso um bloco `:root[data-theme="dark"]` redefine
  as mesmas variáveis e repinta tudo de uma vez
- **Detalhe não-óbvio:** a escala `stone` é invertida entre os temas —
  `stone-100` é o tom mais ESCURO no claro (era o texto de maior destaque,
  quase-branco no escuro; no claro o de maior destaque é quase-preto) e
  vice-versa. Comentado no `index.css` pra não confundir no futuro
- Cores semânticas (vermelho/verde/azul/laranja de erro, sucesso, pendência,
  info) foram mantidas como o Tailwind padrão — não fazem parte da
  identidade visual da marca, só precisam continuar legíveis
- Os ~130 fundos com hex fixo (`style={{background: '#0d0b08'}}` etc.,
  espalhados em ~15 arquivos) viraram `var(--color-app-bg)` /
  `var(--color-app-surface)` / `var(--color-app-surface-2)`

### Modo claro/escuro

**Arquivos:** `frontend/src/lib/theme.ts` (novo), `components/ui.tsx`
(`ThemeToggle`), `components/Layout.tsx`, `pages/LoginPage.tsx`

- Sem escolha salva, segue `prefers-color-scheme` do sistema automaticamente
- Botão sol/lua (`ThemeToggle`) grava a escolha em `localStorage` e aplica via
  atributo `data-theme` na `<html>` — persiste entre sessões, sobrepõe o tema
  do sistema
- `initTheme()` roda em `main.tsx` antes do primeiro render, pra não piscar
  o tema errado ao carregar a página
- Toggle disponível na barra superior (autenticado) e no canto do Login

### Decisão: recibo e relatório impresso continuam com cor fixa

`lib/receiptImage.ts` (imagem do recibo pro WhatsApp) e `lib/reportExport.ts`
(relatório A4 em PDF) **não** seguem o tema claro/escuro do app — um recibo/
relatório impresso não tem "modo escuro", então usam cores fixas. O recibo
foi atualizado pra usar a paleta nova (papel `#FCF6ED`, tinta `#231107`); o
relatório A4 manteve tons neutros de documento (é um relatório interno, não
uma peça de marca).

---

## [v0.8.0] — Impressão remota (celular → impressora do bar)

**Arquivos:** `backend/app/api/v1/endpoints/notifications.py`,
`frontend/src/lib/notifications.ts`, `frontend/src/lib/api.ts`,
`frontend/src/components/Layout.tsx`, `frontend/src/components/OrderDetailView.tsx`

A impressora térmica está ligada por cabo USB a um único PC — o celular do
garçom não tem como imprimir localmente. Reaproveitando o canal SSE da
notificação de "conta pedida" (v0.7.0):

- **`POST /orders` não existe pra isso** — é só `POST /notifications/print`
  com `{order_id, print_type}`, que publica um evento `print.request` no
  mesmo barramento (Postgres LISTEN/NOTIFY)
- **"Impressora do bar é este PC"** — toggle novo na barra lateral (visível pra
  owner/manager/cashier), salvo em `localStorage` por dispositivo — quem estiver
  fisicamente no PC com a impressora liga uma vez só
- Quando o toggle está ligado, o dispositivo escuta `print.request` no mesmo
  listener SSE já aberto, busca a comanda fresca (`fetchOrder`) e chama
  `printComanda()` — o mesmo fluxo de sempre (popup + `window.print()`)
- O botão "Imprimir" na comanda passa a ser inteligente: neste PC (toggle
  ligado) imprime local como sempre; em qualquer outro dispositivo, manda a
  impressão pro PC e mostra um ✓ de confirmação por 2s

**Limitação aceita:** só funciona enquanto o navegador estiver aberto no PC da
impressora (o listener é JS rodando na aba, não um serviço de sistema). Se o
navegador for fechado nesse PC, os pedidos de impressão remota não chegam —
mas o sistema continua funcionando normalmente pra tudo o mais.

---

## [v0.7.0] — Notificação em tempo real ao solicitar a conta

**Arquivos:** `backend/app/core/events.py` (novo), `backend/app/api/v1/endpoints/notifications.py`
(novo), `backend/app/services/order_service.py`, `backend/app/api/deps.py`,
`frontend/src/lib/notifications.ts` (novo), `frontend/src/components/Layout.tsx`

`PATCH /orders/{id}/request-bill` substitui o antigo fluxo (que só mudava o
status da Mesa). Motivo da mudança: comandas de balcão (sem mesa) também
precisam pedir a conta, e o card "Contas pedidas" do Dashboard já lia
`order.status` — nunca recebia esse valor porque só a mesa mudava antes. Agora
a Order muda de status e, se tiver mesa vinculada, o status dela é espelhado
junto (pro card colorir certo em Mesas).

Eventos em tempo real via Server-Sent Events, usando **Postgres LISTEN/NOTIFY**
como barramento — necessário porque o backend roda em dois processos uvicorn
separados (HTTP:8000 e HTTPS:443, ver v0.6.0), que não compartilham memória;
um pub/sub em memória num processo não seria visto pelo outro.

Frontend: toast com som (dois bipes via Web Audio API, sem depender de arquivo
de áudio) quando alguém solicita a conta, visível só pra quem lida com
pagamento (`owner`/`manager`/`cashier` — garçom e cozinha não recebem). Botão
"Ver" no toast abre a comanda direto (`/comanda/:orderId`).

---

## [v0.6.0] — Frontend em produção, PWA instalável e acesso remoto via Tailscale

Sessão de infraestrutura: parou de rodar o frontend como servidor de desenvolvimento,
corrigiu ícones/manifest quebrados no build de produção, resolveu o problema de IP
mutável do PC e habilitou acesso remoto gratuito ao sistema via Tailscale.

### Backend — Correção no fallback de arquivos estáticos

**Arquivo:** `app/main.py`

O catch-all do SPA (`serve_spa`) devolvia `index.html` pra **qualquer** rota não
reconhecida — inclusive `favicon.png`, `icon-recanto.png`, `favicon.svg`, `icons.svg`,
que existem como arquivos soltos em `frontend/public/` (fora de `assets/`, o único
diretório montado como estático). Resultado: ícones quebrados assim que o build de
produção passou a ser servido pelo FastAPI em vez do Vite dev server.

**Fix:** `serve_spa` agora verifica se `full_path` corresponde a um arquivo real
dentro de `dist/` e serve ele diretamente; só cai no `index.html` se não existir
(roteamento client-side do React Router). Guarda contra path traversal:
`candidate.resolve()` precisa estar dentro de `_FRONTEND.resolve()` — testado com
`%2e%2e` e `..%2f` codificados, ambos bloqueados corretamente.

### Frontend — Fix: parcela errada ao dividir conta por pessoa

**Arquivo:** `components/OrderDetailView.tsx`

O botão "Receber" de cada parcela trocava `activeSlot` direto, sem passar pela
`openSlot()` — que é quem reseta valor/troco/forma de pagamento pra aquela parcela
específica. Bug real: abrir a parcela da Pessoa 1, fechar, abrir a da Pessoa 2 —
o campo "Valor" ficava com o valor da Pessoa 1. Corrigido conectando o clique à
`openSlot(i)`.

### Frontend — PWA instalável (ícone + tela cheia na tela inicial)

**Arquivos:** `public/manifest.webmanifest` (novo), `index.html`,
`public/icon-recanto-512.png` (novo, copiado de `assets/icon-recanto.png` — a
versão 512×512 já existia na raiz do projeto, só a pública em `frontend/public/`
estava em 192×192)

- Manifest com `display: standalone`, ícones 192 e 512, `name`/`short_name`
  "BarrioERP", `theme_color`/`background_color` `#0d0b08`
- `apple-touch-icon` (iOS ignora o manifest, usa essa tag), `apple-mobile-web-app-capable`
  e `mobile-web-app-capable` (abre em tela cheia, sem barra do navegador)
- Testado: "Adicionar à tela inicial" no celular já usa o ícone certo e abre como
  app, não como atalho de aba

### Infraestrutura — Build de produção substitui o Vite dev server

- `frontend/dist/` gerado via `npm run build` (estava parado desde 2026-06-27
  enquanto o serviço rodava `npm run dev` — dois processos fazendo o trabalho de um)
- Serviço Windows `BarrioERP-Frontend` (NSSM, rodava `npm run dev` na porta 5173)
  **removido** — o próprio `BarrioERP-Backend` agora serve API + frontend juntos
  na porta 8000
- Único bloqueio de build corrigido: variável `openSlot` não usada em
  `OrderDetailView.tsx` (era o bug de parcela acima, não só um lint)

### Infraestrutura — IP fixo do PC na rede do bar

Problema: o IP do PC mudava (DHCP), obrigando reconfigurar o acesso toda hora.
Reserva de IP no roteador não foi possível (rede com acesso admin bloqueado).
mDNS (`GOMES-PC.local`) não funcionou (provável isolamento de cliente na rede).

**Solução:** IP manual (`192.168.1.250`) configurado só no perfil da rede Wi-Fi
do bar (`TP-Link_A6DE`), via Configurações do Windows — escopo por rede/SSID, não
afeta o uso do mesmo notebook em outras redes (escola, casa).

### Infraestrutura — Acesso remoto via Tailscale

O notebook que roda o BarrioERP não fica fisicamente fixo no bar (uso pessoal
fora do horário de funcionamento), então IP fixo sozinho não bastava pra acesso
de fora da rede do bar. Cogitado subir tudo pra um servidor na nuvem, mas
descartado por custo/complexidade desnecessários pro problema real.

**Tailscale** instalado no PC (`gomes-pc`, IP Tailscale `100.109.236.99`) e no
celular — rede privada (WireGuard) que dá um endereço fixo alcançável de
qualquer rede, sem mexer no roteador. Testado com sucesso em rede móvel (dados).
Regra de firewall `BarrioERP Backend 8000` já cobria os perfis Privado e Público,
então não precisou de ajuste extra.

### Infraestrutura — HTTPS via certificado Tailscale (resolve o botão do WhatsApp)

Sem domínio público, um certificado confiável só é possível pro hostname que o
Tailscale já verifica e resolve: **HTTPS Certificates** ativado no admin do
Tailscale (`login.tailscale.com/admin/dns`), tailnet renomeado pra
`cod-aldebaran.ts.net`, certificado emitido via `tailscale cert` pro hostname
`gomes-pc.cod-aldebaran.ts.net`.

**Arquivos novos:**
- `backend/certs/` (gitignored — só `.crt`/`.key`/`.log` ficam de fora, o script
  abaixo é versionado)
- `backend/certs/renovar-cert.ps1` — renova o certificado e reinicia o serviço
  HTTPS; agendado via Task Scheduler (`BarrioERP-Renovar-Cert`, diário às 4h,
  idempotente — só renova de fato perto do vencimento)

**Novo serviço Windows** `BarrioERP-Backend-TLS` — segunda instância do mesmo
`uvicorn app.main:app`, na porta 443 com `--ssl-certfile`/`--ssl-keyfile`. Roda
em paralelo ao `BarrioERP-Backend` (porta 8000, HTTP puro) — quem tem Tailscale
ativo usa `https://gomes-pc.cod-aldebaran.ts.net` (contexto seguro, Web Share
API funciona); acesso local pela rede do bar sem Tailscale continua disponível
em HTTP puro como fallback. `instalar_servicos.ps1` atualizado pra instalar os
dois de uma vez numa reinstalação futura (e corrigido: apontava pra
`C:\Users\Fabinho\...`, caminho antigo de antes da migração pra `D:`).

**Resultado:** botão de compartilhar recibo por WhatsApp agora dispara o menu
nativo de compartilhar corretamente (testado no PC e no celular). Não abre o
WhatsApp diretamente — abre o menu do sistema com a imagem já anexada, e o
usuário escolhe o app. Isso é o comportamento correto e esperado da Web Share
API com arquivos (`navigator.share({ files })`): nenhum site consegue pular
essa escolha do usuário por questão de segurança/privacidade da plataforma —
não é uma limitação do BarrioERP.

---

## [v0.5.0] — RBAC por cargo, Auditoria, correções de Fiado/Caixa e polish geral

Sessão longa cobrindo: controle de acesso por cargo (garçom não vê dinheiro),
tela de Auditoria nova, correções de contabilidade (fiado inflando o faturamento),
identidade visual própria, exportação de relatórios, recibo por WhatsApp,
divisão de conta por item e vários ajustes de mobile.

### Backend — RBAC (controle de acesso por cargo)

**Arquivos:** `app/api/deps.py` (helper `require_roles`), `orders.py`, `payments.py`,
`cash.py`, `reports.py`, `audit.py`, `menu.py`

Garçom (`waiter`) e cozinha (`kitchen`) não devem ver dinheiro nem faturamento —
só quem atende caixa. Endpoints agora bloqueados (HTTP 403) pra esses cargos:

| Ação | Endpoint | Cargos permitidos |
|---|---|---|
| Desconto / taxa de serviço | `PATCH /orders/{id}/discount`, `/service-fee` | owner, manager, cashier |
| Apagar comanda | `DELETE /orders/{id}` | owner, manager |
| Fechar em fiado / finalizar | `PATCH /orders/{id}/close`, `/finish` | owner, manager, cashier |
| Registrar pagamento | `POST /payments` | owner, manager, cashier |
| Todo o módulo Caixa | `/cash/*` | owner, manager, cashier |
| Relatório do dia / histórico | `GET /reports/daily`, `/history` | owner, manager, cashier |
| Auditoria | `GET /audit` | owner, manager |
| Editar cardápio (criar/editar/apagar) | `/menu/*` (mutações) | owner, manager |

Reads não-sensíveis (listar cardápio, itens, fiado) continuam liberados pra todos.

### Frontend — RBAC

**Arquivos:** `Layout.tsx`, `App.tsx`, `OrderDetailView.tsx`, `DashboardPage.tsx`, `PedidosPage.tsx`

- Menu lateral filtra Caixa/Auditoria/Administração por `roles` no item de nav
- `RequireRole` no `App.tsx` bloqueia acesso direto por URL (redireciona pro Dashboard)
- Dentro da comanda: garçom não vê Total/Subtotal/Taxa/Desconto nem os botões
  Receber/Desconto/Taxa/Dividir conta/Fiado/Apagar — só itens, `+ Item`, `Cozinha`
  e `Solicitar conta` (preço de linha do item continua visível, só o agregado some)
- Dashboard e Pedidos escondem os valores em R$ dos cards pra garçom/cozinha
- Testado ao vivo logando como um garçom real (Felipe) e conferindo cada tela

### Backend — Correções de contabilidade e auditoria

**Arquivos:** `order_service.py`, `payment_service.py`, `order_repository.py`, `schemas/order.py`

- **Fix:** comanda fechada como fiado (pagamento parcial) estava sendo somada
  como faturamento do dia igual a uma venda quitada — corrigido pra só contar
  quando `total_pago >= total`
- **Fix:** `PaymentService.finish()` (fechar com pagamento total) nunca tinha
  log de auditoria — só o fechamento em fiado tinha
- Log de auditoria adicionado em: registrar pagamento, finalizar comanda,
  aplicar desconto, alternar taxa de serviço, fechar em fiado
- Nome do cliente/mesa agora incluído em **todos** os eventos de auditoria
  (antes faltava em fechar/reabrir/cancelar/desconto/taxa)
- Novo campo `is_fiado` no `OrderResponse`, calculado em `list_history()`
- **Fix:** usuário criado pela tela de Equipe ficava sem `establishment_id`
  vinculado e não conseguia operar o sistema — agora herda o do usuário que criou

### Frontend — Tela de Auditoria (nova)

**Arquivo:** `pages/AuditoriaPage.tsx`

Histórico em tempo real (auto-refresh 20s) de tudo que acontece nas comandas:
item adicionado/cancelado, quantidade alterada, pagamento, abertura/fechamento/
finalização/reabertura, com filtros por tipo de ação, nome de quem fez e de quem
se refere a ação, link direto pra comanda. Acessível pelo menu lateral e como
aba dentro de Administração.

### Frontend — Divisão de conta por item

**Arquivo:** `components/OrderDetailView.tsx` (`SplitModal`)

Modal de dividir conta ganhou duas abas: **Igualmente** (já existia) e **Por item**
— toca no número da pessoa em cada item da comanda pra atribuir; o valor de cada
um é calculado proporcionalmente (incluindo taxa/desconto), exato em centavos.

### Frontend — Exportar relatório e recibo por WhatsApp

**Arquivos:** `lib/reportExport.ts`, `lib/receiptImage.ts`, `pages/CaixaPage.tsx`,
`components/OrderDetailView.tsx`

- Caixa: botões CSV e PDF (impressão em A4) do relatório do dia
- Comanda: recibo gerado como **imagem** (canvas, com a logo do bar) pra
  compartilhar pelo WhatsApp — usa Web Share API no celular, baixa a imagem
  no desktop

### Frontend — Administração reorganizada

**Arquivos:** `pages/AdminPage.tsx`, `pages/EquipePage.tsx`, `components/ui.tsx`

- Equipe e Auditoria viraram abas dentro de Administração (`AdminTabs`)
- "Trocar minha senha" adicionado (endpoint já existia no backend sem uso)

### Frontend — Fiado

**Arquivo:** `pages/FiadoPage.tsx`

- Busca por nome do cliente
- Card de resumo no topo: total em fiado, nº de clientes, nº de comandas
- Botão "Ver itens" — mostra os itens da comanda sem precisar reabrir
- Cards de cada cliente vêm colapsados por padrão (evita rolagem enorme)
- Grid lado a lado quando o cliente tem mais de uma comanda em fiado

### Frontend — Cardápio / adicionar itens

**Arquivo:** `components/OrderDetailView.tsx`

- Complemento do item (sabor/corte) deixou de ser obrigatório — se não escolher,
  usa só o nome base; se escolher, concatena (ex: "Churrasco - carne")
- Modal "Adicionar item" não fecha mais sozinho após adicionar — dá pra lançar
  vários itens seguidos sem reabrir o modal a cada um

### Frontend — Mobile

- Modal "Adicionar item" ocupa a tela inteira no celular (era um cartão pequeno
  que ficava atrás do teclado virtual) — lista de itens agora preenche o espaço
  disponível em vez de cortar na metade
- Quantidade com stepper (`QtyStepper` em `ui.tsx`) — toca +/- em vez de apagar
  e digitar
- Nome do bar no topo vira só o ícone no mobile (evitava sobrepor o menu/atalhos)
- `ModalOverlay` (todos os modais) ganhou altura máxima + rolagem interna, pra
  não ficar cortado atrás do teclado

### Identidade visual

**Arquivos:** `assets/`, `frontend/public/`, `components/Layout.tsx`

- Ícone/logo próprio (palmeira, paleta bege/marrom do Recanto) — favicon, atalho
  da área de trabalho, cabeçalho do app
- Título da aba trocado de "frontend" pra "BarrioERP"

### Infraestrutura

- `instalar_servicos.ps1` — script pra registrar o backend/frontend como serviço
  do Windows via NSSM, iniciando sozinho no boot (falta rodar como Administrador)

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

### Produção (como roda hoje no PC do bar)

Serviço Windows `BarrioERP-Backend` (NSSM) sobe `uvicorn app.main:app` na porta
8000, que serve a API **e** o frontend (build estático de `frontend/dist/`)
juntos. Não existe mais serviço separado de frontend.

```bash
# Gerar o build de produção sempre que mexer no frontend:
cd frontend
npm run build
```

Acessar: `http://192.168.1.250:8000` (IP fixo do PC na rede do bar) ou pelo
endereço Tailscale (`gomes-pc`) de qualquer rede.

### Desenvolvimento local (hot-reload)

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
