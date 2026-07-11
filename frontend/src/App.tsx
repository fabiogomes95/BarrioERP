import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { getToken } from './lib/api'
import ErrorBoundary from './components/ErrorBoundary'
import Layout from './components/Layout'
import LoginPage from './pages/LoginPage'
import RegisterPage from './pages/RegisterPage'
import DashboardPage from './pages/DashboardPage'
import MesasPage from './pages/MesasPage'
import PedidosPage from './pages/PedidosPage'
import ComandaPage from './pages/ComandaPage'
import CaixaPage from './pages/CaixaPage'
import AdminPage from './pages/AdminPage'
import CardapioPage from './pages/CardapioPage'
import EquipePage from './pages/EquipePage'
import FiadoPage from './pages/FiadoPage'
import AuditoriaPage from './pages/AuditoriaPage'

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  if (!getToken()) return <Navigate to="/login" replace />
  return <>{children}</>
}

export default function App() {
  return (
    <BrowserRouter>
      <ErrorBoundary>
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
          <Route path="pedidos"  element={<PedidosPage />} />
          <Route path="comanda/:orderId" element={<ComandaPage />} />
          <Route path="caixa"    element={<CaixaPage />} />
          <Route path="admin"    element={<AdminPage />} />
          <Route path="cardapio" element={<CardapioPage />} />
          <Route path="equipe"   element={<EquipePage />} />
          <Route path="fiado"    element={<FiadoPage />} />
          <Route path="auditoria" element={<AuditoriaPage />} />
        </Route>

        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
      </ErrorBoundary>
    </BrowserRouter>
  )
}
