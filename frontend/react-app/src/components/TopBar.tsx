import { RefreshCw } from 'lucide-react';
import { formatCompact, formatLatency, formatPrice } from '../lib/format';
import type { ConnectionState, DecisionData, FeedStatus, KlineData } from '../types';

interface TopBarProps {
  symbol: string;
  klines: KlineData[];
  latestDecision?: DecisionData;
  status: FeedStatus;
  onReconnect: () => void;
}

const connectionLabel: Record<ConnectionState, string> = {
  connecting: 'CONNECTING',
  connected: 'LIVE',
  reconnecting: 'RECONNECTING',
  offline: 'OFFLINE',
  error: 'ERROR',
};

export function TopBar({ symbol, klines, latestDecision, status, onReconnect }: TopBarProps) {
  const latestKline = klines[klines.length - 1];
  const previousClose = klines[klines.length - 2]?.close;
  const delta = latestKline && previousClose ? latestKline.close - previousClose : 0;
  const deltaPct = latestKline && previousClose ? (delta / previousClose) * 100 : 0;
  const ticker = [
    { label: symbol, value: latestKline ? `$${formatPrice(latestKline.close)}` : '--', delta: deltaPct },
    { label: 'VOL', value: latestKline ? formatCompact(latestKline.volume) : '--', delta: 0 },
    { label: 'BARS', value: String(klines.length), delta: 0 },
    { label: 'LLM MODE', value: 'PAPER', delta: 0 },
    { label: 'LAST DECISION', value: latestDecision?.decision ?? 'N/A', delta: 0 },
  ];

  return (
    <header className="topbar">
      <div className="topbar-main">
        <div className="brand-block">
          <div className="brand-mark" aria-hidden="true">V</div>
          <div>
            <p className="brand-title">Vibe Trading</p>
            <p className="brand-subtitle">Multi-Agent Crypto Arena</p>
          </div>
        </div>

        <nav className="top-nav" aria-label="Primary">
          <span>Leaderboard</span>
          <span>Research</span>
          <span>Agent Logs</span>
          <span>Paper Trade</span>
        </nav>

        <div className="meta-block">
          <div className={`connection-pill ${status.state}`}>
            <span className="dot" />
            <span>{connectionLabel[status.state]}</span>
          </div>
          <div className="meta-stat">Lag {formatLatency(status.lastMessageAt)}</div>
          <button className="reconnect-btn" onClick={onReconnect} type="button" title="Reconnect WebSocket">
            <RefreshCw size={14} />
            <span>Reconnect</span>
          </button>
        </div>
      </div>

      <div className="ticker-ribbon" aria-label="Market ticker">
        {ticker.map((item) => (
          <div key={item.label} className="ticker-cell">
            <span>{item.label}</span>
            <strong>{item.value}</strong>
            {item.delta !== 0 && (
              <em className={item.delta >= 0 ? 'up' : 'down'}>
                {item.delta >= 0 ? '+' : ''}{item.delta.toFixed(2)}%
              </em>
            )}
          </div>
        ))}
      </div>
    </header>
  );
}
