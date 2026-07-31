/** Mapa da fábrica: as máquinas posicionadas no chão, em tempo real.
 *
 * As coordenadas vêm de `pos_x`/`pos_y` (plano normalizado 0–100), então
 * reposicionar um equipamento é uma edição de cadastro — não mexe no código.
 */

import type { MachineLive } from '../types';
import { STATUS_LABEL } from './common';

interface Props {
  machines: MachineLive[];
  selectedId: number | null;
  onSelect: (machine: MachineLive) => void;
}

/** Métrica que resume cada tipo de máquina no card do mapa. */
function headline(machine: MachineLive): string {
  switch (machine.machine_type) {
    case 'INJECTOR':
    case 'OVEN':
      return `${machine.temperature?.toFixed(0) ?? '—'} °C`;
    case 'CONVEYOR':
    case 'PACKAGER':
      return `${machine.speed?.toFixed(0) ?? '—'} m/min`;
    case 'ROBOT':
      return `${machine.vibration?.toFixed(1) ?? '—'} mm/s`;
    case 'PALLETIZER':
      return `${machine.energy?.toFixed(1) ?? '—'} kW`;
    default:
      return `${machine.efficiency?.toFixed(0) ?? '—'} %`;
  }
}

export function FactoryMap({ machines, selectedId, onSelect }: Props) {
  const ordered = [...machines].sort((a, b) => a.sequence - b.sequence);

  return (
    <div className="factory-map">
      {/* Linhas de fluxo ligando estações consecutivas. */}
      <svg className="map-flow" viewBox="0 0 100 100" preserveAspectRatio="none">
        {ordered.slice(0, -1).map((machine, index) => {
          const next = ordered[index + 1];
          return (
            <line
              key={machine.id}
              x1={machine.pos_x}
              y1={100 - machine.pos_y}
              x2={next.pos_x}
              y2={100 - next.pos_y}
              stroke="var(--border-strong)"
              strokeWidth="0.35"
              strokeDasharray="1.2 0.8"
              vectorEffect="non-scaling-stroke"
            />
          );
        })}
      </svg>

      {ordered.map((machine) => (
        <button
          key={machine.id}
          type="button"
          className={`map-node st-${machine.status}${
            machine.id === selectedId ? ' selected' : ''
          }`}
          style={{ left: `${machine.pos_x}%`, bottom: `${machine.pos_y}%` }}
          onClick={() => onSelect(machine)}
          title={`${machine.name} — ${STATUS_LABEL[machine.status]}`}
        >
          {machine.active_alarms > 0 && (
            <span className={`map-node-badge sev-${machine.highest_severity ?? 'WARNING'}`}>
              {machine.active_alarms}
            </span>
          )}
          <span className="map-node-code">{machine.code}</span>
          <span className="map-node-metric">{headline(machine)}</span>
          {machine.is_anomaly && <span className="anomaly-flag">⚡ anomalia</span>}
        </button>
      ))}
    </div>
  );
}
