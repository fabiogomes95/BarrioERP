import { type Order, type Table } from './api'

// Recibo para impressora térmica 80mm via impressão do navegador.
// Abre uma janela com o conteúdo formatado e dispara a impressão.

function brl(v: string | number) {
  return Number(v).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })
}

function esc(s: string) {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

export function printComanda(order: Order, table: Table | undefined, barName: string) {
  const win = window.open('', '_blank', 'width=360,height=640')
  if (!win) {
    alert('Permita pop-ups para imprimir o recibo.')
    return
  }

  const active = order.items.filter(i => i.status !== 'cancelled')
  const now = new Date().toLocaleString('pt-BR')
  const where = table ? `Mesa ${table.number}` : 'Balcão / Avulso'

  const itemRows = active.map(it => `
    <div class="row">
      <span class="qtyname">${it.quantity}x ${esc(it.item_name)}</span>
      <span class="val">${brl(it.subtotal)}</span>
    </div>
    ${it.notes ? `<div class="note">&nbsp;&nbsp;- ${esc(it.notes)}</div>` : ''}
  `).join('')

  const feeRow = Number(order.service_fee) > 0
    ? `<div class="row"><span>Taxa de serviço</span><span>${brl(order.service_fee)}</span></div>` : ''
  const discRow = Number(order.discount) > 0
    ? `<div class="row"><span>Desconto</span><span>-${brl(order.discount)}</span></div>` : ''

  const html = `<!doctype html>
<html><head><meta charset="utf-8"><title>Comanda</title>
<style>
  @page { size: 80mm auto; margin: 0; }
  * { box-sizing: border-box; }
  body { width: 80mm; margin: 0; padding: 4mm 3mm; font-family: 'Courier New', monospace;
         color: #000; font-size: 12px; line-height: 1.35; }
  .center { text-align: center; }
  .bar { font-size: 16px; font-weight: bold; }
  .muted { font-size: 11px; }
  .hr { border-top: 1px dashed #000; margin: 6px 0; }
  .row { display: flex; justify-content: space-between; gap: 6px; }
  .qtyname { flex: 1; }
  .val { white-space: nowrap; }
  .note { font-size: 10px; font-style: italic; }
  .total { font-size: 15px; font-weight: bold; }
  .foot { margin-top: 8px; font-size: 10px; }
</style></head>
<body>
  <div class="center bar">${esc(barName)}</div>
  <div class="center muted">${esc(where)}${order.customer_name ? ' · ' + esc(order.customer_name) : ''}</div>
  <div class="center muted">${now}</div>
  <div class="hr"></div>
  ${itemRows || '<div class="center muted">(sem itens)</div>'}
  <div class="hr"></div>
  ${feeRow}${discRow}
  <div class="row total"><span>TOTAL</span><span>${brl(order.total)}</span></div>
  <div class="hr"></div>
  <div class="center foot">Obrigado pela preferência!</div>
  <script>
    window.onload = function () {
      window.print();
      window.onafterprint = function () { window.close(); };
      setTimeout(function () { window.close(); }, 1500);
    };
  </script>
</body></html>`

  win.document.open()
  win.document.write(html)
  win.document.close()
}
