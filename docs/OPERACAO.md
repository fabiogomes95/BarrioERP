# BarrioERP — Operação no Recanto da Barra

Guia do dia a dia: como o sistema está montado neste PC, o que cada parte faz
e como mexer quando precisar. (Instalação e desenvolvimento ficam no
[README.md](../README.md).)

---

## 1. Como está montado

Tudo roda **neste PC** (`gomes-pc`), como serviços do Windows que iniciam
sozinhos quando o PC liga:

| Serviço                  | O que é                                   | Porta local |
|--------------------------|-------------------------------------------|-------------|
| `BarrioERP-Backend`      | O sistema (API + telas do Barrio)         | 8000        |
| `BarrioERP-Menu-Publico` | O cardápio online dos clientes            | 8090        |
| PostgreSQL 16            | Banco de dados                            | 5432        |

O **Tailscale** cuida do acesso seguro (HTTPS) — sem certificado pra renovar
à mão:

- `tailscale serve` → o **Barrio** em https://gomes-pc.cod-aldebaran.ts.net
  (só aparelhos da sua rede Tailscale).
- `tailscale funnel` → **só o cardápio**, aberto pra internet, na porta 8443.
  **Nunca** faça funnel da porta 443: ela é o Barrio inteiro.

> O antigo serviço `BarrioERP-Backend-TLS` (uvicorn com certificado), a tarefa
> `BarrioERP-Renovar-Cert` e a pasta `backend/certs/` foram **removidos** em
> 08/11/2026 — o Tailscale Serve cuida do HTTPS e renova o certificado sozinho.

---

## 2. Endereços

| Para quê                         | Endereço                                                  |
|----------------------------------|-----------------------------------------------------------|
| **Barrio** (equipe)              | https://gomes-pc.cod-aldebaran.ts.net                     |
| Barrio pela rede local (reserva) | http://192.168.1.250:8000                                 |
| **Cardápio pros clientes**       | **https://recantodabarra.github.io** ← este é o que divulga |
| Cardápio direto do PC (reserva)  | https://gomes-pc.cod-aldebaran.ts.net:8443/cardapio/matriz |

---

## 3. Cardápio online

### Visual
Segue o cardápio impresso oficial (papel pêssego, títulos com versalete,
linha pontilhada até o preço com sol/barco/gaivota, preços em vinho).
Ordem: **Pizzas → Petiscos → Cervejas → Destilados → Refrigerantes**.
Cervejas agrupadas em Long Neck / 600ml / Litrão (pelo fim do nome no cadastro).
Arquivo da página: `public_menu_static/index.html`.

### Por que existem dois endereços
A página fica no **GitHub Pages** (organização `recantodabarra`, repositório
`recantodabarra.github.io`), que está **sempre no ar**:

- **PC ligado:** o cardápio vem ao vivo do Barrio e o pedido cai no sistema.
- **PC desligado:** a página usa a última cópia publicada do cardápio e o
  pedido vai **só pelo WhatsApp** (o botão vira "Continuar no WhatsApp").

### Publicação automática
A tarefa agendada **`BarrioERP-Publicar-Cardapio`** roda a cada 10 min
(escondida) e só publica se algo mudou (preço, item novo/esgotado, a página).
Mudou preço e quer publicar **na hora**? Dois cliques em
`deploy/windows/publicar_cardapio.vbs` (pasta do BarrioERP). Log: `logs/publicar_cardapio.log`.
Cópia local do site: `D:\Users\Fabinho\Documents\recanto-cardapio-site`
(commits saem como "Recanto da Barra").

### Horário de pedidos
Hoje: **sexta, sábado e domingo a partir das 18h**, sem hora fixa de fechar
(o dia vale até 5h da madrugada; fora do horário a casa avisa o cliente).
Fora do horário a página mostra "Fechado agora · abrimos sexta às 18h" e
bloqueia o envio (o servidor também recusa). Rodapé mostra
"Pedidos: Sex a Dom a partir das 18h".

Mudar: linha `PUBLIC_MENU_HOURS` no `backend\.env`, ex.:
```
PUBLIC_MENU_HOURS={"qui":"18:00-","sex":"18:00-","sab":"18:00-","dom":"18:00-"}
```
`"18:00-"` = a partir das 18h; `"17:00-23:00"` = horário fechado;
`"11:00-14:00,18:00-"` = almoço e noite. Depois reinicie `BarrioERP-Menu-Publico`.

---

## 4. Pedidos online (cardápio → Barrio)

**Cliente:** monta o pedido (inclui **pizza meio a meio** — cobra a metade
mais cara — e escolhe o **sabor do churrasco**), preenche nome, WhatsApp e
**entrega ou retirada** (entrega só na Praia de Barra do Rio). Opcionais:
**onde entregar** ("barraca 3, casa azul perto da igreja") e **como vai pagar**
(Dinheiro — com "troco para quanto?" —, Pix, Crédito ou Débito). Tudo isso vai
na mensagem do WhatsApp, no card do pedido e na nota da comanda. **Pix:** a
casa manda a chave pelo WhatsApp (o sistema não guarda nem gera chave).
Ao tocar em **Enviar pedido**: o pedido entra no Barrio **e** o WhatsApp do
bar abre com a mensagem pronta (ele envia se quiser).

**No Barrio:**
1. Toca bipe e aparece "Pedido online #N" em qualquer tela (só pra dono,
   gerente e caixa — precisa ter o Barrio aberto em algum aparelho).
2. Tela **Pedidos** → painel "Pedidos online aguardando" → **Aceitar** ou
   **Recusar**. Nada entra na cozinha/caixa sem aceite.
3. Aceitou: vira comanda (Delivery/Retirada, **sem taxa de 10%**), você
   **continua na tela de Pedidos**, e o **ticket da cozinha sai sozinho**.
4. Opcional: faixa verde **"Avisar no WhatsApp"** abre o WhatsApp Desktop
   direto na conversa do cliente com uma mensagem pronta.

**Segurança:** o preço é recalculado no servidor (o navegador não decide
valor), limite de 4 pedidos/min (20/hora) **por cliente** e no máximo 30
esperando aceite.

**Relatório:** tela **Caixa**, no fim — recebidos, aceitos, recusados, valor,
ticket médio, entrega x retirada e mais pedidos (segue dia/período/turno).

---

## 5. Impressão (direta na térmica)

A **POS-80C** está ligada por USB neste PC, e o **servidor imprime direto
nela** — sem janela do Chrome, sem pop-up, de qualquer aparelho:

- Botão de imprimir a **comanda** (recibo/conta).
- **Imprimir cozinha** (itens marcados) e **"adicionar e imprimir"**.
- **Aceite de pedido online** → ticket da cozinha automático
  (só itens de cozinha; pedido só de bebida não imprime).

Os impressos saem **sem acento** (térmica genérica imprime lixo no lugar de
ç/ã) e com corte automático do papel.

Se a impressão direta falhar (impressora desligada, sem papel), cai na
reserva antiga: o PC marcado como **"impressora do bar"** (opção no menu)
imprime pelo navegador.

Configuração no `backend\.env`:
```
THERMAL_PRINTER=POS-80C           # nome da impressora no Windows
AUTO_PRINT_ONLINE_ORDERS=true     # false = não imprime sozinho ao aceitar (ex: testes)
```
Reinicie `BarrioERP-Backend` depois de mudar.

---

## 6. Comandas — novidades

- **Tema** na mesma linha do cardápio ("Areia & Terracota": papel pêssego,
  terracota nos botões, títulos em Cormorant, texto em Poppins), claro e escuro.
  Tudo em `frontend/src/index.css` — trocar a paleta muda o app inteiro.

- **Receber/fechar conta sem precisar atualizar a página.** Causa corrigida:
  o servidor respondia "OK" antes de gravar no banco (FastAPI ≥ 0.118); agora
  grava antes (`DBSession` com `scope="function"` em `backend/app/api/deps.py`).
- **Selecionar várias comandas** (tela Pedidos): **segure** uma comanda (ou
  botão direito no PC) → marque outras →
  - **Mesclar**: escolhe em qual comanda fica tudo; as outras ficam com a nota
    "Itens movidos para a comanda X" e as mesas liberadas. Comanda com
    pagamento registrado não pode ser mesclada (estorne antes).
  - **Apagar**: só dono/gerente.
- **Meio a meio e Churrasco com sabor** vão pra cozinha (KDS e impressão) e
  baixam estoque (meia receita de cada sabor) — quando houver receita cadastrada.

---

## 7. WhatsApp Business (configurar no celular)

Tudo em **⋮ → Ferramentas comerciais** (iPhone: Configurações → Ferramentas comerciais):

1. **Mensagem de saudação** (vai sozinha no 1º contato ou após 14 dias):
   > Oi! Bem-vindo(a) ao Recanto da Barra 🌴
   > Faça seu pedido pelo nosso cardápio digital:
   > https://recantodabarra.github.io
   > Pedidos sexta, sábado e domingo a partir das 18h. Entregamos aqui na Praia de Barra do Rio!
2. **Respostas rápidas**: mesma mensagem com o atalho `/cardapio`.
3. **Mensagem de ausência** → Programar → "Fora do horário comercial".
4. **Perfil comercial → Site**: `https://recantodabarra.github.io`.

---

## 8. Configurações novas no `backend\.env`

| Chave                       | Para quê                                              |
|-----------------------------|-------------------------------------------------------|
| `PUBLIC_MENU_CORS_ORIGINS`  | Sites que podem usar a API do cardápio (o GitHub Pages) |
| `PUBLIC_MENU_HOURS`         | Horário de pedidos online                             |
| `THERMAL_PRINTER`           | Impressora térmica pra impressão direta               |
| `AUTO_PRINT_ONLINE_ORDERS`  | Ticket automático ao aceitar pedido online            |

---

## 9. Comandos úteis (PowerShell)

```powershell
Get-Service BarrioERP-*                               # status dos serviços
Restart-Service BarrioERP-Backend                     # reinicia o Barrio
Restart-Service BarrioERP-Menu-Publico                # reinicia o cardápio
tailscale serve status                                # HTTPS do Barrio
tailscale funnel status                               # o que está público
tailscale funnel --https=8443 off                     # tira o cardápio do ar (link do PC)
schtasks /run /tn "BarrioERP-Publicar-Cardapio"       # publica o cardápio agora
Get-Content logs\service_err.log -Tail 30             # erros do Barrio
Get-Content logs\service_menu_err.log -Tail 30        # erros do cardápio público
schtasks /run /tn "BarrioERP-Limpar-Logs"             # limpa logs antigos agora
```

**Logs:** tudo fica em `logs/` (fora do git). A tarefa **`BarrioERP-Limpar-Logs`**
(dia 1 de cada mês, 10h) apaga os arquivos rotacionados com mais de 30 dias
— script `deploy/windows/limpar_logs.ps1`.

Subir o Barrio de novo do zero (ex: PC novo): `deploy/windows/instalar_servicos.ps1`
(como administrador) já configura o `tailscale serve`.

**Antes de mexer no banco** (migration, limpeza): faça backup com `pg_dump`.

---

## 10. Backup e recuperação

**Onde fica:** todo dia às 23:59 a tarefa `BarrioERP-DB-Backup` gera
`BarrioERP-DB-Backup\barrio_dump.sql` e guarda em **3 lugares**: no PC, no
Google Drive (`G:\Meu Drive\BarrioERP-Backup`) e no GitHub privado (com histórico, então
dá para voltar a qualquer dia).

**Teste mensal:** a tarefa `BarrioERP-Testar-Backup` (dia 2, 10h) restaura o
backup num banco temporário, compara tabela por tabela com o real e apaga o
temporário. Resultado em `logs\testar_backup.log` ("RESULTADO: OK"). À mão:

```powershell
powershell -ExecutionPolicy Bypass -File deploy\windows\testar_backup.ps1
powershell -ExecutionPolicy Bypass -File deploy\windows\testar_backup.ps1 -Dump "G:\Meu Drive\BarrioERP-Backup\barrio_dump.sql"
```

**Recuperar de verdade** (banco corrompido, PC novo) — testado em 08/11/2026:

1. Parar o Barrio: `Stop-Service BarrioERP-Backend, BarrioERP-Menu-Publico`
2. Pegar o backup mais recente (PC, Drive ou `git clone` do repositório de backup).
   Para voltar a um dia específico: `git log` no repositório de backup e
   `git checkout <commit> -- barrio_dump.sql`.
3. Recriar o banco e restaurar (usuário/senha estão no `backend\.env`):
   ```powershell
   $bin = "C:\Program Files\PostgreSQL\16\bin"
   & "$bin\dropdb.exe"   -U <usuario> barrio      # só se o banco antigo existir
   & "$bin\createdb.exe" -U <usuario> barrio
   & "$bin\psql.exe"     -U <usuario> -d barrio -v ON_ERROR_STOP=1 -f barrio_dump.sql
   ```
4. Religar: `Start-Service BarrioERP-Backend, BarrioERP-Menu-Publico`

O que se perde: só o que foi lançado depois do último backup (no pior caso,
o dia de hoje). Por isso, se der problema no meio do movimento, **antes de
qualquer coisa** rode o backup na hora: `schtasks /run /tn "BarrioERP-DB-Backup"`.

---

## 11. Monitor (avisos quando algo cai)

A tarefa **`BarrioERP-Monitor`** roda a cada 5 min (também na bateria) e verifica:
Barrio no ar, cardápio online (local e link público), pedido online esperando
aceite há mais de 10 min, impressora térmica, **notebook na bateria (luz caiu)**,
backup com mais de 30h ou teste mensal reprovado, publicação do cardápio no
GitHub e disco com menos de 10 GB.

Avisa quando o problema começa, lembra a cada 2h e avisa quando volta.
Os avisos vão pro **Telegram** (`ALERT_TELEGRAM_BOT_TOKEN` e
`ALERT_TELEGRAM_CHAT_ID` no `backend\.env`); sem isso, ficam só em
`logs\monitor.log`.

```powershell
cd backend
.venv\Scripts\python.exe -m app.monitoring --verbose   # roda agora e mostra cada verificação
.venv\Scripts\python.exe -m app.monitoring --test      # manda uma mensagem de teste
```

### De olho no dinheiro (mesma tarefa, `app/alerts.py`)

- **Alerta na hora** (lê a auditoria a cada 5 min): item cancelado ou
  diminuído **depois de ir pra cozinha**, estorno de pagamento, desconto a
  partir de 20% da conta, comanda cancelada — com quem fez, mesa, valor e
  motivo. Ações do **dono** não geram alerta. Diferença de caixa no
  fechamento a partir de R$ 20 avisa sempre. Limites no `.env`:
  `ALERT_DISCOUNT_PERCENT`, `ALERT_CASH_DIFF`; desligar: `ALERT_ANOMALIES=false`.
- **Resumo da noite** às 6h (até 7h, se o PC estava desligado): recebido por
  forma de pagamento, comandas e ticket médio, pedidos do cardápio, fiado
  novo, o que ficou aberto, caixa, e cancelamentos/estornos/descontos com
  nome. Noite sem movimento não manda nada.
- **Limpeza de logs** 1x por dia: apaga arquivos rotacionados com mais de 30
  dias e deixa `monitor.log`/`publicar_cardapio.log` com as últimas 2000 linhas.

### Configurar o Telegram (uma vez)

1. No Telegram, fale com **@BotFather** → `/newbot` → escolha um nome. Ele
   responde com o **token** (algo como `123456:ABC...`).
2. Mande qualquer mensagem pro bot novo (ou adicione ele no grupo do bar).
3. Abra no navegador `https://api.telegram.org/bot<TOKEN>/getUpdates` e
   copie o número de `"chat":{"id": ...}` (grupo começa com `-`).
4. No `backend\.env`:
   ```
   ALERT_TELEGRAM_BOT_TOKEN=<token>
   ALERT_TELEGRAM_CHAT_ID=<id>
   ```
5. Teste: `.venv\Scripts\python.exe -m app.monitoring --test`. Não precisa
   reiniciar nada — o monitor lê o `.env` a cada rodada.

---

## 12. O que é público e o que não é

- **Público:** o cardápio (itens, preços, WhatsApp do bar) e o envio de
  pedido — que só entra numa fila de aceite, sem acesso a comandas, caixa ou login.
- **Só na rede Tailscale:** o Barrio inteiro (login, comandas, caixa, relatórios).

---

## 13. Pendências

- Domínio próprio pro cardápio (ex: `cardapio.recantodabarra.com.br`) — depois.
- Fotos dos pratos no cardápio — quando houver fotos.
