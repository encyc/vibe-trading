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

  return (
    <header className="topbar">
      <div className="brand-block">
        <div className="brand-mark" aria-hidden="true" />
        <div>
          <p className="brand-title">Vibe Terminal</p>
          <p className="brand-subtitle">LLM Multi-Agent Trading Cockpit</p>
        </div>
      </div>

      <div className="symbol-block">
        <p className="symbol-name">{symbol}</p>
        <p className="symbol-price">${latestKline ? formatPrice(latestKline.close) : '--'}</p>
        <p className={`symbol-delta ${delta >= 0 ? 'up' : 'down'}`}>
          {delta >= 0 ? '+' : ''}{formatPrice(delta)} ({deltaPct.toFixed(2)}%)
        </p>
      </div>

      <div className="meta-block">
        <div className={`connection-pill ${status.state}`}>
          <span className="dot" />
          <span>{connectionLabel[status.state]}</span>
        </div>
        <div className="meta-stat">Lag {formatLatency(status.lastMessageAt)}</div>
        <div className="meta-stat">Vol {latestKline ? formatCompact(latestKline.volume) : '--'}</div>
        <button className="reconnect-btn" onClick={onReconnect} type="button">Reconnect</button>
      </div>

      <div className="decision-chip">
        <p>Latest Decision</p>
        <strong>{latestDecision?.decision ?? 'N/A'}</strong>
      </div>
    </header>
  );
}
