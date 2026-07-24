# MEI — parte específica do software (BarrioERP como assinatura)

> Checklist de pendências fiscais/administrativas só da parte de **vender o
> BarrioERP como assinatura** pelo MEI atual. Não cobre a regularização do
> CPF/bar (isso já está com o contador) nem os pontos de negócio/técnicos
> (ver conversa — infra, billing, produto). Apagar ou arquivar depois que
> tudo aqui estiver feito.

## 1. Adicionar CNAE secundária de software

- [ ] Acessar o Portal do Empreendedor (MEI) e adicionar atividade secundária
  de TI. Confirmar com o contador (ou no próprio portal) qual CNAE se
  encaixa melhor no modelo de negócio — os candidatos comuns são:
  - `6201-5/01` — Desenvolvimento de programas de computador sob encomenda
  - `6203-1/00` — Desenvolvimento e licenciamento de programas de
    computador não-customizáveis (mais perto do modelo SaaS "pronto,
    mesmo sistema pra todo mundo")
  - `6209-1/00` — Suporte técnico, manutenção e outros serviços em
    tecnologia da informação
  - A escolha certa muda a natureza do serviço na nota fiscal — **confirmar
    com o contador antes de emitir a primeira nota**, não escolher no
    achismo.
- [ ] Confirmar que a atividade escolhida está na lista de ocupações
  permitidas pro MEI (a maioria de TI está, mas o portal recusa na hora se
  não estiver).

## 2. Emissão de nota fiscal do software (serviço, não produto)

- [ ] Assinatura de software é **serviço** → precisa de NFS-e (nota fiscal
  de serviço eletrônica), emitida pelo portal da **prefeitura do
  município**, não pelo mesmo emissor de NFC-e do bar (que nem existe hoje
  — foi descartado no `PENDENTE.md`). São dois sistemas de nota diferentes.
- [ ] Verificar com a prefeitura: cadastro de ISS (Imposto Sobre Serviço)
  pra MEI — em muitos municípios o MEI é isento ou tem alíquota fixa
  simplificada, mas isso varia de cidade pra cidade. Perguntar
  especificamente pro contador o procedimento no seu município.
- [ ] Definir o fluxo prático: emitir 1 nota por cliente/mês (por
  assinatura), ou nota consolidada — depende do volume de clientes.

## 3. Teto de faturamento do MEI — monitorar, não só no fechamento do ano

- [ ] O teto do MEI é **único e somado** entre bar + software. Hoje o bar
  fica sob controle porque parte do faturamento (Pix) está separado no CPF
  da mãe — **mas isso é um problema à parte que precisa ser resolvido com o
  contador** (ver conversa), não uma forma válida de "abrir espaço" pro
  software no teto.
- [ ] Depois de decidir como o bar vai ficar regularizado, pedir pro
  contador simular: quanto de faturamento de assinatura cabe no MEI antes
  de precisar migrar pra ME (ficar de olho principalmente se a
  base de clientes crescer rápido).

## 4. O que fica fora deste documento (ver os outros pontos da conversa)

- Contrato/Termos de Uso pros clientes assinantes — jurídico, não fiscal.
- Gateway de pagamento (Stripe/Mercado Pago/Asaas) e modelo de
  assinatura/plano no sistema.
- Infra de produção (sair do PC caseiro pra algo mais robusto).
- Gaps de produto (estoque, reservas, KDS) — já mapeados no `PENDENTE.md`.

*Criado em 2026-07-24.*
