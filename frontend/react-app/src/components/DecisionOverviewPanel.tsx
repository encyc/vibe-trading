import { formatCompact, formatPrice, formatTime } from '../lib/format';
import type { BarTrace, DecisionData, KlineData } from '../types';

interface DecisionOverviewPanelProps {
  klines: KlineData[];
  decisions: DecisionData[];
  selectedKline?: KlineData | null;
  trace?: BarTrace | null;
}

export function DecisionOverviewPanel({ klines, decisions, selectedKline, trace }: DecisionOverviewPanelProps) {
  const current = selectedKline ?? klines[klines.length - 1];
  const currentOpenMs = current ? (current.open_time_ms ?? new Date(current.time).getTime()) : null;
  const previous = currentOpenMs
    ? klines.find((item) => {
      const itemMs = item.open_time_ms ?? new Date(item.time).getTime();
      return itemMs === currentOpenMs - 60 * 60 * 1000
        || itemMs === currentOpenMs - 4 * 60 * 60 * 1000
        || itemMs === currentOpenMs - 24 * 60 * 60 * 1000;
    }) ?? klines[klines.length - 2]
    : klines[klines.length - 2];
  const latestDecision = trace?.decision ?? (
    currentOpenMs
      ? decisions.find((item) => (item.open_time_ms ?? new Date(item.time).getTime()) === currentOpenMs)
      : decisions[decisions.length - 1]
  );
  const recent = decisions.slice(-5).reverse();

  const delta = current && previous ? current.close - previous.close : 0;
  const deltaPct = current && previous ? (delta / previous.close) * 100 : 0;

  return (
    <section className="panel decision-overview-panel">
      <div className="panel-head">
        <h2>Current Candle & Decision</h2>
        <span>{current ? formatTime(current.time) : '--:--:--'}</span>
      </div>

      <div className="decision-overview-body">
        <div className="kline-grid">
          <div><span>Open</span><strong>{current ? formatPrice(current.open) : '--'}</strong></div>
          <div><span>High</span><strong>{current ? formatPrice(current.high) : '--'}</strong></div>
          <div><span>Low</span><strong>{current ? formatPrice(current.low) : '--'}</strong></div>
          <div><span>Close</span><strong>{current ? formatPrice(current.close) : '--'}</strong></div>
          <div><span>Volume</span><strong>{current ? formatCompact(current.volume) : '--'}</strong></div>
          <div>
            <span>Delta</span>
            <strong className={delta >= 0 ? 'up' : 'down'}>
              {current ? `${delta >= 0 ? '+' : ''}${formatPrice(delta)} (${deltaPct.toFixed(2)}%)` : '--'}
            </strong>
          </div>
        </div>

        <div className="final-decision-box">
          <p className="final-title">Final Decision</p>
          <p className={`final-value ${latestDecision ? latestDecision.decision.toLowerCase() : ''}`}>
            {latestDecision?.decision ?? 'N/A'}
          </p>
          <p className="final-rationale">
            {latestDecision?.rationale || 'No final decision rationale yet.'}
          </p>
        </div>

        <div className="recent-decision-list">
          <p className="recent-title">Recent Decisions</p>
          {recent.length === 0 && <p className="empty-text">No decisions yet.</p>}
          {recent.map((row) => (
            <div key={`${row.index}-${row.time}`} className="recent-row">
              <span>{formatTime(row.time)}</span>
              <strong>{row.decision}</strong>
              <span>{formatPrice(row.close)}</span>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
