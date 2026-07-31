/** Sessão do usuário: login, logout e o perfil corrente (Fase 9). */

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';

import { api, tokenStorage } from '../api/client';
import type { User, UserRole } from '../types';

interface AuthState {
  user: User | null;
  token: string | null;
  loading: boolean;
  error: string | null;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
  /** `true` se o perfil do usuário atende ao nível exigido. */
  can: (minimum: UserRole) => boolean;
}

const ROLE_LEVEL: Record<UserRole, number> = { VIEWER: 0, OPERATOR: 1, ADMIN: 2 };

const AuthContext = createContext<AuthState | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(() => tokenStorage.get());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Ao abrir o app com um token salvo, revalida contra o backend: o token pode
  // ter expirado enquanto a aba estava fechada.
  useEffect(() => {
    if (!token) {
      setLoading(false);
      return;
    }
    let cancelled = false;
    api.auth
      .me()
      .then((me) => {
        if (!cancelled) setUser(me);
      })
      .catch(() => {
        if (!cancelled) {
          tokenStorage.clear();
          setToken(null);
          setUser(null);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [token]);

  const login = useCallback(async (username: string, password: string) => {
    setError(null);
    try {
      const result = await api.auth.login(username, password);
      tokenStorage.set(result.access_token);
      setToken(result.access_token);
      setUser(result.user);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Falha ao autenticar';
      setError(message);
      throw err;
    }
  }, []);

  const logout = useCallback(() => {
    tokenStorage.clear();
    setToken(null);
    setUser(null);
  }, []);

  const can = useCallback(
    (minimum: UserRole) => (user ? ROLE_LEVEL[user.role] >= ROLE_LEVEL[minimum] : false),
    [user],
  );

  const value = useMemo(
    () => ({ user, token, loading, error, login, logout, can }),
    [user, token, loading, error, login, logout, can],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth precisa estar dentro de <AuthProvider>');
  return context;
}
