# Cardápio público — próximos passos (sessão de 14/08/2026)

## Estado atual — tudo pronto, só falta expor com segurança

- Serviço Windows **`BarrioERP-Menu-Publico`** rodando na porta **8090**, isolado do
  ERP (não carrega login/comandas/caixa, só lê o cardápio). Script de instalação:
  `instalar_servico_cardapio_publico.ps1`.
- Página em `public_menu_static/index.html` (+ `logo.png`), visual moderno
  (banner com gradiente, cards, abas de categoria), com **pizza meio a meio**
  funcionando (cobra sempre o valor da metade mais cara).
- Cliente monta o pedido e manda pronto pro WhatsApp — não grava direto no banco.
- Config em `backend/.env`: `PUBLIC_MENU_WHATSAPP=5584991303956`,
  `PUBLIC_MENU_DISPLAY_NAME=Recanto da Barra`.
- Testado e funcionando em: `http://100.109.236.99:8090/cardapio/matriz`
  (rede Tailscale) e `http://localhost:8090/cardapio/matriz` (no próprio PC).

## ⚠️ O que deu errado hoje (não repetir)

`tailscale funnel --bg 8090` expõe por padrão na porta pública **443** — a MESMA
porta que `https://gomes-pc.cod-aldebaran.ts.net` usa pro ERP
(`BarrioERP-Backend-TLS`). Isso fez o hostname inteiro passar a responder o
cardápio em vez do sistema, pra qualquer acesso por **nome** (funcionou normal
por IP direto). Resultado: sistema "sumiu" pro celular/tablet no meio do
expediente. Resolvido desligando o funnel (`tailscale funnel --https=443 off`).

**Acesso de emergência que salvou o expediente, guardar essa info:**
`http://100.109.236.99:8000` — HTTP simples, porta 8000, sempre funciona
independente de Tailscale Funnel/DNS/certificado (é o fallback que já existia
desde a config original dos serviços).

## Próximos passos (fazer fora do horário de pico, com calma)

1. Ligar o Funnel numa porta **separada** da 443, pra nunca mais colidir com o ERP:
   ```
   tailscale funnel --https=443 off        # garantir que tá desligado
   tailscale funnel --bg --https=8443 8090
   ```
   Link público final: `https://gomes-pc.cod-aldebaran.ts.net:8443/cardapio/matriz`

2. **Antes de divulgar pra qualquer cliente**, confirmar que o ERP não foi afetado:
   ```
   curl https://gomes-pc.cod-aldebaran.ts.net/health
   ```
   Tem que responder o JSON do ERP (`{"status":"ok",...}`), não o HTML do cardápio.

3. Só depois de confirmado: gerar QR code do link pra colocar nas mesas/balcão,
   e/ou colocar no Instagram/WhatsApp Business.

4. Pendências menores (perguntar ao usuário antes de mexer):
   - `Establishment.name` no banco está como "Matriz" (nome interno/tenant) —
     a página usa `PUBLIC_MENU_DISPLAY_NAME` como nome fantasia, então isso é
     só cosmético e já está resolvido, mas vale confirmar se querem meia o
     nome do tenant no banco também.
   - Confirmar se `5584991303956` é realmente o WhatsApp que deve receber os
     pedidos (veio do "Delivery" impresso no cardápio).

## Arquivos relevantes desta feature

- `backend/app/public_menu.py` — app FastAPI isolado
- `public_menu_static/index.html`, `public_menu_static/logo.png` — página pública
- `instalar_servico_cardapio_publico.ps1` — instala o serviço Windows
- `backend/.env` → `PUBLIC_MENU_WHATSAPP`, `PUBLIC_MENU_DISPLAY_NAME`
- Memória: `barrioerp-cardapio-publico.md` (contexto completo da decisão/arquitetura)

## Fora do escopo desta feature (não mexi, achei no caminho)

- `frontend/src/components/OrderDetailView.tsx` e `frontend/src/lib/api.ts` têm
  alterações não commitadas, de antes desta sessão — provavelmente trabalho em
  andamento do próprio usuário, só ficou registrado aqui pra não se perder.
- Nada do que foi criado nesta sessão (cardápio público) foi commitado nem
  enviado pro GitHub ainda — decidir isso na próxima sessão.
