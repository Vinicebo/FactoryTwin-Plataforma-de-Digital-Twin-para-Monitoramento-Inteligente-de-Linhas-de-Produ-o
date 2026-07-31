/** Gráfico ao vivo de uma grandeza, com as faixas de aviso e crítico. */

import {
  Area,
  AreaChart,
  CartesianGrid,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import type { MetricKey } from '../hooks/useMetricHistory';
import { useMetricHistory } from '../hooks/useMetricHistory';
import type { MachineLive } from '../types';
import { EmptyState } from './common';

export const METRICS: { key: MetricKey; label: string; unit: string }[] = [
  { key: 'temperature', label: 'Temperatura', unit: '°C' },
  { key: 'speed', label: 'Velocidade', unit: 'rpm' },
  { key: 'efficiency', label: 'Eficiência', unit: '%' },
  { key: 'energy', label: 'Energia', unit: 'kW' },
  { key: 'vibration', label: 'Vibração', unit: 'mm/s' },
  { key: 'pressure', label: 'Pressão', unit: 'bar' },
];

/** Limites de aviso/crítico da métrica, quando existirem para aquela grandeza. */
function thresholds(machine: MachineLive, metric: MetricKey) {
  switch (metric) {
    case 'temperature':
      return { warning: machine.temp_warning, critical: machine.temp_critical };
    case 'efficiency':
      return { warning: machine.eff_warning, critical: machine.eff_critical };
    case 'vibration':
      return { warning: machine.vib_warning, critical: machine.vib_critical };
    case 'speed':
      return { warning: machine.speed_max, critical: null };
    case 'pressure':
      return { warning: machine.pressure_max, critical: null };
    default:
      return { warning: null, critical: null };
  }
}

interface Props {
  machine: MachineLive;
  metric: MetricKey;
}

export function MetricChart({ machine, metric }: Props) {
  const points = useMetricHistory(machine, metric);
  const meta = METRICS.find((m) => m.key === metric)!;
  const limits = thresholds(machine, metric);

  if (points.length < 2) {
    return <EmptyState>Coletando dados de {meta.label.toLowerCase()}…</EmptyState>;
  }

  const values = points.map((p) => p.value);
  const candidates = [...values, limits.warning, limits.critical].filter(
    (v): v is number => v !== null && v !== undefined,
  );
  const min = Math.min(...candidates);
  const max = Math.max(...candidates);
  const padding = (max - min || 1) * 0.15;

  return (
    <ResponsiveContainer width="100%" height={220}>
      <AreaChart data={points} margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
        <defs>
          <linearGradient id={`grad-${metric}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--accent)" stopOpacity={0.35} />
            <stop offset="100%" stopColor="var(--accent)" stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" vertical={false} />
        <XAxis
          dataKey="label"
          tick={{ fill: 'var(--text-dim)', fontSize: 11 }}
          stroke="var(--border)"
          minTickGap={40}
        />
        <YAxis
          domain={[min - padding, max + padding]}
          tick={{ fill: 'var(--text-dim)', fontSize: 11 }}
          stroke="var(--border)"
          tickFormatter={(v: number) => v.toFixed(0)}
          width={46}
        />
        <Tooltip
          contentStyle={{
            background: 'var(--bg-elevated)',
            border: '1px solid var(--border-strong)',
            borderRadius: 6,
            fontSize: 12,
          }}
          labelStyle={{ color: 'var(--text-muted)' }}
          formatter={(value: number) => [`${value.toFixed(2)} ${meta.unit}`, meta.label]}
        />
        {limits.warning !== null && (
          <ReferenceLine
            y={limits.warning}
            stroke="var(--warning)"
            strokeDasharray="4 4"
            label={{ value: 'aviso', fill: 'var(--warning)', fontSize: 10, position: 'right' }}
          />
        )}
        {limits.critical !== null && (
          <ReferenceLine
            y={limits.critical}
            stroke="var(--critical)"
            strokeDasharray="4 4"
            label={{ value: 'crítico', fill: 'var(--critical)', fontSize: 10, position: 'right' }}
          />
        )}
        <Area
          type="monotone"
          dataKey="value"
          stroke="var(--accent)"
          strokeWidth={2}
          fill={`url(#grad-${metric})`}
          isAnimationActive={false}
          dot={false}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}
