# BarrioERP — Pendente (negócio: billing e infra)

> Ainda não decidido como vai ser feito nenhum dos dois — só registrando que
> existem e vão precisar de decisão antes de vender pra terceiros. Ver
> também `MEI_SOFTWARE.md` (parte fiscal) e `PENDENTE.md` (roadmap de
> produto, sendo trabalhado agora).

## 1. Billing / assinatura

Não existe hoje nenhuma cobrança, plano ou bloqueio por inadimplência no
sistema. Decisões em aberto:

- Gateway de pagamento: Stripe vs Mercado Pago vs Asaas (os dois últimos
  mais comuns pra recorrência PJ pequena no Brasil, com boleto/Pix nativo)
- Modelo de plano: preço único ou por número de mesas/usuários/estabelecimentos?
- Onde mora a lógica de bloqueio: middleware que checa `Subscription` ativa
  antes de liberar login/uso da `Company`?
- Cobrança manual (você mesmo cobra por fora, sistema só registra) vs
  cobrança automática recorrente (gateway cobra sozinho todo mês)

## 2. Infra de produção

Hoje: PC em casa, Tailscale, dois serviços Windows (NSSM) — ver seção 28 do
`ARCHITECTURE.md`. Funciona bem pra 1 cliente (uso próprio), mas é ponto
único de falha grave com clientes pagantes de verdade. Decisões em aberto:

- Continuar caseiro (mais barato, mais risco) vs migrar pra VPS (Hetzner,
  DigitalOcean, etc.)
- Backup automático do Postgres — não configurado hoje, independente de
  onde o banco rodar
- Se migrar: manter multi-tenant num banco só (como já é hoje) vs isolar
  por cliente

*Criado em 2026-07-24.*
