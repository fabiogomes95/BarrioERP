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

export function applyTheme(theme: Theme): void {
  document.documentElement.setAttribute('data-theme', theme)
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
