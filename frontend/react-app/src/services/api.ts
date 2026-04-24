import type { BacktestCreateRequest, BacktestTask, BarTrace, SystemStatus } from '../types';

function stripTrailingSlash(input: string): string {
  return input.replace(/\/$/, '');
}

export function getCoreApiBaseUrl(): string {
  const configured = import.meta.env.VITE_API_BASE_URL;
  if (configured) {
    return stripTrailingSlash(configured);
  }

  if (import.meta.env.DEV) {
    return 'http://localhost:8000';
  }

  return `${window.location.protocol}//${window.location.hostname}:8000`;
}

export function getBacktestApiBaseUrl(): string {
  const configured = import.meta.env.VITE_BACKTEST_API_URL;
  if (configured) {
    return stripTrailingSlash(configured);
  }

  if (import.meta.env.DEV) {
    return 'http://localhost:8001';
  }

  return `${window.location.protocol}//${window.location.hostname}:8001`;
}

async function requestJson<T>(input: RequestInfo | URL, init?: RequestInit): Promise<T> {
  const response = await fetch(input, init);
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `Request failed: ${response.status}`);
  }
  return (await response.json()) as T;
}

export async function getSystemStatus(): Promise<SystemStatus> {
  return requestJson<SystemStatus>(`${getCoreApiBaseUrl()}/api/status`);
}

export async function resetMonitorData(): Promise<{ success: boolean }> {
  return requestJson<{ success: boolean }>(`${getCoreApiBaseUrl()}/api/reset`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  });
}

export async function createBacktestTask(payload: BacktestCreateRequest): Promise<{ task_id: string; status: string }> {
  return requestJson<{ task_id: string; status: string }>(`${getBacktestApiBaseUrl()}/api/backtest`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
}

export async function getBacktestTask(taskId: string): Promise<BacktestTask> {
  return requestJson<BacktestTask>(`${getBacktestApiBaseUrl()}/api/backtest/${taskId}`);
}

export function getBacktestResultUrl(taskId: string): string {
  return `${getBacktestApiBaseUrl()}/results/${taskId}`;
}

export function getBacktestProgressWsUrl(taskId: string): string {
  const base = getBacktestApiBaseUrl();
  const wsBase = base.startsWith('https://')
    ? base.replace('https://', 'wss://')
    : base.replace('http://', 'ws://');

  return `${wsBase}/ws/progress/${taskId}`;
}

export async function getBarTrace(openTimeMs: number, symbol: string, interval: string): Promise<BarTrace | null> {
  const params = new URLSearchParams({ symbol, interval });
  const result = await requestJson<{ found: boolean; bar: BarTrace | null }>(
    `${getCoreApiBaseUrl()}/api/bar/${openTimeMs}?${params.toString()}`,
  );

  if (!result.found) {
    return null;
  }
  return result.bar;
}
