import { type DailyReport, type Order, type Table } from './api'

const METHOD_LABEL: Record<string, string> = {
  cash: 'Dinheiro', credit_card: 'Crédito', debit_card: 'Débito',
  pix: 'Pix', voucher: 'Voucher', other: 'Outro',
}

function brl(v: string | number) {
  return Number(v).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })
}

function esc(s: string) {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

function fmtDay(day: string) {
  return new Date(day + 'T12:00:00').toLocaleDateString('pt-BR')
}

// ── CSV ──────────────────────────────────────────────────────────────────────

function csvField(v: string | number) {
  const s = String(v)
  return /[;"\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
}

function csvRow(fields: (string | number)[]) {
  return fields.map(csvField).join(';')
}

export function exportDailyReportCSV(
  report: DailyReport, history: Order[], tables: Table[], day: string,
) {
  const lines: string[] = []

  lines.push(csvRow(['Relatório do dia', fmtDay(day)]))
  lines.push('')
  lines.push(csvRow(['Faturado', brl(report.revenue_total)]))
  lines.push(csvRow(['Comandas', report.orders_count]))
  lines.push(csvRow(['Ticket médio', brl(report.average_ticket)]))
  lines.push('')

  lines.push(csvRow(['Forma de pagamento', 'Quantidade', 'Total']))
  for (const m of report.by_payment_method) {
    lines.push(csvRow([METHOD_LABEL[m.method] ?? m.method, m.count, brl(m.total)]))
  }
  lines.push('')

  lines.push(csvRow(['Item mais vendido', 'Quantidade', 'Total']))
  for (const it of report.top_items) {
    lines.push(csvRow([it.name, it.quantity, brl(it.total)]))
  }
  lines.push('')

  lines.push(csvRow(['Comanda fechada', 'Tipo', 'Itens', 'Total', 'Fechada às']))
  for (const o of history) {
    const table = tables.find(t => t.id === o.table_id)
    const where = table ? `Mesa ${table.number}` : (o.customer_name ?? 'Balcão')
    const items = o.items.filter(i => i.status !== 'cancelled').length
    const time = o.closed_at ? new Date(o.closed_at).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' }) : ''
    lines.push(csvRow([where, o.order_type, items, brl(o.total), time]))
  }

  // BOM pro Excel reconhecer UTF-8 (acentos) corretamente
  const blob = new Blob(['﻿' + lines.join('\r\n')], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `relatorio-${day}.csv`
  a.click()
  URL.revokeObjectURL(url)
}

// ── PDF (via impressão do navegador — "Salvar como PDF" no diálogo) ──────────

export function printDailyReport(
  report: DailyReport, history: Order[], tables: Table[], day: string, barName: string,
) {
  const win = window.open('', '_blank', 'width=800,height=900')
  if (!win) { alert('Permita pop-ups para exportar o relatório.'); return }

  const paymentRows = report.by_payment_method.length === 0
    ? '<tr><td colspan="3" class="empty">Nenhum pagamento registrado</td></tr>'
    : report.by_payment_method.map(m => `
      <tr>
        <td>${esc(METHOD_LABEL[m.method] ?? m.method)}</td>
        <td class="num">${m.count}</td>
        <td class="num">${brl(m.total)}</td>
      </tr>
    `).join('')

  const itemRows = report.top_items.length === 0
    ? '<tr><td colspan="3" class="empty">Nada vendido no período</td></tr>'
    : report.top_items.map(it => `
      <tr>
        <td>${esc(it.name)}</td>
        <td class="num">${it.quantity}×</td>
        <td class="num">${brl(it.total)}</td>
      </tr>
    `).join('')

  const historyRows = history.length === 0
    ? '<tr><td colspan="4" class="empty">Nenhuma comanda fechada no período</td></tr>'
    : history.map(o => {
      const table = tables.find(t => t.id === o.table_id)
      const where = table ? `Mesa ${table.number}` : (o.customer_name ?? 'Balcão')
      const items = o.items.filter(i => i.status !== 'cancelled').length
      const time = o.closed_at ? new Date(o.closed_at).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' }) : '—'
      return `
        <tr>
          <td>${esc(where)}</td>
          <td class="num">${items}</td>
          <td class="num">${brl(o.total)}</td>
          <td class="num">${time}</td>
        </tr>
      `
    }).join('')

  const html = `<!doctype html>
<html><head><meta charset="utf-8"><title>Relatório ${fmtDay(day)}</title>
<style>
  @page { size: A4; margin: 16mm; }
  * { box-sizing: border-box; }
  body { font-family: Arial, Helvetica, sans-serif; color: #1a1a1a; margin: 0; }
  h1 { font-size: 20px; margin: 0 0 2px; }
  .sub { color: #666; font-size: 12px; margin-bottom: 20px; }
  .stats { display: flex; gap: 16px; margin-bottom: 24px; }
  .stat { flex: 1; border: 1px solid #ddd; border-radius: 8px; padding: 10px 14px; }
  .stat .label { font-size: 10px; text-transform: uppercase; color: #888; letter-spacing: .05em; }
  .stat .value { font-size: 18px; font-weight: bold; margin-top: 2px; }
  h2 { font-size: 13px; text-transform: uppercase; letter-spacing: .04em; color: #444;
       margin: 22px 0 8px; border-bottom: 2px solid #222; padding-bottom: 4px; }
  table { width: 100%; border-collapse: collapse; font-size: 12px; }
  th { text-align: left; font-size: 10px; text-transform: uppercase; color: #888; padding: 4px 6px; }
  td { padding: 5px 6px; border-top: 1px solid #eee; }
  .num { text-align: right; white-space: nowrap; }
  th.num { text-align: right; }
  .empty { color: #999; font-style: italic; padding: 10px 6px; }
  .foot { margin-top: 30px; font-size: 10px; color: #999; text-align: center; }
</style></head>
<body>
  <h1>${esc(barName)}</h1>
  <div class="sub">Relatório do dia — ${fmtDay(day)}</div>

  <div class="stats">
    <div class="stat"><div class="label">Faturado</div><div class="value">${brl(report.revenue_total)}</div></div>
    <div class="stat"><div class="label">Comandas</div><div class="value">${report.orders_count}</div></div>
    <div class="stat"><div class="label">Ticket médio</div><div class="value">${brl(report.average_ticket)}</div></div>
  </div>

  <h2>Por forma de pagamento</h2>
  <table>
    <thead><tr><th>Método</th><th class="num">Qtd</th><th class="num">Total</th></tr></thead>
    <tbody>${paymentRows}</tbody>
  </table>

  <h2>Itens mais vendidos</h2>
  <table>
    <thead><tr><th>Item</th><th class="num">Qtd</th><th class="num">Total</th></tr></thead>
    <tbody>${itemRows}</tbody>
  </table>

  <h2>Comandas fechadas</h2>
  <table>
    <thead><tr><th>Mesa/Cliente</th><th class="num">Itens</th><th class="num">Total</th><th class="num">Fechada às</th></tr></thead>
    <tbody>${historyRows}</tbody>
  </table>

  <div class="foot">Gerado em ${new Date().toLocaleString('pt-BR')} · BarrioERP</div>
  <script>
    window.onload = function () { window.print(); };
  </script>
</body></html>`

  win.document.open()
  win.document.write(html)
  win.document.close()
}
