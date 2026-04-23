import { formatPrice } from '../lib/format';
import type { DecisionData, KlineData } from '../types';

interface WatchlistPanelProps {
  klines: KlineData[];
  decisions: DecisionData[];
}

interface WatchItem {
  symbol: string;
  price: number;
  change: number;
}

export function WatchlistPanel({ klines, decisions }: WatchlistPanelProps) {
  const latest = klines[klines.length - 1]?.close ?? 0;
  const base = latest || 100000;

  const items: WatchItem[] = [
    { symbol: 'BTCUSDT', price: base, change: 1.42 },
    { symbol: 'ETHUSDT', price: base * 0.053, change: -0.84 },
    { symbol: 'SOLUSDT', price: base * 0.0015, change: 2.31 },
    { symbol: 'BNBUSDT', price: base * 0.0064, change: 0.67 },
    { symbol: 'DOGEUSDT', price: base * 0.0000019, change: -1.12 },
  ];

  return (
    <section className="panel watchlist-panel">
      <div className="panel-head">
        <h2>自选列表</h2>
        <span>{decisions.length} decisions</span>
      </div>

      <div className="watchlist-body">
        {items.map((item) => (
          <div key={item.symbol} className="watch-row">
            <div>
              <strong>{item.symbol}</strong>
              <p>{item.change > 0 ? 'Momentum up' : 'Pressure down'}</p>
            </div>
            <div className="watch-price">
              <span>${formatPrice(item.price)}</span>
              <em className={item.change >= 0 ? 'up' : 'down'}>{item.change >= 0 ? '+' : ''}{item.change.toFixed(2)}%</em>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
