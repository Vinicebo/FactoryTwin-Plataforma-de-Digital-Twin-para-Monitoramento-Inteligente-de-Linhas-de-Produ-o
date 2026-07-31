/** Tabela de máquinas com telemetria ao vivo e comandos do operador. */

import { useState } from 'react';

import { api } from '../api/client';
import { useAuth } from '../auth/AuthContext';
import { Panel, STATUS_LABEL, StatusDot, fmt } from '../components/common';
import type { MachineLive, MachineStatus } from '../types';

const COMMANDABLE: MachineStatus[] = ['RUNNING', 'IDLE', 'MAINTENANCE', 'OFFLINE'];

export function Machines({ machines }: { machines: MachineLive[] }) {
  const { can } = useAuth();
  const [busyId, setBusyId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const changeStatus = async (machine: MachineLive, status: MachineStatus) => {
    setBusyId(machine.id);
    setError(null);
    try {
      await api.machines.setStatus(machine.id, status, 'Comando manual pelo painel');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Falha ao comandar a máquina');
    } finally {
      setBusyId(null);
    }
  };

  const ordered = [...machines].sort((a, b) => a.sequence - b.sequence);

  return (
    <>
      <div className="page-header">
        <div>
          <h1>Máquinas</h1>
          <p>Telemetria ao vivo de cada estação, na ordem do fluxo produtivo</p>
        </div>
      </div>

      {error && <div className="error-box">{error}</div>}

      <Panel title="Estações da linha" subtitle={`${ordered.length} equipamentos`}>
        <div className="table-scroll">
          <table className="table">
            <thead>
              <tr>
                <th>#</th>
                <th>Código</th>
                <th>Máquina</th>
                <th>Estado</th>
                <th className="num">Temp. (°C)</th>
                <th className="num">Vel.</th>
                <th className="num">Efic. (%)</th>
                <th className="num">Energia (kW)</th>
                <th className="num">Vibr. (mm/s)</th>
                <th className="num">Alarmes</th>
                {can('OPERATOR') && <th>Comando</th>}
              </tr>
            </thead>
            <tbody>
              {ordered.map((machine) => (
                <tr key={machine.id}>
                  <td className="num">{machine.sequence}</td>
                  <td className="code">{machine.code}</td>
                  <td>
                    {machine.name}
                    {machine.is_anomaly && <span className="anomaly-flag"> ⚡</span>}
                  </td>
                  <td>
                    <span className="row" style={{ gap: 6 }}>
                      <StatusDot status={machine.status} />
                      {STATUS_LABEL[machine.status]}
                    </span>
                  </td>
                  <td className="num">{fmt.num(machine.temperature)}</td>
                  <td className="num">{fmt.num(machine.speed)}</td>
                  <td className="num">{fmt.num(machine.efficiency)}</td>
                  <td className="num">{fmt.num(machine.energy)}</td>
                  <td className="num">{fmt.num(machine.vibration, 2)}</td>
                  <td className="num">
                    {machine.active_alarms > 0 ? (
                      <span className={`badge sev-${machine.highest_severity ?? 'WARNING'}`}>
                        {machine.active_alarms}
                      </span>
                    ) : (
                      '—'
                    )}
                  </td>
                  {can('OPERATOR') && (
                    <td>
                      <select
                        value={machine.status}
                        disabled={busyId === machine.id}
                        onChange={(e) => changeStatus(machine, e.target.value as MachineStatus)}
                        style={{
                          background: 'var(--bg)',
                          color: 'var(--text)',
                          border: '1px solid var(--border-strong)',
                          borderRadius: 6,
                          padding: '3px 6px',
                          fontSize: 12,
                        }}
                      >
                        {/* O estado atual pode não ser comandável (ex.: FAULT),
                            então garantimos que ele apareça na lista. */}
                        {Array.from(new Set([machine.status, ...COMMANDABLE])).map((status) => (
                          <option key={status} value={status}>
                            {STATUS_LABEL[status]}
                          </option>
                        ))}
                      </select>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
    </>
  );
}
