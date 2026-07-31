/** Análise: OEE por máquina, gargalo da linha e status do modelo de IA. */

import { useCallback, useEffect, useState } from 'react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import { api } from '../api/client';
import { useAuth } from '../auth/AuthContext';
import { EmptyState, Kpi, Meter, Panel, fmt } from '../components/common';
import type { ModelInfo, OEEMetrics, SimulatorState } from '../types';

const WINDOWS = [1, 4, 8, 24];

export function Analytics() {
  const { can } = useAuth();
  const [hours, setHours] = useState(8);
  const [ranking, setRanking] = useState<OEEMetrics[]>([]);
  const [lineOee, setLineOee] = useState<OEEMetrics | null>(null);
  const [model, setModel] = useState<ModelInfo | null>(null);
  const [simulator, setSimulator] = useState<SimulatorState | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [rank, oee, modelInfo, simState] = await Promise.all([
        api.production.ranking(hours),
        api.production.oee(undefined, hours),
        api.ml.model(),
        api.simulation.state(),
      ]);
      setRanking(rank);
      setLineOee(oee);
      setModel(modelInfo);
      setSimulator(simState);
    } finally {
      setLoading(false);
    }
  }, [hours]);

  useEffect(() => {
    void load();
  }, [load]);

  const trainModel = async () => {
    setBusy(true);
    setMessage(null);
    try {
      const result = await api.ml.train(false);
      setMessage(`${result.detail} — ${result.metadata.n_samples} amostras`);
      setModel(await api.ml.model());
    } catch (err) {
      setMessage(err instanceof Error ? err.message : 'Falha ao treinar');
    } finally {
      setBusy(false);
    }
  };

  const toggleSimulator = async () => {
    setBusy(true);
    try {
      setSimulator(simulator?.running ? await api.simulation.stop() : await api.simulation.start());
    } finally {
      setBusy(false);
    }
  };

  const chartData = ranking.map((m) => ({
    code: m.machine_code ?? '—',
    oee: Number((m.oee * 100).toFixed(1)),
  }));

  const bottleneck = ranking[0];

  return (
    <>
      <div className="page-header">
        <div>
          <h1>Análise de desempenho</h1>
          <p>OEE decomposto, gargalo da linha e modelo de detecção de anomalias</p>
        </div>
        <div className="metric-tabs">
          {WINDOWS.map((h) => (
            <button
              key={h}
              type="button"
              className={`metric-tab${hours === h ? ' active' : ''}`}
              onClick={() => setHours(h)}
            >
              {h}h
            </button>
          ))}
        </div>
      </div>

      {message && <div className="error-box">{message}</div>}

      {lineOee && (
        <div className="kpi-grid">
          <Kpi label="OEE da linha" value={fmt.pct(lineOee.oee)} />
          <Kpi label="Disponibilidade" value={fmt.pct(lineOee.availability)} />
          <Kpi label="Performance" value={fmt.pct(lineOee.performance)} />
          <Kpi label="Qualidade" value={fmt.pct(lineOee.quality)} />
          <Kpi
            label="MTBF"
            value={lineOee.mtbf_minutes === null ? '—' : fmt.num(lineOee.mtbf_minutes)}
            unit="min"
            hint={`${lineOee.fault_count} falha(s) na janela`}
          />
          <Kpi
            label="Energia por peça"
            value={
              lineOee.energy_per_part === null ? '—' : (lineOee.energy_per_part * 1000).toFixed(2)
            }
            unit="Wh"
          />
        </div>
      )}

      <div className="grid-2">
        <Panel
          title="OEE por máquina"
          subtitle={bottleneck ? `Gargalo atual: ${bottleneck.machine_code}` : undefined}
        >
          {loading ? (
            <EmptyState>Carregando…</EmptyState>
          ) : chartData.length === 0 ? (
            <EmptyState>Sem dados de produção na janela.</EmptyState>
          ) : (
            <ResponsiveContainer width="100%" height={280}>
              <BarChart data={chartData} margin={{ top: 8, right: 12, left: -14, bottom: 0 }}>
                <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" vertical={false} />
                <XAxis
                  dataKey="code"
                  tick={{ fill: 'var(--text-dim)', fontSize: 11 }}
                  stroke="var(--border)"
                />
                <YAxis
                  domain={[0, 100]}
                  tick={{ fill: 'var(--text-dim)', fontSize: 11 }}
                  stroke="var(--border)"
                  unit="%"
                  width={48}
                />
                <Tooltip
                  cursor={{ fill: 'rgb(255 255 255 / 4%)' }}
                  contentStyle={{
                    background: 'var(--bg-elevated)',
                    border: '1px solid var(--border-strong)',
                    borderRadius: 6,
                    fontSize: 12,
                  }}
                  formatter={(value: number) => [`${value}%`, 'OEE']}
                />
                <Bar dataKey="oee" radius={[4, 4, 0, 0]}>
                  {chartData.map((entry) => (
                    <Cell
                      key={entry.code}
                      fill={
                        entry.oee >= 85
                          ? 'var(--running)'
                          : entry.oee >= 60
                            ? 'var(--warning)'
                            : 'var(--critical)'
                      }
                    />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          )}
        </Panel>

        <div className="stack">
          <Panel title="Detalhamento por máquina">
            {ranking.length === 0 ? (
              <EmptyState>Sem dados.</EmptyState>
            ) : (
              <div className="table-scroll">
                <table className="table">
                  <thead>
                    <tr>
                      <th>Máquina</th>
                      <th style={{ width: 90 }}>OEE</th>
                      <th className="num">A</th>
                      <th className="num">P</th>
                      <th className="num">Q</th>
                      <th className="num">Peças</th>
                    </tr>
                  </thead>
                  <tbody>
                    {ranking.map((m) => (
                      <tr key={m.machine_id ?? m.machine_code}>
                        <td className="code">{m.machine_code}</td>
                        <td>
                          <Meter value={m.oee} />
                          <div style={{ fontSize: 11, marginTop: 2, color: 'var(--text-muted)' }}>
                            {fmt.pct(m.oee)}
                          </div>
                        </td>
                        <td className="num">{fmt.pct(m.availability, 0)}</td>
                        <td className="num">{fmt.pct(m.performance, 0)}</td>
                        <td className="num">{fmt.pct(m.quality, 0)}</td>
                        <td className="num">{fmt.int(m.total_count)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Panel>

          <Panel
            title="Modelo de anomalias"
            subtitle="IsolationForest sobre features normalizadas"
            actions={
              can('ADMIN') && (
                <button type="button" className="btn btn-sm" disabled={busy} onClick={trainModel}>
                  Retreinar
                </button>
              )
            }
          >
            {model ? (
              <table className="table">
                <tbody>
                  <tr>
                    <td>Situação</td>
                    <td>
                      <span className={`badge ${model.is_ready ? 'st-RESOLVED' : 'sev-WARNING'}`}>
                        {model.is_ready ? 'Treinado' : 'Não treinado'}
                      </span>
                    </td>
                  </tr>
                  <tr>
                    <td>Amostras</td>
                    <td className="num">{String(model.metadata.n_samples ?? '—')}</td>
                  </tr>
                  <tr>
                    <td>Origem</td>
                    <td>{String(model.metadata.source ?? '—')}</td>
                  </tr>
                  <tr>
                    <td>Contaminação</td>
                    <td className="num">{String(model.metadata.contamination ?? '—')}</td>
                  </tr>
                  <tr>
                    <td>Treinado em</td>
                    <td>
                      {model.metadata.trained_at
                        ? fmt.dateTime(String(model.metadata.trained_at))
                        : '—'}
                    </td>
                  </tr>
                  <tr>
                    <td>Features</td>
                    <td style={{ fontSize: 11 }}>{model.features.join(', ')}</td>
                  </tr>
                </tbody>
              </table>
            ) : (
              <EmptyState>Carregando…</EmptyState>
            )}
          </Panel>

          {can('ADMIN') && simulator && (
            <Panel
              title="Simulador"
              actions={
                <button
                  type="button"
                  className={`btn btn-sm ${simulator.running ? 'btn-danger' : 'btn-primary'}`}
                  disabled={busy}
                  onClick={toggleSimulator}
                >
                  {simulator.running ? 'Parar' : 'Iniciar'}
                </button>
              }
            >
              <table className="table">
                <tbody>
                  <tr>
                    <td>Estado</td>
                    <td>{simulator.running ? 'Rodando' : 'Parado'}</td>
                  </tr>
                  <tr>
                    <td>Intervalo do tick</td>
                    <td className="num">{simulator.tick_seconds}s</td>
                  </tr>
                  <tr>
                    <td>Ticks executados</td>
                    <td className="num">{fmt.int(simulator.tick_count)}</td>
                  </tr>
                  <tr>
                    <td>Clientes WebSocket</td>
                    <td className="num">{simulator.websocket_clients}</td>
                  </tr>
                </tbody>
              </table>
            </Panel>
          )}
        </div>
      </div>
    </>
  );
}
