/** Lista de alarmes abertos, com as ações do operador. */

import { useState } from 'react';

import { api } from '../api/client';
import { useAuth } from '../auth/AuthContext';
import type { Alarm } from '../types';
import { ALARM_CODE_LABEL, EmptyState, SEVERITY_LABEL, fmt } from './common';

interface Props {
  alarms: Alarm[];
  limit?: number;
}

export function AlarmList({ alarms, limit }: Props) {
  const { can } = useAuth();
  // Guarda o id em processamento para desabilitar o botão e evitar duplo clique.
  const [busyId, setBusyId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const visible = limit ? alarms.slice(0, limit) : alarms;

  const act = async (id: number, action: 'ack' | 'resolve') => {
    setBusyId(id);
    setError(null);
    try {
      if (action === 'ack') await api.alarms.acknowledge(id);
      else await api.alarms.resolve(id);
      // A lista é atualizada pelo evento WebSocket correspondente; não
      // mexemos no estado local para não divergir do servidor.
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Falha ao tratar o alarme');
    } finally {
      setBusyId(null);
    }
  };

  if (visible.length === 0) {
    return <EmptyState>Nenhum alarme aberto. Linha operando dentro dos limites.</EmptyState>;
  }

  return (
    <>
      {error && <div className="error-box">{error}</div>}
      <div className="alarm-list">
        {visible.map((alarm) => (
          <article key={alarm.id} className={`alarm-item sev-${alarm.severity}`}>
            <div />
            <div>
              <div className="alarm-meta">
                <span className={`badge sev-${alarm.severity}`}>
                  {SEVERITY_LABEL[alarm.severity]}
                </span>
                <strong>{alarm.machine_code ?? `#${alarm.machine_id}`}</strong>
                <span>{ALARM_CODE_LABEL[alarm.code] ?? alarm.code}</span>
                <span>·</span>
                <span>{fmt.ago(alarm.triggered_at)}</span>
                {alarm.status === 'ACKNOWLEDGED' && (
                  <span className="badge st-ACKNOWLEDGED">Reconhecido</span>
                )}
              </div>
              <div className="alarm-message">{alarm.message}</div>
            </div>
            {can('OPERATOR') && (
              <div className="alarm-actions">
                {alarm.status === 'ACTIVE' && (
                  <button
                    type="button"
                    className="btn btn-sm"
                    disabled={busyId === alarm.id}
                    onClick={() => act(alarm.id, 'ack')}
                  >
                    Reconhecer
                  </button>
                )}
                <button
                  type="button"
                  className="btn btn-sm btn-danger"
                  disabled={busyId === alarm.id}
                  onClick={() => act(alarm.id, 'resolve')}
                >
                  Resolver
                </button>
              </div>
            )}
          </article>
        ))}
      </div>
    </>
  );
}
