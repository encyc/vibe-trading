import { useEffect, useRef } from 'react';
import { formatTime } from '../lib/format';
import type { LogEntry } from '../types';

interface LogsPanelProps {
  logs: LogEntry[];
}

export function LogsPanel({ logs }: LogsPanelProps) {
  const ref = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!ref.current) {
      return;
    }
    ref.current.scrollTop = ref.current.scrollHeight;
  }, [logs]);

  return (
    <section className="panel logs-panel">
      <div className="panel-head">
        <h2>Runtime Log</h2>
        <span>{logs.length} entries</span>
      </div>
      <div ref={ref} className="log-list">
        {logs.length === 0 && <p className="empty-text">No log data.</p>}
        {logs.map((log, idx) => (
          <p key={`${log.timestamp}-${idx}`} className={`log-line ${log.level}`}>
            <time>{formatTime(log.timestamp)}</time>
            <span className="log-tag">[{log.tag || 'system'}]</span>
            <span>{log.message}</span>
          </p>
        ))}
      </div>
    </section>
  );
}
