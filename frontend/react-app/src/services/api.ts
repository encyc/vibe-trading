import type { BarTrace, SystemStatus } from '../types';

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