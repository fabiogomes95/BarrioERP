# BarrioERP — Pendente

> Este arquivo existe pra não perder o desenho pensado entre sessões.
> Não é doc permanente como o `CHANGELOG.md`/`ARCHITECTURE.md`.

## Contexto

Dono confirmou que vai comercializar o BarrioERP pra outros bares, não é só
uso próprio — por isso a prioridade em fechar gaps de produto que hoje não
afetam o Recanto mas afetariam outro cliente.

## Status: leva de comercialização concluída

1. ~~Relatórios por período~~ — **feito** (v0.11.0)
2. ~~Controle de estoque/insumos~~ — **feito** (v0.12.0, `ARCHITECTURE.md` seção 29)
3. ~~Reservas de mesa com data/hora~~ — **feito** (v0.13.0, `ARCHITECTURE.md` seção 30)
4. ~~Tela simplificada pra cozinha (KDS)~~ — **feito** (v0.14.0, `ARCHITECTURE.md` seção 31)

Nenhum item novo definido ainda — retomar com o dono quando surgir a
próxima prioridade.

## Próximo item técnico (não é do roadmap de produto, decidido adiar)

**Impressão térmica sem confirmação manual no PC.** Hoje o celular manda
o pedido de impressão (via SSE, `frontend/src/lib/notifications.ts`) e o
PC marcado como "impressora do bar" abre uma aba e chama `window.print()`
(`frontend/src/lib/print.ts`) — funciona, mas o Chrome sempre mostra o
diálogo nativo de impressão, exigindo um clique manual no PC.

Duas opções discutidas em 2026-07-24 (nenhuma implementada ainda):

1. **Kiosk printing do Chrome (recomendado pra tentar primeiro)** — zero
   código novo. Trocar como o navegador abre nesse PC por um atalho com
   a flag `chrome.exe --kiosk-printing`, e definir a impressora térmica
   como padrão do Windows nesse PC. Isso faz o `window.print()` que já
   existe imprimir direto, sem diálogo.
2. **Agente local de impressão (mais robusto, mais trabalho)** — um
   serviço novo rodando no PC (nos moldes dos serviços NSSM que já
   existem) que fala ESC/POS direto com a impressora (USB/rede), sem
   passar pelo navegador. Mais confiável a longo prazo (não depende de
   manter uma aba aberta/focada), mas é infraestrutura nova.

Plano: começar pela opção 1 (sem risco, sem código); só migrar pra opção
2 se o modo kiosk se mostrar instável na prática.

**Fora do escopo (decisão do dono):**
- Multi-estabelecimento pela UI — não vai querer
- Emissão fiscal (NFC-e) — descartada, dono não é MEI/CNPJ

**Pendências fiscais/de negócio separadas** (não são deste arquivo):
ver `MEI_SOFTWARE.md` e `PENDENTE_NEGOCIO.md` na raiz do projeto.
