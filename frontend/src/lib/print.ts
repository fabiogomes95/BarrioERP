import { type Order, type Table } from './api'

export interface KitchenItem {
  name: string
  qty: number
  notes?: string | null
}

export function printCozinha(items: KitchenItem[], where: string) {
  const win = window.open('', '_blank', 'width=360,height=500')
  if (!win) { alert('Permita pop-ups para imprimir.'); return }

  const now = new Date().toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })
  const single = items.length === 1
  const nameSize = single ? '34px' : '20px'
  const qtySize  = single ? '20px' : '14px'

  const rows = items.map(it => `
    <div class="item">
      <div class="qty" style="font-size:${qtySize}">${it.qty}×</div>
      <div class="name" style="font-size:${nameSize}">${esc(it.name)}</div>
      ${it.notes ? `<div class="notes">${esc(it.notes)}</div>` : ''}
    </div>
    <div class="hr"></div>
  `).join('')

  const html = `<!doctype html>
<html><head><meta charset="utf-8"><title>Cozinha</title>
<style>
  @page { size: 80mm auto; margin: 0; }
  * { box-sizing: border-box; }
  body { width: 80mm; margin: 0; padding: 6mm 4mm; font-family: 'Courier New', monospace;
         color: #000; text-align: center; }
  .where { font-size: 13px; font-weight: bold; margin-bottom: 4px; }
  .hr { border-top: 2px dashed #000; margin: 8px 0; }
  .item { margin: 4px 0; }
  .qty { font-weight: bold; }
  .name { font-weight: bold; line-height: 1.2; word-break: break-word; margin: 4px 0; }
  .notes { font-size: 12px; font-style: italic; }
  .time { font-size: 11px; color: #333; }
</style></head>
<body>
  <div class="where">${esc(where)}</div>
  <div class="hr"></div>
  ${rows}
  <div class="time">${now}</div>
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

// Recibo para impressora térmica 80mm via impressão do navegador.
// Abre uma janela com o conteúdo formatado e dispara a impressão.

function brl(v: string | number) {
  return Number(v).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })
}

function esc(s: string) {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

export function printComanda(order: Order, table: Table | undefined, barName: string) {
  // Abre em janela com largura de 72mm em pixels (72 * 96/25.4 ≈ 272px)
  const win = window.open('', '_blank', 'width=304,height=700')
  if (!win) {
    alert('Permita pop-ups para imprimir o recibo.')
    return
  }

  const active = order.items.filter(i => i.status !== 'cancelled')
  const now = new Date().toLocaleString('pt-BR')
  const typeLabel = order.order_type === 'delivery'
    ? 'Delivery'
    : order.order_type === 'pickup'
      ? 'Retirada'
      : 'Consumo no local'
  const where = table ? `Mesa ${table.number}` : typeLabel

  const itemRows = active.map(it => `
    <tr>
      <td class="qtyname">${it.quantity}x ${esc(it.item_name)}</td>
      <td class="val">${brl(it.subtotal)}</td>
    </tr>
  `).join('')

  const subRow = Number(order.service_fee) > 0
    ? `<tr><td>Subtotal</td><td class="val">${brl(order.subtotal)}</td></tr>` : ''
  const feeRow = Number(order.service_fee) > 0
    ? `<tr><td>Taxa de servico (${order.service_fee_percent}%)</td><td class="val">${brl(order.service_fee)}</td></tr>` : ''
  const discRow = Number(order.discount) > 0
    ? `<tr><td>Desconto</td><td class="val">-${brl(order.discount)}</td></tr>` : ''

  // Não usa @page size para não conflitar com o driver da impressora POS-80C.
  // Largura 72mm = área imprimível (80mm − 2×4mm margens).
  // Fontes em pt: unidade física independente do DPI da tela.
  // Mínimo 10pt para legibilidade nesta impressora.
  const html = `<!doctype html>
<html><head><meta charset="utf-8"><title>Comanda</title>
<style>
  @page { margin: 0 4mm; }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { width: 72mm; margin: 0 auto; padding: 3mm 0;
         font-family: 'Courier New', monospace;
         font-size: 10pt; line-height: 1.2; color: #000; font-weight: bold; }
  .center { text-align: center; }
  .bar { font-size: 13pt; font-weight: bold; margin-bottom: 1mm; }
  .sub { font-size: 9pt; }
  .hr { border: none; border-top: 1px dashed #000; margin: 1.5mm 0; }
  table { width: 100%; border-collapse: collapse; }
  td { vertical-align: top; padding: 0.3mm 0; }
  .qtyname { text-align: left; word-break: break-word; }
  .val { text-align: right; white-space: nowrap; padding-left: 2mm; }
  .total-row td { font-size: 12pt; font-weight: bold; padding-top: 1.5mm; border-top: 1px solid #000; }
  .foot { margin-top: 3mm; font-size: 9pt; text-align: center; }
</style></head>
<body>
  <div class="center bar">${esc(barName)}</div>
  <div class="center sub">${esc(where)}${order.customer_name ? ' - ' + esc(order.customer_name) : ''}</div>
  <div class="center sub">${now}</div>
  <div class="hr"></div>
  <table>
    ${itemRows || '<tr><td class="sub center">(sem itens)</td></tr>'}
  </table>
  <div class="hr"></div>
  <table>
    ${subRow}${feeRow}${discRow}
    <tr class="total-row"><td>TOTAL</td><td class="val">${brl(order.total)}</td></tr>
  </table>
  <div class="hr"></div>
  <div class="foot">Obrigado pela preferencia!</div>
  <script>
    window.onload = function () {
      window.print();
      window.onafterprint = function () { window.close(); };
      setTimeout(function () { window.close(); }, 2000);
    };
  </script>
</body></html>`

  win.document.open()
  win.document.write(html)
  win.document.close()
}
