import { AgentActivityPanel } from './components/AgentActivityPanel';
import { ChartPanel } from './components/ChartPanel';
import { DecisionOverviewPanel } from './components/DecisionOverviewPanel';
import { LogsPanel } from './components/LogsPanel';
import { SideToolbar } from './components/SideToolbar';
import { TopBar } from './components/TopBar';
import { useTradingFeed } from './hooks/useTradingFeed';

const SYMBOL = 'BTCUSDT';

function App() {
  const { snapshot, status, latestDecision, reconnectNow } = useTradingFeed();

  return (
    <div className="app-shell trading-layout">
      <TopBar
        symbol={SYMBOL}
        klines={snapshot.klines}
        latestDecision={latestDecision}
        status={status}
        onReconnect={reconnectNow}
      />

      <main className="terminal-grid">
        <section className="chart-zone">
          <SideToolbar />

          <div className="chart-stage panel">
            <div className="panel-head chart-head">
              <h2>BTCUSDT · 4小时</h2>
              <span>{snapshot.klines.length > 0 ? `收 ${snapshot.klines[snapshot.klines.length - 1].close.toFixed(2)}` : '等待数据'}</span>
            </div>

            <div className="chart-main">
              <ChartPanel
                klines={snapshot.klines}
                indicators={snapshot.indicators}
                decisions={snapshot.decisions}
              />
            </div>

            <div className="chart-footer">
              <span>已加载历史数据: {snapshot.klines.length}</span>
              <span>最近更新: {status.lastMessageAt ? new Date(status.lastMessageAt).toLocaleTimeString() : '--'}</span>
            </div>
          </div>
        </section>

        <section className="control-zone">
          <AgentActivityPanel
            phaseStatus={snapshot.phaseStatus}
            agentReports={snapshot.agentReports}
            logs={snapshot.logs}
          />
          <DecisionOverviewPanel
            klines={snapshot.klines}
            decisions={snapshot.decisions}
          />
        </section>
      </main>

      <section className="bottom-log-strip">
        <LogsPanel logs={snapshot.logs} />
      </section>
    </div>
  );
}

export default App;
