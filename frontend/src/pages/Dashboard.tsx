/** Tela principal: KPIs da linha, mapa da fábrica, gráfico ao vivo e alarmes. */

import { useEffect, useMemo, useState } from 'react';

import { api } from '../api/client';
import { useAuth } from '../auth/AuthContext';
import { AlarmList } from '../components/AlarmList';
import { FactoryMap } from '../components/FactoryMap';
import { METRICS, MetricChart } from '../components/MetricChart';
import { Kpi, Panel, StatusLabel, fmt } from '../components/common';
import type { MetricKey } from '../hooks/useMetricHistory';
import type { Alarm, LineSummary, MachineLive } from '../types';

interface Props {
  machines: MachineLive[];
  alarms: Alarm[];
  summary: LineSummary | null;
}

export function Dashboard({ machines, alarms, summary }: Props) {
  const { can } = useAuth();
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [metric, setMetric] = useState<MetricKey>('temperature');
  const [actionError, setActionError] = useState<string | null>(null);

  // Seleciona a primeira máquina assim que o snapshot chega.
  useEffect(() => {
    if (selectedId === null && machines.length > 0) {
      setSelectedId(machines[0].id);
    }
  }, [machines, selectedId]);

  const selected = useMemo(
    () => machines.find((m) => m.id === selectedId),
    [machines, selectedId],
  );

  const oeeTone = summary
    ? summary.oee >= 0.85
      ? 'good'
      : summary.oee >= 0.6
        ? 'warn'
        : 'bad'
    : 'neutral';

  const injectFault = async () => {
    if (!selected) return;
    setActionError(null);
    try {
      await api.simulation.injectFault(selected.id);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Falha ao injetar');
    }
  };

  return (
    <>
      <div className="page-header">
        <div>
          <h1>Linha {summary?.line ?? 'LINE-01'}</h1>
          <p>
            Janela de análise:{' '}
            {summary
              ? `${fmt.dateTime(summary.window_start)} → ${fmt.time(summary.window_end)}`
              : 'carregando…'}
          </p>
        </div>
      </div>

      <div className="kpi-grid">
        <Kpi
          label="OEE"
          value={summary ? fmt.pct(summary.oee) : '—'}
          hint="Disponibilidade × Performance × Qualidade"
          tone={oeeTone}
        />
        <Kpi
          label="Máquinas produzindo"
          value={summary ? `${summary.machines_running}/${summary.machines_total}` : '—'}
          hint={summary ? `${summary.machines_faulted} em falha` : undefined}
          tone={summary && summary.machines_faulted > 0 ? 'warn' : 'good'}
        />
        <Kpi
          label="Peças boas"
          value={summary ? fmt.int(summary.good_count) : '—'}
          hint={summary ? `${fmt.int(summary.scrap_count)} de refugo` : undefined}
        />
        <Kpi
          label="Taxa de refugo"
          value={summary ? fmt.pct(summary.scrap_rate, 2) : '—'}
          tone={summary && summary.scrap_rate > 0.05 ? 'bad' : 'good'}
        />
        <Kpi
          label="Alarmes abertos"
          value={summary ? summary.active_alarms : '—'}
          hint={summary ? `${summary.critical_alarms} críticos` : undefined}
          tone={summary && summary.critical_alarms > 0 ? 'bad' : 'good'}
        />
        <Kpi
          label="Energia consumida"
          value={summary ? summary.energy_kwh.toFixed(1) : '—'}
          unit="kWh"
          hint={summary ? `Eficiência média ${fmt.num(summary.avg_efficiency)}%` : undefined}
        />
      </div>

      <div className="grid-2">
        <div className="stack">
          <Panel
            title="Mapa da fábrica"
            subtitle="Clique numa máquina para ver os detalhes"
          >
            <FactoryMap
              machines={machines}
              selectedId={selectedId}
              onSelect={(m) => setSelectedId(m.id)}
            />
          </Panel>

          {selected && (
            <Panel
              title={`${selected.code} — ${selected.name}`}
              subtitle={`Tempo de ciclo ideal: ${selected.ideal_cycle_time_s}s · última leitura ${fmt.time(
                selected.last_reading_at,
              )}`}
              actions={
                <div className="metric-tabs">
                  {METRICS.map((m) => (
                    <button
                      key={m.key}
                      type="button"
                      className={`metric-tab${metric === m.key ? ' active' : ''}`}
                      onClick={() => setMetric(m.key)}
                    >
                      {m.label}
                    </button>
                  ))}
                </div>
              }
            >
              <div className="kpi-grid" style={{ marginBottom: 14 }}>
                <Kpi label="Estado" value={<StatusLabel status={selected.status} />} />
                <Kpi
                  label="Temperatura"
                  value={fmt.num(selected.temperature)}
                  unit="°C"
                  hint={`nominal ${selected.temp_nominal}`}
                />
                <Kpi
                  label="Eficiência"
                  value={fmt.num(selected.efficiency)}
                  unit="%"
                  hint={`meta ≥ ${selected.eff_warning}%`}
                />
                <Kpi
                  label="Vibração"
                  value={fmt.num(selected.vibration, 2)}
                  unit="mm/s"
                  hint={`limite ${selected.vib_critical}`}
                />
              </div>

              <MetricChart machine={selected} metric={metric} />

              {can('OPERATOR') && (
                <div className="row" style={{ marginTop: 14 }}>
                  <button type="button" className="btn btn-sm btn-danger" onClick={injectFault}>
                    Injetar falha (demonstração)
                  </button>
                  {actionError && <span style={{ color: 'var(--critical)' }}>{actionError}</span>}
                </div>
              )}
            </Panel>
          )}
        </div>

        <Panel
          title="Alarmes ativos"
          subtitle={`${alarms.length} aberto(s)`}
        >
          <AlarmList alarms={alarms} limit={20} />
        </Panel>
      </div>
    </>
  );
}
