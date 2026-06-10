import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { getToken } from './lib/api'
import Layout from './components/Layout'
import LoginPage from './pages/LoginPage'
import MesasPage from './pages/MesasPage'
import PedidosPage from './pages/PedidosPage'
import CardapioPage from './pages/CardapioPage'
import EquipePage from './pages/EquipePage'

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  if (!getToken()) return <Navigate to="/login" replace />
  return <>{children}</>
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />

        <Route
          path="/"
          element={
            <ProtectedRoute>
              <Layout />
            </ProtectedRoute>
          }
        >
          {/* Página inicial → Mesas */}
          <Route index element={<Navigate to="/mesas" replace />} />
          <Route path="mesas"    element={<MesasPage />} />
          <Route path="pedidos"  element={<PedidosPage />} />
          <Route path="cardapio" element={<CardapioPage />} />
          <Route path="equipe"   element={<EquipePage />} />
        </Route>

        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
