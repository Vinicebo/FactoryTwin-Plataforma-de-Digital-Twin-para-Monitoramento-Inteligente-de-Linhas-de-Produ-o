/** Canal WebSocket de tempo real (Fase 6).
 *
 * Mantém o estado do dashboard inteiro — máquinas, alarmes e resumo da linha —
 * a partir de um único socket, aplicando cada evento sobre o snapshot inicial.
 * Não há polling: o backend empurra tudo.
 */

import { useCallback, useEffect, useRef, useState } from 'react';

import { websocketUrl } from '../api/client';
import type {
  Alarm,
  LineSummary,
  MachineLive,
  MachineStatusPayload,
  RealtimeEvent,
  SnapshotPayload,
  TelemetryEvent,
} from '../types';

export type ConnectionState = 'connecting' | 'open' | 'closed';

interface RealtimeState {
  connection: ConnectionState;
  machines: MachineLive[];
  alarms: Alarm[];
  summary: LineSummary | null;
  /** Última telemetria por máquina — alimenta os mini-gráficos ao vivo. */
  lastEventAt: string | null;
  eventCount: number;
}

/** Backoff exponencial limitado, para não martelar um backend fora do ar. */
const RECONNECT_BASE_MS = 1000;
const RECONNECT_MAX_MS = 15000;
/** Alarmes fechados somem da lista; mantemos um teto para a memória não crescer. */
const MAX_ALARMS = 200;

export function useRealtime(token: string | null): RealtimeState {
  const [connection, setConnection] = useState<ConnectionState>('closed');
  const [machines, setMachines] = useState<MachineLive[]>([]);
  const [alarms, setAlarms] = useState<Alarm[]>([]);
  const [summary, setSummary] = useState<LineSummary | null>(null);
  const [lastEventAt, setLastEventAt] = useState<string | null>(null);
  const [eventCount, setEventCount] = useState(0);

  const socketRef = useRef<WebSocket | null>(null);
  const reconnectRef = useRef<number | null>(null);
  const attemptsRef = useRef(0);
  // Evita reconectar depois que o componente desmontou ou o usuário deslogou.
  const activeRef = useRef(true);

  const applyTelemetry = useCallback((batch: TelemetryEvent[]) => {
    setMachines((current) => {
      const byId = new Map(batch.map((item) => [item.machine_id, item]));
      return current.map((machine) => {
        const update = byId.get(machine.id);
        if (!update) return machine;
        return {
          ...machine,
          status: update.status,
          temperature: update.temperature,
          speed: update.speed,
          efficiency: update.efficiency,
          energy: update.energy,
          vibration: update.vibration,
          pressure: update.pressure,
          last_reading_at: update.ts,
          is_anomaly: update.is_anomaly,
        };
      });
    });
  }, []);

  const handleEvent = useCallback(
    (event: RealtimeEvent) => {
      setLastEventAt(event.ts);
      setEventCount((n) => n + 1);

      switch (event.type) {
        case 'snapshot': {
          const payload = event.payload as SnapshotPayload;
          setMachines(payload.machines);
          setAlarms(payload.alarms);
          setSummary(payload.summary);
          break;
        }
        case 'telemetry':
          applyTelemetry(event.payload as TelemetryEvent[]);
          break;

        case 'line_summary':
          setSummary(event.payload as LineSummary);
          break;

        case 'machine_status': {
          const payload = event.payload as MachineStatusPayload;
          setMachines((current) =>
            current.map((machine) =>
              machine.id === payload.machine_id ? { ...machine, status: payload.to } : machine,
            ),
          );
          break;
        }

        case 'alarm_raised':
        case 'alarm_updated': {
          const alarm = event.payload as Alarm;
          setAlarms((current) => {
            const rest = current.filter((item) => item.id !== alarm.id);
            return [alarm, ...rest].slice(0, MAX_ALARMS);
          });
          setMachines((current) =>
            current.map((machine) =>
              machine.id === alarm.machine_id
                ? { ...machine, active_alarms: machine.active_alarms + 1 }
                : machine,
            ),
          );
          break;
        }

        case 'alarm_resolved': {
          const alarm = event.payload as Alarm;
          setAlarms((current) => current.filter((item) => item.id !== alarm.id));
          setMachines((current) =>
            current.map((machine) =>
              machine.id === alarm.machine_id
                ? { ...machine, active_alarms: Math.max(0, machine.active_alarms - 1) }
                : machine,
            ),
          );
          break;
        }

        default:
          break;
      }
    },
    [applyTelemetry],
  );

  useEffect(() => {
    activeRef.current = true;

    if (!token) {
      setConnection('closed');
      return;
    }

    const connect = () => {
      if (!activeRef.current) return;
      setConnection('connecting');

      const socket = new WebSocket(websocketUrl(token));
      socketRef.current = socket;

      socket.onopen = () => {
        attemptsRef.current = 0;
        setConnection('open');
      };

      socket.onmessage = (message) => {
        if (message.data === 'pong') return;
        try {
          handleEvent(JSON.parse(message.data) as RealtimeEvent);
        } catch {
          // Mensagem malformada não pode derrubar o dashboard.
        }
      };

      socket.onclose = () => {
        setConnection('closed');
        if (!activeRef.current) return;

        const delay = Math.min(
          RECONNECT_BASE_MS * 2 ** attemptsRef.current,
          RECONNECT_MAX_MS,
        );
        attemptsRef.current += 1;
        reconnectRef.current = window.setTimeout(connect, delay);
      };

      socket.onerror = () => socket.close();
    };

    connect();

    return () => {
      activeRef.current = false;
      if (reconnectRef.current !== null) window.clearTimeout(reconnectRef.current);
      socketRef.current?.close();
      socketRef.current = null;
    };
  }, [token, handleEvent]);

  return { connection, machines, alarms, summary, lastEventAt, eventCount };
}
