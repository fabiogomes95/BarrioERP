import { type Order, type Table } from './api'

function brl(v: string | number) {
  return Number(v).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })
}

// Cores fixas (não seguem o tema claro/escuro do app) — o recibo deve
// sempre parecer "papel", igual ao impresso na térmica e ao cardápio físico.
const FONT = "'Courier New', monospace"
const PAPER = '#fcf6ed'
const INK = '#231107'
const MUTED = '#7a5c48'
const DASH = '#c7ac8b'

function loadImage(src: string): Promise<HTMLImageElement | null> {
  return new Promise(resolve => {
    const img = new Image()
    img.onload = () => resolve(img)
    img.onerror = () => resolve(null) // sem logo, segue sem quebrar o recibo
    img.src = src
  })
}

function wrapText(ctx: CanvasRenderingContext2D, text: string, maxWidth: number): string[] {
  const words = text.split(' ')
  const lines: string[] = []
  let line = ''
  for (const w of words) {
    const test = line ? `${line} ${w}` : w
    if (ctx.measureText(test).width > maxWidth && line) {
      lines.push(line)
      line = w
    } else {
      line = test
    }
  }
  if (line) lines.push(line)
  return lines.length ? lines : ['']
}

/** Gera uma imagem PNG do recibo, com a mesma cara do impresso — pra compartilhar (WhatsApp etc). */
export async function buildReceiptImage(
  order: Order, table: Table | undefined, barName: string,
): Promise<Blob> {
  const active = order.items.filter(i => i.status !== 'cancelled')
  const typeLabel = order.order_type === 'delivery'
    ? 'Delivery'
    : order.order_type === 'pickup'
      ? 'Retirada'
      : 'Consumo no local'
  const where = table ? `Mesa ${table.number}` : typeLabel
  const subtitle = where + (order.customer_name ? ` — ${order.customer_name}` : '')
  const now = new Date().toLocaleString('pt-BR')
  const logo = await loadImage('/icon-recanto.png')

  const W = 440
  const PAD = 28
  const contentW = W - PAD * 2
  const valueColW = 84
  const nameColW = contentW - valueColW

  // Canvas de medição (não desenhado) — usado só pra calcular a altura total antes de criar o canvas final.
  const measure = document.createElement('canvas').getContext('2d')!

  type Row = { lines: string[]; value: string; bold?: boolean; muted?: boolean }
  measure.font = `bold 14px ${FONT}`
  const itemRows: Row[] = active.map(it => ({
    lines: wrapText(measure, `${it.quantity}x ${it.item_name}`, nameColW),
    value: brl(it.subtotal),
  }))

  const totalsRows: Row[] = []
  if (Number(order.service_fee) > 0) {
    totalsRows.push({ lines: ['Subtotal'], value: brl(order.subtotal), muted: true })
    totalsRows.push({ lines: [`Taxa de serviço (${order.service_fee_percent}%)`], value: brl(order.service_fee), muted: true })
  }
  if (Number(order.discount) > 0) {
    totalsRows.push({ lines: ['Desconto'], value: `-${brl(order.discount)}`, muted: true })
  }

  const LOGO_SIZE = 56
  const HEADER_H = (logo ? LOGO_SIZE + 14 : 0) + 34 + 24 + 22 + 20   // logo + nome do bar + subtítulo + data + respiro
  const DASH_H = 22
  const ITEM_ROW_LINE_H = 22
  const ITEM_ROW_GAP = 10
  const TOTALS_ROW_H = 24
  const TOTAL_ROW_H = 46
  const FOOTER_H = 50

  const itemsH = itemRows.reduce((h, r) => h + r.lines.length * ITEM_ROW_LINE_H + ITEM_ROW_GAP, 0)
  const totalsH = totalsRows.length * TOTALS_ROW_H

  const H = PAD + HEADER_H + DASH_H + itemsH + DASH_H + totalsH + TOTAL_ROW_H + DASH_H + FOOTER_H + PAD

  const canvas = document.createElement('canvas')
  const scale = 2 // retina, fica nítido no zoom do WhatsApp
  canvas.width = W * scale
  canvas.height = H * scale
  const ctx = canvas.getContext('2d')!
  ctx.scale(scale, scale)

  ctx.fillStyle = PAPER
  ctx.fillRect(0, 0, W, H)
  ctx.textBaseline = 'alphabetic'

  let y = PAD

  if (logo) {
    ctx.save()
    ctx.beginPath()
    ctx.arc(W / 2, y + LOGO_SIZE / 2, LOGO_SIZE / 2, 0, Math.PI * 2)
    ctx.closePath()
    ctx.clip()
    ctx.drawImage(logo, W / 2 - LOGO_SIZE / 2, y, LOGO_SIZE, LOGO_SIZE)
    ctx.restore()
    y += LOGO_SIZE + 14
  }

  ctx.fillStyle = INK
  ctx.font = `bold 21px ${FONT}`
  ctx.textAlign = 'center'
  y += 24
  ctx.fillText(barName, W / 2, y)

  ctx.font = `14px ${FONT}`
  ctx.fillStyle = MUTED
  y += 26
  ctx.fillText(subtitle, W / 2, y)

  y += 22
  ctx.fillText(now, W / 2, y)

  y += 14
  y = drawDash(ctx, y, PAD, W - PAD)

  ctx.textAlign = 'left'
  if (itemRows.length === 0) {
    ctx.font = `italic 14px ${FONT}`
    ctx.fillStyle = MUTED
    ctx.textAlign = 'center'
    y += ITEM_ROW_LINE_H
    ctx.fillText('(sem itens)', W / 2, y)
    ctx.textAlign = 'left'
  } else {
    for (const row of itemRows) {
      ctx.font = `bold 14px ${FONT}`
      row.lines.forEach((line, i) => {
        y += ITEM_ROW_LINE_H
        ctx.fillStyle = INK
        ctx.textAlign = 'left'
        ctx.fillText(line, PAD, y)
        if (i === 0) {
          const nameW = ctx.measureText(line).width
          const valueW = ctx.measureText(row.value).width
          const dotsStart = PAD + nameW + 6
          const dotsEnd = W - PAD - valueW - 6
          if (dotsEnd > dotsStart) {
            ctx.fillStyle = DASH
            ctx.font = `14px ${FONT}`
            let x = dotsStart
            while (x < dotsEnd) { ctx.fillText('.', x, y); x += 5 }
            ctx.font = `bold 14px ${FONT}`
          }
          ctx.fillStyle = INK
          ctx.textAlign = 'right'
          ctx.fillText(row.value, W - PAD, y)
        }
      })
      y += ITEM_ROW_GAP
    }
  }

  y = drawDash(ctx, y, PAD, W - PAD)

  for (const row of totalsRows) {
    y += TOTALS_ROW_H
    ctx.font = `14px ${FONT}`
    ctx.fillStyle = MUTED
    ctx.textAlign = 'left'
    ctx.fillText(row.lines[0], PAD, y)
    ctx.textAlign = 'right'
    ctx.fillText(row.value, W - PAD, y)
  }

  y += 14
  ctx.strokeStyle = INK
  ctx.lineWidth = 1.5
  ctx.beginPath()
  ctx.moveTo(PAD, y)
  ctx.lineTo(W - PAD, y)
  ctx.stroke()

  y += 32
  ctx.font = `bold 19px ${FONT}`
  ctx.fillStyle = INK
  ctx.textAlign = 'left'
  ctx.fillText('TOTAL', PAD, y)
  ctx.textAlign = 'right'
  ctx.fillText(brl(order.total), W - PAD, y)

  y += 20
  y = drawDash(ctx, y, PAD, W - PAD)

  ctx.font = `14px ${FONT}`
  ctx.fillStyle = MUTED
  ctx.textAlign = 'center'
  y += 24
  ctx.fillText('Obrigado pela preferência!', W / 2, y)

  return new Promise(resolve => canvas.toBlob(b => resolve(b!), 'image/png'))
}

function drawDash(ctx: CanvasRenderingContext2D, y: number, x0: number, x1: number): number {
  ctx.strokeStyle = DASH
  ctx.lineWidth = 1
  ctx.setLineDash([4, 4])
  ctx.beginPath()
  ctx.moveTo(x0, y)
  ctx.lineTo(x1, y)
  ctx.stroke()
  ctx.setLineDash([])
  return y
}

/**
 * Compartilha o recibo como imagem via WhatsApp.
 * Com suporte a Web Share API + arquivos: abre o menu nativo de compartilhar já com a imagem anexada.
 * Sem suporte: baixa a imagem e abre o WhatsApp Web, pra anexar manualmente.
 */
export async function shareReceiptWhatsApp(
  order: Order, table: Table | undefined, barName: string,
): Promise<'shared' | 'downloaded'> {
  const blob = await buildReceiptImage(order, table, barName)
  const file = new File([blob], `comanda-${order.id.slice(0, 8)}.png`, { type: 'image/png' })

  const nav = navigator as Navigator & { canShare?: (data: { files: File[] }) => boolean }
  if (nav.share && nav.canShare?.({ files: [file] })) {
    await nav.share({ files: [file] })
    return 'shared'
  }

  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = file.name
  a.click()
  URL.revokeObjectURL(url)
  window.open('https://web.whatsapp.com/', '_blank')
  return 'downloaded'
}
