/** Componentes de apresentação reaproveitados pelas páginas. */

import type { ReactNode } from 'react';

import type { AlarmSeverity, MachineStatus } from '../types';

export const STATUS_LABEL: Record<MachineStatus, string> = {
  RUNNING: 'Produzindo',
  IDLE: 'Parada',
  SETUP: 'Setup',
  MAINTENANCE: 'Manutenção',
  FAULT: 'Falha',
  OFFLINE: 'Desligada',
};

export const SEVERITY_LABEL: Record<AlarmSeverity, string> = {
  INFO: 'Informativo',
  WARNING: 'Aviso',
  CRITICAL: 'Crítico',
};

export const ALARM_CODE_LABEL: Record<string, string> = {
  HIGH_TEMPERATURE: 'Temperatura alta',
  LOW_EFFICIENCY: 'Eficiência baixa',
  OVERSPEED: 'Velocidade excessiva',
  UNDERSPEED: 'Velocidade insuficiente',
  HIGH_VIBRATION: 'Vibração alta',
  HIGH_PRESSURE: 'Pressão alta',
  MACHINE_FAULT: 'Falha de máquina',
  ANOMALY_DETECTED: 'Anomalia (IA)',
};

export function StatusDot({ status }: { status: MachineStatus }) {
  return <span className={`status-dot st-${status}`} title={STATUS_LABEL[status]} />;
}

export function StatusLabel({ status }: { status: MachineStatus }) {
  return (
    <span className="row" style={{ gap: 6 }}>
      <StatusDot status={status} />
      {STATUS_LABEL[status]}
    </span>
  );
}

interface KpiProps {
  label: string;
  value: ReactNode;
  unit?: string;
  hint?: string;
  tone?: 'neutral' | 'good' | 'warn' | 'bad';
}

export function Kpi({ label, value, unit, hint, tone = 'neutral' }: KpiProps) {
  return (
    <div className={`kpi ${tone === 'neutral' ? '' : tone}`}>
      <div className="kpi-label">{label}</div>
      <div className="kpi-value">
        {value}
        {unit && <span className="unit">{unit}</span>}
      </div>
      {hint && <div className="kpi-hint">{hint}</div>}
    </div>
  );
}

export function Panel({
  title,
  subtitle,
  actions,
  children,
}: {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="panel">
      <header className="panel-header">
        <div>
          <h2>{title}</h2>
          {subtitle && <div className="subtitle">{subtitle}</div>}
        </div>
        {actions}
      </header>
      {children}
    </section>
  );
}

export function EmptyState({ children }: { children: ReactNode }) {
  return <div className="empty-state">{children}</div>;
}

/** Barra de progresso 0–1, colorida pela faixa do valor. */
export function Meter({ value }: { value: number }) {
  const pct = Math.max(0, Math.min(1, value)) * 100;
  const color = pct >= 85 ? 'var(--running)' : pct >= 60 ? 'var(--warning)' : 'var(--critical)';
  return (
    <div className="bar-track">
      <div className="bar-fill" style={{ width: `${pct}%`, background: color }} />
    </div>
  );
}

export const fmt = {
  pct: (value: number, digits = 1) => `${(value * 100).toFixed(digits)}%`,
  num: (value: number | null | undefined, digits = 1) =>
    value === null || value === undefined ? '—' : value.toFixed(digits),
  int: (value: number) => value.toLocaleString('pt-BR'),
  time: (iso: string | null) =>
    iso ? new Date(iso).toLocaleTimeString('pt-BR', { hour12: false }) : '—',
  dateTime: (iso: string | null) =>
    iso ? new Date(iso).toLocaleString('pt-BR', { hour12: false }) : '—',
  /** "há 3 min" — usado nos alarmes. */
  ago: (iso: string) => {
    const seconds = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
    if (seconds < 60) return `há ${Math.floor(seconds)}s`;
    if (seconds < 3600) return `há ${Math.floor(seconds / 60)} min`;
    if (seconds < 86400) return `há ${Math.floor(seconds / 3600)} h`;
    return `há ${Math.floor(seconds / 86400)} d`;
  },
};
