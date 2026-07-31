/** Central de alarmes: abertos em tempo real e histórico consultado na API. */

import { useCallback, useEffect, useState } from 'react';

import { api } from '../api/client';
import { AlarmList } from '../components/AlarmList';
import { ALARM_CODE_LABEL, EmptyState, Panel, SEVERITY_LABEL, fmt } from '../components/common';
import type { Alarm, AlarmStats } from '../types';

export function Alarms({ alarms }: { alarms: Alarm[] }) {
  const [history, setHistory] = useState<Alarm[]>([]);
  const [stats, setStats] = useState<AlarmStats | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [page, statistics] = await Promise.all([
        api.alarms.list(false, 100),
        api.alarms.stats(),
      ]);
      setHistory(page.items);
      setStats(statistics);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  // O histórico é uma consulta pontual; o número de alarmes abertos muda por
  // WebSocket, então recarregamos quando ele mudar.
  useEffect(() => {
    void load();
  }, [alarms.length, load]);

  return (
    <>
      <div className="page-header">
        <div>
          <h1>Alarmes</h1>
          <p>Motor de regras com deduplicação, escalonamento e histerese</p>
        </div>
        <button type="button" className="btn" onClick={() => void load()}>
          Atualizar histórico
        </button>
      </div>

      <div className="grid-2">
        <Panel title="Abertos agora" subtitle={`${alarms.length} alarme(s)`}>
          <AlarmList alarms={alarms} />
        </Panel>

        <div className="stack">
          <Panel title="Distribuição por severidade">
            {stats && stats.total_active > 0 ? (
              <table className="table">
                <tbody>
                  {Object.entries(stats.by_severity).map(([severity, count]) => (
                    <tr key={severity}>
                      <td>
                        <span className={`badge sev-${severity}`}>
                          {SEVERITY_LABEL[severity as keyof typeof SEVERITY_LABEL] ?? severity}
                        </span>
                      </td>
                      <td className="num">{count}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <EmptyState>Sem alarmes abertos.</EmptyState>
            )}
          </Panel>

          <Panel title="Por tipo de ocorrência">
            {stats && Object.keys(stats.by_code).length > 0 ? (
              <table className="table">
                <tbody>
                  {Object.entries(stats.by_code)
                    .sort((a, b) => b[1] - a[1])
                    .map(([code, count]) => (
                      <tr key={code}>
                        <td>{ALARM_CODE_LABEL[code] ?? code}</td>
                        <td className="num">{count}</td>
                      </tr>
                    ))}
                </tbody>
              </table>
            ) : (
              <EmptyState>Nenhuma ocorrência ativa.</EmptyState>
            )}
          </Panel>
        </div>
      </div>

      <div style={{ marginTop: 16 }}>
        <Panel title="Histórico" subtitle="Últimos 100 registros, incluindo resolvidos">
          {loading ? (
            <EmptyState>Carregando…</EmptyState>
          ) : history.length === 0 ? (
            <EmptyState>Nenhum alarme registrado ainda.</EmptyState>
          ) : (
            <div className="table-scroll">
              <table className="table">
                <thead>
                  <tr>
                    <th>Máquina</th>
                    <th>Ocorrência</th>
                    <th>Severidade</th>
                    <th>Situação</th>
                    <th className="num">Medido</th>
                    <th className="num">Limite</th>
                    <th>Disparo</th>
                    <th>Resolução</th>
                  </tr>
                </thead>
                <tbody>
                  {history.map((alarm) => (
                    <tr key={alarm.id}>
                      <td className="code">{alarm.machine_code ?? alarm.machine_id}</td>
                      <td>{ALARM_CODE_LABEL[alarm.code] ?? alarm.code}</td>
                      <td>
                        <span className={`badge sev-${alarm.severity}`}>
                          {SEVERITY_LABEL[alarm.severity]}
                        </span>
                      </td>
                      <td>
                        <span className={`badge st-${alarm.status}`}>{alarm.status}</span>
                      </td>
                      <td className="num">{fmt.num(alarm.measured_value, 2)}</td>
                      <td className="num">{fmt.num(alarm.threshold, 2)}</td>
                      <td>{fmt.dateTime(alarm.triggered_at)}</td>
                      <td>{alarm.resolved_at ? fmt.dateTime(alarm.resolved_at) : '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Panel>
      </div>
    </>
  );
}
