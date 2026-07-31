import { NavLink, Navigate, Route, Routes } from 'react-router-dom';

import { useAuth } from './auth/AuthContext';
import { useRealtime } from './hooks/useRealtime';
import { Alarms } from './pages/Alarms';
import { Analytics } from './pages/Analytics';
import { Dashboard } from './pages/Dashboard';
import { Login } from './pages/Login';
import { Machines } from './pages/Machines';

const CONNECTION_LABEL = {
  open: 'Tempo real',
  connecting: 'Conectando…',
  closed: 'Desconectado',
} as const;

const ROLE_LABEL = {
  ADMIN: 'Administrador',
  OPERATOR: 'Operador',
  VIEWER: 'Visitante',
} as const;

export default function App() {
  const { user, token, loading, logout } = useAuth();
  // O hook só abre o socket quando há token; ao deslogar, ele fecha sozinho.
  const { connection, machines, alarms, summary } = useRealtime(token);

  if (loading) {
    return <div className="login-page">Carregando…</div>;
  }

  if (!user) {
    return <Login />;
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark">⚙</span>
          <span>
            FactoryTwin
            <small>Digital Twin Industrial</small>
          </span>
        </div>

        <nav className="nav">
          <NavLink to="/" end>
            Painel
          </NavLink>
          <NavLink to="/maquinas">Máquinas</NavLink>
          <NavLink to="/alarmes">
            Alarmes{alarms.length > 0 && ` (${alarms.length})`}
          </NavLink>
          <NavLink to="/analise">Análise</NavLink>
        </nav>

        <div className="topbar-right">
          <div className={`conn-indicator ${connection}`}>
            <span className="dot" />
            {CONNECTION_LABEL[connection]}
          </div>
          <div className="user-chip">
            <strong>{user.full_name || user.username}</strong>
            <span>{ROLE_LABEL[user.role]}</span>
          </div>
          <button type="button" className="btn btn-sm" onClick={logout}>
            Sair
          </button>
        </div>
      </header>

      <main className="content">
        <Routes>
          <Route
            path="/"
            element={<Dashboard machines={machines} alarms={alarms} summary={summary} />}
          />
          <Route path="/maquinas" element={<Machines machines={machines} />} />
          <Route path="/alarmes" element={<Alarms alarms={alarms} />} />
          <Route path="/analise" element={<Analytics />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  );
}
