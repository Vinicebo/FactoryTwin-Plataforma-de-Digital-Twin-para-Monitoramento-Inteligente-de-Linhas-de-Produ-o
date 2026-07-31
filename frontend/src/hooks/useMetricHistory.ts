/** Buffer em memória das últimas leituras de uma métrica, por máquina.
 *
 * O gráfico ao vivo precisa de uma janela deslizante; guardá-la no cliente
 * evita uma chamada REST a cada tick do simulador.
 */

import { useEffect, useRef, useState } from 'react';

import type { MachineLive } from '../types';

export type MetricKey = 'temperature' | 'speed' | 'efficiency' | 'energy' | 'vibration' | 'pressure';

export interface HistoryPoint {
  ts: number;
  label: string;
  value: number;
}

export function useMetricHistory(
  machine: MachineLive | undefined,
  metric: MetricKey,
  maxPoints = 60,
): HistoryPoint[] {
  const [points, setPoints] = useState<HistoryPoint[]>([]);
  // Trocar de máquina ou de métrica precisa zerar o buffer, senão o gráfico
  // mistura séries de grandezas diferentes.
  const seriesKey = `${machine?.id ?? 'none'}:${metric}`;
  const keyRef = useRef(seriesKey);

  useEffect(() => {
    if (keyRef.current !== seriesKey) {
      keyRef.current = seriesKey;
      setPoints([]);
    }
  }, [seriesKey]);

  const value = machine ? machine[metric] : null;
  const readingAt = machine?.last_reading_at ?? null;

  useEffect(() => {
    if (value === null || value === undefined || !readingAt) return;

    const ts = new Date(readingAt).getTime();
    setPoints((current) => {
      // O mesmo timestamp pode chegar de re-renders; não duplica pontos.
      if (current.length > 0 && current[current.length - 1].ts === ts) return current;

      const next = [
        ...current,
        {
          ts,
          label: new Date(ts).toLocaleTimeString('pt-BR', {
            minute: '2-digit',
            second: '2-digit',
          }),
          value,
        },
      ];
      return next.length > maxPoints ? next.slice(next.length - maxPoints) : next;
    });
  }, [value, readingAt, maxPoints]);

  return points;
}
