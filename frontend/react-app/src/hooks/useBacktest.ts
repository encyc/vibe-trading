import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  createBacktestTask,
  getBacktestProgressWsUrl,
  getBacktestResultUrl,
  getBacktestTask,
  getSystemStatus,
  resetMonitorData,
} from '../services/api';
import type {
  BacktestCreateRequest,
  BacktestProgress,
  BacktestTask,
  BacktestTaskStatus,
  SystemStatus,
} from '../types';

const POLL_INTERVAL_MS = 2000;
const STATUS_REFRESH_MS = 5000;

function defaultStartDate(): string {
  const date = new Date();
  date.setDate(date.getDate() - 60);
  return date.toISOString().slice(0, 10);
}

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

function canPoll(status?: BacktestTaskStatus): boolean {
  return status === 'pending' || status === 'running';
}

export function useBacktest() {
  const [form, setForm] = useState<BacktestCreateRequest>({
    symbol: 'BTCUSDT',
    interval: '4h',
    start_time: defaultStartDate(),
    end_time: today(),
    initial_balance: 10000,
    llm_mode: 'simulated',
  });

  const [task, setTask] = useState<BacktestTask | null>(null);
  const [progress, setProgress] = useState<BacktestProgress | null>(null);
  const [monitorStatus, setMonitorStatus] = useState<SystemStatus | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isResetting, setIsResetting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const pollTimerRef = useRef<number | null>(null);
  const wsRef = useRef<WebSocket | null>(null);

  const taskId = task?.task_id ?? null;

  const setField = useCallback(<K extends keyof BacktestCreateRequest>(key: K, value: BacktestCreateRequest[K]) => {
    setForm((prev) => ({ ...prev, [key]: value }));
  }, []);

  const refreshMonitorStatus = useCallback(async () => {
    try {
      const status = await getSystemStatus();
      setMonitorStatus(status);
    } catch {
      // Monitor backend might be temporarily unavailable.
    }
  }, []);

  useEffect(() => {
    void refreshMonitorStatus();
  }, [refreshMonitorStatus]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      void refreshMonitorStatus();
    }, STATUS_REFRESH_MS);

    return () => {
      window.clearInterval(timer);
    };
  }, [refreshMonitorStatus]);

  const runBacktest = useCallback(async () => {
    setError(null);
    setIsSubmitting(true);

    try {
      const created = await createBacktestTask(form);
      setTask({
        task_id: created.task_id,
        symbol: form.symbol,
        interval: form.interval,
        start_time: form.start_time,
        end_time: form.end_time,
        llm_mode: form.llm_mode,
        status: 'pending',
        current_kline: 0,
        total_klines: 0,
        current_equity: form.initial_balance,
        total_trades: 0,
        llm_calls: 0,
        llm_cache_hits: 0,
        created_at: new Date().toISOString(),
      });
    } catch (runError) {
      setError(runError instanceof Error ? runError.message : '回测启动失败');
    } finally {
      setIsSubmitting(false);
    }
  }, [form]);

  const resetData = useCallback(async () => {
    setIsResetting(true);
    setError(null);
    try {
      await resetMonitorData();
      await refreshMonitorStatus();
    } catch (resetError) {
      setError(resetError instanceof Error ? resetError.message : '重置失败');
    } finally {
      setIsResetting(false);
    }
  }, [refreshMonitorStatus]);

  useEffect(() => {
    if (!taskId || !canPoll(task?.status)) {
      if (pollTimerRef.current !== null) {
        window.clearInterval(pollTimerRef.current);
        pollTimerRef.current = null;
      }
      return;
    }

    const fetchTask = async () => {
      try {
        const latest = await getBacktestTask(taskId);
        setTask(latest);
      } catch {
        // task endpoint might not be available on monitoring-only backend.
      }
    };

    void fetchTask();
    pollTimerRef.current = window.setInterval(fetchTask, POLL_INTERVAL_MS);

    return () => {
      if (pollTimerRef.current !== null) {
        window.clearInterval(pollTimerRef.current);
        pollTimerRef.current = null;
      }
    };
  }, [task?.status, taskId]);

  useEffect(() => {
    if (!taskId) {
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
      return;
    }

    const ws = new WebSocket(getBacktestProgressWsUrl(taskId));
    wsRef.current = ws;

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data) as BacktestProgress;
        if (data.task_id === taskId) {
          setProgress(data);
          setTask((prev) => {
            if (!prev) {
              return prev;
            }
            return {
              ...prev,
              status: data.status,
              current_kline: data.current_kline,
              total_klines: data.total_klines,
              current_equity: data.current_equity,
              total_trades: data.total_trades,
              llm_calls: data.llm_calls,
              llm_cache_hits: data.llm_cache_hits,
            };
          });
        }
      } catch {
        // ignore malformed progress payload
      }
    };

    ws.onerror = () => {
      // not all backend modes expose progress ws endpoint
    };

    return () => {
      ws.close();
      if (wsRef.current === ws) {
        wsRef.current = null;
      }
    };
  }, [taskId]);

  const resultUrl = useMemo(() => (taskId ? getBacktestResultUrl(taskId) : null), [taskId]);

  return {
    form,
    setField,
    runBacktest,
    resetData,
    isSubmitting,
    isResetting,
    task,
    taskId,
    progress,
    monitorStatus,
    error,
    resultUrl,
    refreshMonitorStatus,
  };
}

export type UseBacktestResult = ReturnType<typeof useBacktest>;
