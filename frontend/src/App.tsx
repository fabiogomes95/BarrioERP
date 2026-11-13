import { lazy, Suspense, type ComponentType } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { getToken, getUser } from './lib/api'
import ErrorBoundary from './components/ErrorBoundary'
import Layout from './components/Layout'
import { Spinner } from './components/ui'
import LoginPage from './pages/LoginPage'

/**
 * Cada tela vira um arquivo separado (o celular baixa só o que abre).
 * Depois de um deploy, uma aba aberta há horas ainda aponta pros arquivos
 * antigos, que o build apagou — nesse caso recarrega a página UMA vez
 * pra pegar a versão nova, em vez de mostrar tela de erro.
 */
function lazyPage(load: () => Promise<{ default: ComponentType }>) {
  return lazy(() => load().then(
    mod => { sessionStorage.removeItem('chunk-reload'); return mod },
    err => {
      if (!sessionStorage.getItem('chunk-reload')) {
        sessionStorage.setItem('chunk-reload', '1')
        window.location.reload()
        return new Promise<never>(() => {})
      }
      throw err
    },
  ))
}

const RegisterPage = lazyPage(() => import('./pages/RegisterPage'))
const DashboardPage = lazyPage(() => import('./pages/DashboardPage'))
const MesasPage = lazyPage(() => import('./pages/MesasPage'))
const PedidosPage = lazyPage(() => import('./pages/PedidosPage'))
const ComandaPage = lazyPage(() => import('./pages/ComandaPage'))
const CaixaPage = lazyPage(() => import('./pages/CaixaPage'))
const AdminPage = lazyPage(() => import('./pages/AdminPage'))
const CardapioPage = lazyPage(() => import('./pages/CardapioPage'))
const EquipePage = lazyPage(() => import('./pages/EquipePage'))
const FiadoPage = lazyPage(() => import('./pages/FiadoPage'))
const AuditoriaPage = lazyPage(() => import('./pages/AuditoriaPage'))
const EstoquePage = lazyPage(() => import('./pages/EstoquePage'))
const ReservasPage = lazyPage(() => import('./pages/ReservasPage'))
const KDSPage = lazyPage(() => import('./pages/KDSPage'))

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  if (!getToken()) return <Navigate to="/login" replace />
  return <>{children}</>
}

/** Bloqueia a rota (redireciona pro Dashboard) se o role do usuário não estiver na lista. */
function RequireRole({ roles, children }: { roles: string[]; children: React.ReactNode }) {
  const role = getUser()?.role
  if (!role || !roles.includes(role)) return <Navigate to="/dashboard" replace />
  return <>{children}</>
}

export default function App() {
  return (
    <BrowserRouter>
      <ErrorBoundary>
      <Suspense fallback={<Spinner />}>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />

        <Route
          path="/"
          element={
            <ProtectedRoute>
              <Layout />
            </ProtectedRoute>
          }
        >
          {/* Página inicial → Dashboard */}
          <Route index element={<Navigate to="/dashboard" replace />} />
          <Route path="dashboard" element={<DashboardPage />} />
          <Route path="mesas"    element={<MesasPage />} />
          <Route path="reservas" element={<ReservasPage />} />
          <Route path="cozinha" element={<KDSPage />} />
          <Route path="pedidos"  element={<PedidosPage />} />
          <Route path="comanda/:orderId" element={<ComandaPage />} />
          <Route path="caixa"    element={<RequireRole roles={['owner', 'manager', 'cashier']}><CaixaPage /></RequireRole>} />
          <Route path="admin"    element={<RequireRole roles={['owner', 'manager']}><AdminPage /></RequireRole>} />
          <Route path="cardapio" element={<CardapioPage />} />
          <Route path="equipe"   element={<RequireRole roles={['owner', 'manager']}><EquipePage /></RequireRole>} />
          <Route path="fiado"    element={<RequireRole roles={['owner', 'manager', 'cashier']}><FiadoPage /></RequireRole>} />
          <Route path="auditoria" element={<RequireRole roles={['owner', 'manager']}><AuditoriaPage /></RequireRole>} />
          <Route path="estoque"  element={<RequireRole roles={['owner', 'manager']}><EstoquePage /></RequireRole>} />
        </Route>

        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
      </Suspense>
      </ErrorBoundary>
    </BrowserRouter>
  )
}
