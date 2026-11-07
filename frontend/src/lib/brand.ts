import { getUser } from './api'

/**
 * Marca do estabelecimento no topo do app. O Barrio atende outros bares, então
 * a identidade do Recanto da Barra (mesmo cabeçalho do cardápio público:
 * "Recanto [logo] Da Barra") só aparece quando é ELE que está logado — os
 * demais continuam vendo a marca "Barrio".
 */
export interface Brand {
  left: string
  right: string
  full: string
  tagline: string
  logo: string
}

const RECANTO: Brand = {
  left: 'Recanto',
  right: 'Da Barra',
  full: 'Recanto da Barra',
  tagline: 'Bar & Restaurante',
  logo: '/brand/recanto-logo.png',
}

function normalize(s: string) {
  return s.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().trim()
}

export function getBrand(): Brand | null {
  const company = getUser()?.company_name
  return company && normalize(company) === 'recanto da barra' ? RECANTO : null
}
