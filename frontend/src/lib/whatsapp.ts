/**
 * Abre a conversa com o cliente direto no app do WhatsApp (Desktop no PC,
 * app no celular) — whatsapp:// pula a página intermediária do navegador que
 * o wa.me abre no computador. Telefone só com dígitos, com ou sem 55.
 */
export function whatsLink(phone: string, text?: string) {
  const digits = phone.length <= 11 ? `55${phone}` : phone
  return `whatsapp://send?phone=${digits}${text ? `&text=${encodeURIComponent(text)}` : ''}`
}
