// Tema claro/escuro — aplicado via atributo data-theme na <html>.
// Sem escolha salva, index.css segue prefers-color-scheme do sistema
// automaticamente (ver @media nesse arquivo).

export type Theme = 'light' | 'dark'

const KEY = 'barrio_theme'

export function getStoredTheme(): Theme | null {
  const v = localStorage.getItem(KEY)
  return v === 'light' || v === 'dark' ? v : null
}

function systemPrefersDark(): boolean {
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ?? false
}

export function getEffectiveTheme(): Theme {
  return getStoredTheme() ?? (systemPrefersDark() ? 'dark' : 'light')
}

// Cor das barras do celular (status/navegação) — mesmo fundo do app em cada
// tema (--color-app-bg em index.css). Sem isso, com o app no escuro e o
// celular no claro, a barra de status ficava creme em cima do app escuro.
const BAR_COLOR: Record<Theme, string> = { light: '#fbeedf', dark: '#1c140e' }

export function applyTheme(theme: Theme): void {
  document.documentElement.setAttribute('data-theme', theme)
  document.querySelectorAll('meta[name="theme-color"]').forEach(m => {
    m.setAttribute('content', BAR_COLOR[theme])
    m.removeAttribute('media')
  })
}

export function setTheme(theme: Theme): void {
  localStorage.setItem(KEY, theme)
  applyTheme(theme)
}

/** Chamado uma vez, antes da primeira renderização (ver main.tsx) — evita
 * flash do tema errado ao carregar a página. */
export function initTheme(): void {
  applyTheme(getEffectiveTheme())
}
