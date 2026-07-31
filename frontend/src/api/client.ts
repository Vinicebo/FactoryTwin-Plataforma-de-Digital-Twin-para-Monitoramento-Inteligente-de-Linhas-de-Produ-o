/** Cliente HTTP da API do FactoryTwin. */

import type {
  Alarm,
  AlarmStats,
  LineSummary,
  Machine,
  MachineLive,
  MachineStatus,
  MetricSeries,
  ModelInfo,
  OEEMetrics,
  Page,
  SimulatorState,
  Token,
  User,
} from '../types';

const API_BASE = import.meta.env.VITE_API_BASE ?? '/api/v1';
const TOKEN_KEY = 'factorytwin.token';

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

export const tokenStorage = {
  get: (): string | null => localStorage.getItem(TOKEN_KEY),
  set: (token: string) => localStorage.setItem(TOKEN_KEY, token),
  clear: () => localStorage.removeItem(TOKEN_KEY),
};

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = tokenStorage.get();
  const headers = new Headers(init.headers);
  headers.set('Content-Type', 'application/json');
  if (token) headers.set('Authorization', `Bearer ${token}`);

  const response = await fetch(`${API_BASE}${path}`, { ...init, headers });

  if (!response.ok) {
    // 401 significa token expirado ou revogado: limpamos para o app voltar
    // à tela de login em vez de repetir chamadas que sempre falhariam.
    if (response.status === 401) tokenStorage.clear();

    let detail = response.statusText;
    try {
      const body = await response.json();
      detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* corpo não-JSON: mantém o statusText */
    }
    throw new ApiError(response.status, detail);
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

const get = <T>(path: string) => request<T>(path);
const post = <T>(path: string, body?: unknown) =>
  request<T>(path, { method: 'POST', body: body === undefined ? undefined : JSON.stringify(body) });
const patch = <T>(path: string, body: unknown) =>
  request<T>(path, { method: 'PATCH', body: JSON.stringify(body) });
const del = <T>(path: string) => request<T>(path, { method: 'DELETE' });

export const api = {
  auth: {
    login: (username: string, password: string) =>
      post<Token>('/auth/login/json', { username, password }),
    me: () => get<User>('/auth/me'),
    listUsers: () => get<Page<User>>('/auth/users?limit=100'),
  },

  machines: {
    list: () => get<Page<Machine>>('/machines?limit=100'),
    live: () => get<MachineLive[]>('/machines/live'),
    get: (id: number) => get<Machine>(`/machines/${id}`),
    update: (id: number, body: Partial<Machine>) => patch<Machine>(`/machines/${id}`, body),
    remove: (id: number) => del<{ detail: string }>(`/machines/${id}`),
    setStatus: (id: number, status: MachineStatus, reason?: string) =>
      post<Machine>(`/machines/${id}/status`, { status, reason }),
  },

  readings: {
    series: (machineId: number, metric: string, minutes = 60) =>
      get<MetricSeries>(
        `/readings/machines/${machineId}/series?metric=${metric}&minutes=${minutes}`,
      ),
  },

  production: {
    summary: (hours = 8) => get<LineSummary>(`/production/summary?hours=${hours}`),
    oee: (machineId?: number, hours = 8) =>
      get<OEEMetrics>(
        `/production/oee?hours=${hours}${machineId ? `&machine_id=${machineId}` : ''}`,
      ),
    ranking: (hours = 8) => get<OEEMetrics[]>(`/production/oee/ranking?hours=${hours}`),
  },

  alarms: {
    list: (onlyOpen = true, limit = 100) =>
      get<Page<Alarm>>(`/alarms?only_open=${onlyOpen}&limit=${limit}`),
    stats: () => get<AlarmStats>('/alarms/stats'),
    acknowledge: (id: number) => post<Alarm>(`/alarms/${id}/acknowledge`, {}),
    resolve: (id: number) => post<Alarm>(`/alarms/${id}/resolve`),
  },

  ml: {
    model: () => get<ModelInfo>('/ml/model'),
    train: (synthetic = false) => post<{ detail: string; metadata: Record<string, unknown> }>(
      '/ml/model/train',
      { synthetic },
    ),
  },

  simulation: {
    state: () => get<SimulatorState>('/simulation/state'),
    start: () => post<SimulatorState>('/simulation/start'),
    stop: () => post<SimulatorState>('/simulation/stop'),
    injectFault: (machineId: number) =>
      post<{ detail: string }>(`/simulation/machines/${machineId}/inject-fault`),
  },
};

/** URL do canal de tempo real, já com o token na query string. */
export function websocketUrl(token: string): string {
  const explicit = import.meta.env.VITE_WS_URL;
  if (explicit) return `${explicit}?token=${encodeURIComponent(token)}`;

  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${protocol}//${window.location.host}/ws/live?token=${encodeURIComponent(token)}`;
}
