import { useState } from 'react';

import { useAuth } from '../auth/AuthContext';

export function Login() {
  const { login, error } = useAuth();
  const [username, setUsername] = useState('admin');
  const [password, setPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setSubmitting(true);
    try {
      await login(username, password);
    } catch {
      // O erro já é exposto pelo contexto de autenticação.
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="login-page">
      <form className="login-card" onSubmit={handleSubmit}>
        <div className="brand" style={{ marginBottom: 18 }}>
          <span className="brand-mark">⚙</span>
          <span>
            FactoryTwin
            <small>Digital Twin Industrial</small>
          </span>
        </div>

        <h1>Entrar</h1>
        <p className="subtitle">Monitoramento da linha LINE-01</p>

        {error && <div className="error-box">{error}</div>}

        <div className="field">
          <label htmlFor="username">Usuário</label>
          <input
            id="username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoComplete="username"
            required
          />
        </div>

        <div className="field">
          <label htmlFor="password">Senha</label>
          <input
            id="password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            required
          />
        </div>

        <button
          type="submit"
          className="btn btn-primary"
          style={{ width: '100%', marginTop: 6 }}
          disabled={submitting}
        >
          {submitting ? 'Entrando…' : 'Entrar'}
        </button>

        <div className="demo-users">
          Usuários de demonstração:
          <br />
          <code>admin / admin123</code> — administrador
          <br />
          <code>operador / operador123</code> — operador
          <br />
          <code>visitante / visitante123</code> — somente leitura
        </div>
      </form>
    </div>
  );
}
