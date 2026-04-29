import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  EMPTY_SNAPSHOT,
  EMPTY_INDICATORS,
  type DecisionData,
  type FeedStatus,
  type KlineData,
  type TradingSnapshot,
  type WsMessage,
} from '../types';

const HEARTBEAT_INTERVAL_MS = 15000;
const STALE_THRESHOLD_MS = 45000;
const WATCHDOG_INTERVAL_MS = 10000;
const MAX_BACKOFF_MS = 20000;
const BASE_BACKOFF_MS = 1200;
const MAX_LOGS = 500;
const MAX_EXECUTIONS = 500;
const MAX_DECISIONS = 1000;
const MAX_KLINES = 2000;

function withLatestKline(klines: KlineData[], incoming: KlineData): KlineData[] {
  const last = klines[klines.length - 1];
  if (!last) {
    return [incoming];
  }

  const incomingTime = new Date(incoming.time).getTime();
  const lastTime = new Date(last.time).getTime();

  // 相同时间戳 - 替换最后一根
  if (incomingTime === lastTime) {
    return [...klines.slice(0, -1), incoming];
  }

  // 新K线时间更早（历史数据补齐）- 去重合并
  if (incomingTime < lastTime) {
    const map = new Map<string, KlineData>();
    for (const item of klines) {
      map.set(item.time, item);
    }
    map.set(incoming.time, incoming);
    return Array.from(map.values())
      .sort((a, b) => new Date(a.time).getTime() - new Date(b.time).getTime())
      .slice(-MAX_KLINES);
  }

  // 新K线时间更晚 - 正常追加
  return [...klines, incoming].slice(-MAX_KLINES);
}

// 去重并排序K线数据
function dedupeAndSortKlines(klines: KlineData[]): KlineData[] {
  if (!klines || klines.length === 0) {
    return [];
  }

  const map = new Map<string, KlineData>();
  for (const item of klines) {
    map.set(item.time, item);
  }

  return Array.from(map.values())
    .sort((a, b) => new Date(a.time).getTime() - new Date(b.time).getTime())
    .slice(-MAX_KLINES);
}

function stableString(errorLike: unknown): string {
  if (errorLike instanceof Error) {
    return errorLike.message;
  }
  return typeof errorLike === 'string' ? errorLike : 'Unknown error';
}

function getWsUrl(): string {
  const explicit = import.meta.env.VITE_WS_URL;
  if (explicit) {
    return explicit;
  }

  if (import.meta.env.DEV) {
    return 'ws://localhost:8000/ws';
  }

  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${protocol}//${window.location.hostname}:8000/ws`;
}

export function useTradingFeed() {
  const [snapshot, setSnapshot] = useState<TradingSnapshot>(EMPTY_SNAPSHOT);
  const [status, setStatus] = useState<FeedStatus>({
    state: 'connecting',
    reconnectAttempt: 0,
    lastMessageAt: null,
    error: null,
  });

  const wsRef = useRef<WebSocket | null>(null);
  const shouldRunRef = useRef(true);
  const reconnectTimerRef = useRef<number | null>(null);
  const heartbeatTimerRef = useRef<number | null>(null);
  const watchdogTimerRef = useRef<number | null>(null);
  const reconnectAttemptsRef = useRef(0);
  const lastMessageAtRef = useRef<number | null>(null);
  const connectingRef = useRef(false);

  const wsUrl = useMemo(() => getWsUrl(), []);

  const clearTimer = (timerRef: { current: number | null }) => {
    if (timerRef.current !== null) {
      window.clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  };

  const clearIntervals = useCallback(() => {
    if (heartbeatTimerRef.current !== null) {
      window.clearInterval(heartbeatTimerRef.current);
      heartbeatTimerRef.current = null;
    }
    if (watchdogTimerRef.current !== null) {
      window.clearInterval(watchdogTimerRef.current);
      watchdogTimerRef.current = null;
    }
  }, []);

  const hardClose = useCallback(() => {
    clearIntervals();
    connectingRef.current = false;

    const socket = wsRef.current;
    if (!socket) {
      return;
    }

    // Avoid closing a CONNECTING socket immediately in dev, which triggers noisy
    // "closed before the connection is established" browser warnings.
    if (socket.readyState === WebSocket.CONNECTING) {
      socket.onmessage = null;
      socket.onerror = null;
      socket.onclose = null;
      socket.onopen = () => {
        socket.close(1000, 'teardown');
      };
      wsRef.current = null;
      return;
    }

    socket.onopen = null;
    socket.onclose = null;
    socket.onmessage = null;
    socket.onerror = null;
    if (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CLOSING) {
      socket.close(1000, 'teardown');
    }
    wsRef.current = null;
  }, [clearIntervals]);

  const applyMessage = useCallback((message: WsMessage) => {
    if (message.type === 'heartbeat') {
      return;
    }

    setSnapshot((prev) => {
      switch (message.type) {
        case 'init':
          return {
            klines: dedupeAndSortKlines(message.data.klines ?? []),
            indicators: message.data.indicators ?? EMPTY_INDICATORS,
            decisions: (message.data.decisions ?? []).slice(-MAX_DECISIONS),
            logs: (message.data.logs ?? []).slice(-MAX_LOGS),
            executions: (message.data.executions ?? []).slice(-MAX_EXECUTIONS),
            phaseStatus: message.data.phase_status ?? { current: '' },
            agentReports: message.data.agent_reports ?? {},
          };
        case 'kline':
          return { ...prev, klines: withLatestKline(prev.klines, message.data) };
        case 'decision': {
          const nextDecisions = [...prev.decisions, message.data].slice(-MAX_DECISIONS);
          return { ...prev, decisions: nextDecisions };
        }
        case 'log': {
          const nextLogs = [...prev.logs, message.data].slice(-MAX_LOGS);
          return { ...prev, logs: nextLogs };
        }
        case 'execution': {
          const nextExecutions = [...prev.executions, message.data].slice(-MAX_EXECUTIONS);
          return { ...prev, executions: nextExecutions };
        }
        case 'phase': {
          const nextPhaseStatus = {
            ...prev.phaseStatus,
            current: message.data.phase,
            [message.data.phase]: {
              status: message.data.status,
              duration: message.data.duration,
            },
          };
          return { ...prev, phaseStatus: nextPhaseStatus };
        }
        case 'report': {
          const phaseBucket = prev.agentReports[message.data.phase] ?? {};
          return {
            ...prev,
            agentReports: {
              ...prev.agentReports,
              [message.data.phase]: {
                ...phaseBucket,
                [message.data.agent]: message.data.content,
              },
            },
          };
        }
        case 'decision_tree':
          return prev;
        case 'reset':
          return {
            ...EMPTY_SNAPSHOT,
            indicators: prev.indicators,
          };
        default:
          return prev;
      }
    });
  }, []);

  const scheduleReconnect = useCallback(() => {
    if (!shouldRunRef.current) {
      return;
    }

    clearTimer(reconnectTimerRef);
    reconnectAttemptsRef.current += 1;

    const power = Math.min(reconnectAttemptsRef.current - 1, 6);
    const baseDelay = Math.min(BASE_BACKOFF_MS * 2 ** power, MAX_BACKOFF_MS);
    const jitter = Math.floor(Math.random() * 700);
    const delay = baseDelay + jitter;

    setStatus((prev) => ({
      ...prev,
      state: navigator.onLine ? 'reconnecting' : 'offline',
      reconnectAttempt: reconnectAttemptsRef.current,
    }));

    reconnectTimerRef.current = window.setTimeout(() => {
      if (!navigator.onLine) {
        scheduleReconnect();
        return;
      }
      void connect();
    }, delay);
  }, []);

  const connect = useCallback(async () => {
    if (!shouldRunRef.current || connectingRef.current) {
      return;
    }

    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      return;
    }

    clearTimer(reconnectTimerRef);
    connectingRef.current = true;
    setStatus((prev) => ({
      ...prev,
      state: reconnectAttemptsRef.current > 0 ? 'reconnecting' : 'connecting',
      error: null,
    }));

    try {
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        connectingRef.current = false;
        reconnectAttemptsRef.current = 0;
        lastMessageAtRef.current = Date.now();

        setStatus((prev) => ({
          ...prev,
          state: 'connected',
          reconnectAttempt: 0,
          error: null,
          lastMessageAt: lastMessageAtRef.current,
        }));

        clearIntervals();
        heartbeatTimerRef.current = window.setInterval(() => {
          if (wsRef.current?.readyState === WebSocket.OPEN) {
            wsRef.current.send('ping');
          }
        }, HEARTBEAT_INTERVAL_MS);

        watchdogTimerRef.current = window.setInterval(() => {
          const lastAt = lastMessageAtRef.current;
          if (!lastAt) {
            return;
          }
          const age = Date.now() - lastAt;
          if (age > STALE_THRESHOLD_MS) {
            hardClose();
            scheduleReconnect();
          }
        }, WATCHDOG_INTERVAL_MS);
      };

      ws.onmessage = (event) => {
        lastMessageAtRef.current = Date.now();
        setStatus((prev) => ({ ...prev, lastMessageAt: lastMessageAtRef.current }));

        if (typeof event.data === 'string' && (event.data === 'pong' || event.data === 'ping')) {
          return;
        }

        try {
          const payload = JSON.parse(event.data) as WsMessage;
          applyMessage(payload);
        } catch {
          // Ignore malformed payloads to keep UI alive.
        }
      };

      ws.onerror = () => {
        setStatus((prev) => ({ ...prev, state: 'error', error: 'WebSocket error' }));
      };

      ws.onclose = () => {
        connectingRef.current = false;
        clearIntervals();
        wsRef.current = null;

        if (!shouldRunRef.current) {
          setStatus((prev) => ({ ...prev, state: 'offline' }));
          return;
        }

        scheduleReconnect();
      };
    } catch (error) {
      connectingRef.current = false;
      setStatus((prev) => ({
        ...prev,
        state: 'error',
        error: stableString(error),
      }));
      scheduleReconnect();
    }
  }, [applyMessage, clearIntervals, hardClose, scheduleReconnect, wsUrl]);

  useEffect(() => {
    shouldRunRef.current = true;
    void connect();

    const handleVisibility = () => {
      if (document.visibilityState === 'visible' && wsRef.current?.readyState !== WebSocket.OPEN) {
        void connect();
      }
    };

    const handleOnline = () => {
      setStatus((prev) => ({ ...prev, state: 'reconnecting', error: null }));
      void connect();
    };

    const handleOffline = () => {
      setStatus((prev) => ({ ...prev, state: 'offline' }));
    };

    document.addEventListener('visibilitychange', handleVisibility);
    window.addEventListener('online', handleOnline);
    window.addEventListener('offline', handleOffline);

    return () => {
      shouldRunRef.current = false;
      document.removeEventListener('visibilitychange', handleVisibility);
      window.removeEventListener('online', handleOnline);
      window.removeEventListener('offline', handleOffline);
      clearTimer(reconnectTimerRef);
      hardClose();
    };
  }, [connect, hardClose]);

  const reconnectNow = useCallback(() => {
    reconnectAttemptsRef.current = 0;
    hardClose();
    void connect();
  }, [connect, hardClose]);

  const latestDecision: DecisionData | undefined = snapshot.decisions[snapshot.decisions.length - 1];

  return {
    snapshot,
    status,
    latestDecision,
    reconnectNow,
  };
}
