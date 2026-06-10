/**
 * api.ts — camada de comunicação com o backend
 *
 * Centraliza toda interação HTTP: URL base, headers, tratamento de erros.
 * Nenhum componente deve usar fetch() diretamente — sempre via funções aqui.
 *
 * O Vite está configurado com proxy: /api → http://localhost:8000
 * Então todas as chamadas usam caminhos relativos (/api/v1/...) e funcionam
 * tanto em desenvolvimento (proxy) quanto em produção (mesmo servidor).
 */

const BASE = '/api/v1'

// ── Token no localStorage ──────────────────────────────────────────────────

export function getToken(): string | null {
  return localStorage.getItem('barrio_token')
}

function saveToken(token: string): void {
  localStorage.setItem('barrio_token', token)
}

export function clearToken(): void {
  localStorage.removeItem('barrio_token')
  localStorage.removeItem('barrio_user')
}

// ── Usuário local (decodificado do JWT) ────────────────────────────────────

export interface LocalUser {
  id: string
  name: string
  role: string
  company_id: string
}

function saveUser(user: LocalUser): void {
  localStorage.setItem('barrio_user', JSON.stringify(user))
}

export function getUser(): LocalUser | null {
  const raw = localStorage.getItem('barrio_user')
  return raw ? (JSON.parse(raw) as LocalUser) : null
}

/**
 * Decodifica o payload do JWT sem biblioteca externa.
 * JWTs são base64url — apenas lemos o payload (parte do meio).
 * NÃO verificamos a assinatura aqui — o backend faz isso em cada request.
 */
function decodeToken(token: string): LocalUser {
  const payload = JSON.parse(atob(token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')))
  return {
    id: payload.sub,
    name: payload.name,
    role: payload.role,
    company_id: payload.company_id,
  }
}

// ── Funções de autenticação ────────────────────────────────────────────────

export interface LoginResult {
  user: LocalUser
}

/**
 * Autentica o usuário e salva token + dados no localStorage.
 * Lança erro com mensagem legível se as credenciais forem inválidas.
 */
export async function login(email: string, password: string): Promise<LoginResult> {
  const res = await fetch(`${BASE}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  })

  if (!res.ok) {
    // O backend retorna { error: "...", message: "..." } nos erros de domínio
    const body = await res.json().catch(() => ({}))
    throw new Error(body.message ?? 'Credenciais inválidas')
  }

  const { access_token } = await res.json()
  const user = decodeToken(access_token)

  saveToken(access_token)
  saveUser(user)

  return { user }
}
