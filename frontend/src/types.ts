/** Contratos espelhando os schemas Pydantic do backend. */

export type MachineStatus =
  | 'RUNNING'
  | 'IDLE'
  | 'SETUP'
  | 'MAINTENANCE'
  | 'FAULT'
  | 'OFFLINE';

export type AlarmSeverity = 'INFO' | 'WARNING' | 'CRITICAL';
export type AlarmStatus = 'ACTIVE' | 'ACKNOWLEDGED' | 'RESOLVED';
export type UserRole = 'VIEWER' | 'OPERATOR' | 'ADMIN';

export interface User {
  id: number;
  username: string;
  email: string;
  full_name: string;
  role: UserRole;
  is_active: boolean;
  created_at: string;
}

export interface Token {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: User;
}

export interface Machine {
  id: number;
  code: string;
  name: string;
  machine_type: string;
  line: string;
  sequence: number;
  status: MachineStatus;
  is_active: boolean;
  pos_x: number;
  pos_y: number;
  ideal_cycle_time_s: number;
  temp_nominal: number;
  temp_warning: number;
  temp_critical: number;
  speed_nominal: number;
  speed_min: number;
  speed_max: number;
  eff_warning: number;
  eff_critical: number;
  vib_warning: number;
  vib_critical: number;
  pressure_nominal: number;
  pressure_max: number;
  energy_nominal: number;
}

export interface MachineLive extends Machine {
  temperature: number | null;
  speed: number | null;
  efficiency: number | null;
  energy: number | null;
  vibration: number | null;
  pressure: number | null;
  last_reading_at: string | null;
  active_alarms: number;
  highest_severity: AlarmSeverity | null;
  is_anomaly: boolean;
}

export interface Alarm {
  id: number;
  machine_id: number;
  code: string;
  severity: AlarmSeverity;
  status: AlarmStatus;
  message: string;
  measured_value: number | null;
  threshold: number | null;
  triggered_at: string;
  acknowledged_at: string | null;
  resolved_at: string | null;
  acknowledged_by_id: number | null;
  machine_code?: string;
  machine_name?: string;
}

export interface LineSummary {
  line: string;
  machines_total: number;
  machines_running: number;
  machines_faulted: number;
  machines_idle: number;
  active_alarms: number;
  critical_alarms: number;
  oee: number;
  good_count: number;
  scrap_count: number;
  scrap_rate: number;
  energy_kwh: number;
  avg_efficiency: number;
  window_start: string;
  window_end: string;
}

export interface OEEMetrics {
  machine_id: number | null;
  machine_code: string | null;
  availability: number;
  performance: number;
  quality: number;
  oee: number;
  good_count: number;
  scrap_count: number;
  total_count: number;
  scrap_rate: number;
  energy_kwh: number;
  energy_per_part: number | null;
  fault_count: number;
  mtbf_minutes: number | null;
  mttr_minutes: number | null;
  window_start: string;
  window_end: string;
}

export interface SeriesPoint {
  ts: string;
  value: number;
}

export interface MetricSeries {
  machine_id: number;
  metric: string;
  unit: string;
  points: SeriesPoint[];
}

export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface AlarmStats {
  total_active: number;
  by_severity: Record<string, number>;
  by_code: Record<string, number>;
  by_machine: Record<string, number>;
}

export interface SimulatorState {
  running: boolean;
  tick_seconds: number;
  tick_count: number;
  machines_tracked: number;
  websocket_clients: number;
}

export interface ModelInfo {
  is_ready: boolean;
  model_path: string;
  features: string[];
  metadata: Record<string, unknown>;
}

/** Telemetria enviada pelo WebSocket a cada tick do simulador. */
export interface TelemetryEvent {
  machine_id: number;
  machine_code: string;
  ts: string;
  temperature: number;
  speed: number;
  efficiency: number;
  energy: number;
  vibration: number;
  pressure: number;
  status: MachineStatus;
  anomaly_score: number | null;
  is_anomaly: boolean;
}

export type RealtimeEventType =
  | 'snapshot'
  | 'telemetry'
  | 'alarm_raised'
  | 'alarm_updated'
  | 'alarm_resolved'
  | 'machine_status'
  | 'line_summary'
  | 'simulator_state';

export interface RealtimeEvent<T = unknown> {
  type: RealtimeEventType;
  ts: string;
  payload: T;
}

export interface SnapshotPayload {
  machines: MachineLive[];
  summary: LineSummary;
  alarms: Alarm[];
}

export interface MachineStatusPayload {
  machine_id: number;
  machine_code: string;
  from: MachineStatus;
  to: MachineStatus;
  by?: string;
  reason?: string | null;
}
