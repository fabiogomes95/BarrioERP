const BASE = '/api/v1'

// ── Token ─────────────────────────────────────────────────────────────────────

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

// ── Usuário local ─────────────────────────────────────────────────────────────

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

function decodeToken(token: string): LocalUser {
  const payload = JSON.parse(atob(token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')))
  return {
    id: payload.sub,
    name: payload.name,
    role: payload.role,
    company_id: payload.company_id,
  }
}

// ── Request helper autenticado ────────────────────────────────────────────────

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getToken()
  const res = await fetch(`${BASE}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(options.headers ?? {}),
    },
  })

  if (res.status === 401) {
    clearToken()
    window.location.href = '/login'
    throw new Error('Sessão expirada')
  }

  if (res.status === 204) return undefined as T

  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    const msg = body.detail ?? body.message ?? `Erro ${res.status}`
    throw new Error(Array.isArray(msg) ? msg.map((e: { msg: string }) => e.msg).join(', ') : msg)
  }

  return res.json() as Promise<T>
}

// ── Auth ──────────────────────────────────────────────────────────────────────

export interface LoginResult {
  user: LocalUser
}

export async function login(email: string, password: string): Promise<LoginResult> {
  const res = await fetch(`${BASE}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  })

  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.message ?? 'Credenciais inválidas')
  }

  const { access_token } = await res.json()
  const user = decodeToken(access_token)
  saveToken(access_token)
  saveUser(user)
  return { user }
}

// ── Mesas ─────────────────────────────────────────────────────────────────────

export type TableStatus = 'free' | 'occupied' | 'bill_requested' | 'reserved' | 'blocked'

export interface Table {
  id: string
  number: number
  label: string
  capacity: number
  status: TableStatus
  section: string | null
  is_active: boolean
  version: number
  establishment_id: string
  created_at: string
  updated_at: string
}

interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}

export async function fetchTables(): Promise<Table[]> {
  const data = await request<PaginatedResponse<Table>>('/tables/?page_size=100')
  return data.items
}

export async function createTable(data: {
  number: number
  label: string
  capacity: number
  section?: string | null
}): Promise<Table> {
  return request<Table>('/tables/', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

// ── Pedidos ───────────────────────────────────────────────────────────────────

export interface OrderItem {
  id: string
  order_id: string
  item_name: string
  unit_price: string
  quantity: number
  subtotal: string
  notes: string | null
  status: string
  cancelled_at: string | null
  cancelled_reason: string | null
}

export interface Order {
  id: string
  table_id: string | null
  waiter_id: string | null
  status: string
  guest_count: number
  customer_name: string | null
  notes: string | null
  total: string
  subtotal: string
  service_fee: string
  discount: string
  closed_at: string | null
  version: number
  items: OrderItem[]
  created_at: string
  updated_at: string
}

export async function fetchOpenOrders(tableId?: string): Promise<Order[]> {
  const qs = tableId ? `?table_id=${tableId}` : ''
  return request<Order[]>(`/orders/open${qs}`)
}

export async function createOrder(data: {
  table_id: string
  guest_count?: number
  customer_name?: string | null
  notes?: string | null
}): Promise<Order> {
  return request<Order>('/orders/', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export async function addOrderItem(
  orderId: string,
  data: {
    menu_item_id?: string
    item_name?: string
    unit_price?: number
    quantity: number
    notes?: string | null
  },
): Promise<Order> {
  return request<Order>(`/orders/${orderId}/items`, {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export async function cancelOrderItem(
  orderId: string,
  itemId: string,
  reason?: string,
): Promise<Order> {
  const qs = reason ? `?reason=${encodeURIComponent(reason)}` : ''
  return request<Order>(`/orders/${orderId}/items/${itemId}${qs}`, { method: 'DELETE' })
}

export async function closeOrder(
  orderId: string,
  version: number,
  notes?: string | null,
): Promise<Order> {
  return request<Order>(`/orders/${orderId}/close`, {
    method: 'PATCH',
    body: JSON.stringify({ version, notes: notes ?? null }),
  })
}

export async function updateTableStatus(
  tableId: string,
  status: TableStatus,
  version: number,
): Promise<Table> {
  return request<Table>(`/tables/${tableId}`, {
    method: 'PATCH',
    body: JSON.stringify({ status, version }),
  })
}

// ── Pagamentos ────────────────────────────────────────────────────────────────

export type PaymentMethod = 'cash' | 'credit_card' | 'debit_card' | 'pix' | 'voucher' | 'other'

export interface Payment {
  id: string
  order_id: string
  cashier_id: string | null
  method: PaymentMethod
  status: string
  amount: string
  amount_tendered: string | null
  change_given: string | null
  reference: string | null
  created_at: string
  updated_at: string
}

export async function fetchOrderPayments(orderId: string): Promise<Payment[]> {
  // Rota sem trailing slash (router de payments sem prefix)
  return request<Payment[]>(`/orders/${orderId}/payments`)
}

export async function registerPayment(data: {
  order_id: string
  method: PaymentMethod
  // Dinheiro = strings para preservar precisão decimal (regra: API → strings, nunca float)
  amount: string
  amount_tendered?: string | null
  reference?: string | null
}): Promise<Payment> {
  return request<Payment>('/payments', { method: 'POST', body: JSON.stringify(data) })
}

export async function finishOrder(orderId: string, version: number): Promise<Order> {
  // Fecha a comanda APENAS se o total pago cobrir o total da conta
  return request<Order>(`/orders/${orderId}/finish`, {
    method: 'PATCH',
    body: JSON.stringify({ version }),
  })
}

// ── Cardápio ──────────────────────────────────────────────────────────────────

export interface Category {
  id: string
  name: string
  description: string | null
  sort_order: number
  is_active: boolean
}

export interface MenuItem {
  id: string
  category_id: string
  name: string
  description: string | null
  price: string
  sort_order: number
  is_active: boolean
  is_available: boolean
}

export async function fetchCategories(): Promise<Category[]> {
  // Endpoint retorna lista simples (não paginada) — sem trailing slash
  return request<Category[]>('/menu/categories')
}

export async function fetchMenuItems(categoryId?: string): Promise<MenuItem[]> {
  const qs = categoryId ? `&category_id=${categoryId}` : ''
  const data = await request<PaginatedResponse<MenuItem>>(`/menu/items?page_size=200${qs}`)
  return data.items
}

export async function createCategory(data: {
  name: string
  description?: string | null
  sort_order?: number
}): Promise<Category> {
  return request<Category>('/menu/categories', { method: 'POST', body: JSON.stringify(data) })
}

export async function updateCategory(
  id: string,
  data: { name?: string; description?: string | null; sort_order?: number; is_active?: boolean },
): Promise<Category> {
  return request<Category>(`/menu/categories/${id}`, { method: 'PATCH', body: JSON.stringify(data) })
}

export async function deleteCategory(id: string): Promise<void> {
  return request<void>(`/menu/categories/${id}`, { method: 'DELETE' })
}

export async function createMenuItem(data: {
  category_id: string
  name: string
  description?: string | null
  price: number
  sort_order?: number
}): Promise<MenuItem> {
  return request<MenuItem>('/menu/items', { method: 'POST', body: JSON.stringify(data) })
}

export async function updateMenuItem(
  id: string,
  data: {
    name?: string
    description?: string | null
    price?: number
    sort_order?: number
    is_active?: boolean
    is_available?: boolean
    category_id?: string
  },
): Promise<MenuItem> {
  return request<MenuItem>(`/menu/items/${id}`, { method: 'PATCH', body: JSON.stringify(data) })
}

export async function deleteMenuItem(id: string): Promise<void> {
  return request<void>(`/menu/items/${id}`, { method: 'DELETE' })
}

// ── Equipe ────────────────────────────────────────────────────────────────────

export type UserRole = 'owner' | 'manager' | 'cashier' | 'waiter' | 'kitchen'

export interface TeamUser {
  id: string
  company_id: string
  establishment_id: string | null
  name: string
  email: string
  phone: string | null
  role: UserRole
  is_active: boolean
  created_at: string
  updated_at: string
}

export async function fetchUsers(): Promise<TeamUser[]> {
  const data = await request<PaginatedResponse<TeamUser>>('/users/?page_size=100')
  return data.items
}

export async function createUser(data: {
  name: string
  email: string
  password: string
  role: UserRole
  phone?: string | null
}): Promise<TeamUser> {
  return request<TeamUser>('/users/', { method: 'POST', body: JSON.stringify(data) })
}

export async function updateUser(
  id: string,
  data: {
    name?: string
    email?: string
    phone?: string | null
    role?: UserRole
    is_active?: boolean
  },
): Promise<TeamUser> {
  return request<TeamUser>(`/users/${id}`, { method: 'PATCH', body: JSON.stringify(data) })
}

export async function deleteUser(id: string): Promise<void> {
  return request<void>(`/users/${id}`, { method: 'DELETE' })
}

export async function resetUserPassword(
  id: string,
  newPassword: string,
): Promise<TeamUser> {
  return request<TeamUser>(`/users/${id}/password`, {
    method: 'PATCH',
    body: JSON.stringify({ new_password: newPassword, confirm_password: newPassword }),
  })
}
