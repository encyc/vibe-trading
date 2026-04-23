export function formatPrice(value: number): string {
  if (!Number.isFinite(value)) {
    return '--';
  }
  return value.toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

export function formatCompact(value: number): string {
  if (!Number.isFinite(value)) {
    return '--';
  }
  return new Intl.NumberFormat(undefined, {
    notation: 'compact',
    maximumFractionDigits: 2,
  }).format(value);
}

export function formatTime(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) {
    return '--:--:--';
  }
  return date.toLocaleTimeString(undefined, {
    hour12: false,
  });
}

export function formatMinute(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) {
    return '--:--';
  }
  return date.toLocaleTimeString(undefined, {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  });
}

export function formatLatency(lastMessageAt: number | null): string {
  if (!lastMessageAt) {
    return '--';
  }
  const diffMs = Date.now() - lastMessageAt;
  if (diffMs < 1000) {
    return `${diffMs}ms`;
  }
  return `${(diffMs / 1000).toFixed(1)}s`;
}
