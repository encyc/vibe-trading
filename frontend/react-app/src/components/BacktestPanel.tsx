import type { FeedStatus, PhaseStatus } from '../types';
import type { UseBacktestResult } from '../hooks/useBacktest';

interface BacktestPanelProps {
  phaseStatus: PhaseStatus;
  status: FeedStatus;
  backtest: UseBacktestResult;
}

const phaseOrder = ['ANALYZING', 'DEBATING', 'ASSESSING_RISK', 'PLANNING', 'COMPLETED'];

export function BacktestPanel({ phaseStatus, status, backtest }: BacktestPanelProps) {
  const current = phaseStatus.current || 'IDLE';
  const task = backtest.task;

  return (
    <section className="panel control-panel">
      <div className="panel-head">
        <h2>回测</h2>
        <span>{status.state}</span>
      </div>

      <div className="control-fields">
        <label>
          策略
          <select value={backtest.form.llm_mode} onChange={(event) => backtest.setField('llm_mode', event.target.value as 'simulated' | 'cached' | 'real')}>
            <option value="simulated">Vibe Multi-Agent Strategy</option>
            <option value="cached">Cached LLM Strategy</option>
            <option value="real">Real LLM Strategy</option>
          </select>
        </label>

        <label>
          交易对
          <input value={backtest.form.symbol} onChange={(event) => backtest.setField('symbol', event.target.value.toUpperCase())} />
        </label>

        <label>
          K线周期
          <select value={backtest.form.interval} onChange={(event) => backtest.setField('interval', event.target.value)}>
            <option value="1h">1h</option>
            <option value="4h">4h</option>
            <option value="1d">1d</option>
          </select>
        </label>

        <label>
          初始资金
          <input
            type="number"
            min={100}
            step={100}
            value={backtest.form.initial_balance}
            onChange={(event) => backtest.setField('initial_balance', Number(event.target.value || 0))}
          />
        </label>

        <label>
          时间范围
          <div className="range-row">
            <input type="date" value={backtest.form.start_time} onChange={(event) => backtest.setField('start_time', event.target.value)} />
            <input type="date" value={backtest.form.end_time} onChange={(event) => backtest.setField('end_time', event.target.value)} />
          </div>
        </label>

        <div className="action-row action-row-2">
          <button type="button" className="run-btn" onClick={backtest.runBacktest} disabled={backtest.isSubmitting}>
            {backtest.isSubmitting ? '提交中...' : '运行回测'}
          </button>
          <button type="button" className="ghost-btn" onClick={backtest.resetData} disabled={backtest.isResetting}>
            {backtest.isResetting ? '重置中...' : '重置监控'}
          </button>
          <button type="button" className="ghost-btn" onClick={backtest.refreshMonitorStatus}>
            刷新状态
          </button>
        </div>

        <div className="action-row action-row-2">
          <button
            type="button"
            className="ghost-btn"
            onClick={() => {
              if (backtest.resultUrl) {
                window.open(backtest.resultUrl, '_blank', 'noopener,noreferrer');
              }
            }}
            disabled={!backtest.resultUrl}
          >
            详细信息
          </button>
          <button
            type="button"
            className="ghost-btn"
            onClick={() => {
              if (backtest.resultUrl) {
                window.open(backtest.resultUrl, '_blank', 'noopener,noreferrer');
              }
            }}
            disabled={!backtest.resultUrl}
          >
            交易记录
          </button>
        </div>

        {backtest.error && <p className="inline-error">{backtest.error}</p>}

        <div className="task-summary">
          <p>Task: {task?.task_id ?? '--'}</p>
          <p>Status: {task?.status ?? '--'}</p>
          <p>Progress: {backtest.progress ? `${backtest.progress.progress_percentage.toFixed(2)}%` : '--'}</p>
          <p>Equity: {task ? task.current_equity.toFixed(2) : '--'}</p>
        </div>
      </div>

      <div className="phase-steps">
        {phaseOrder.map((phase) => {
          const phaseObj = phaseStatus[phase];
          const phaseState = typeof phaseObj === 'string' || !phaseObj ? 'pending' : phaseObj.status;

          return (
            <div key={phase} className={`phase-step ${current === phase ? 'active' : ''}`}>
              <span className={`phase-dot ${phaseState}`} />
              <span>{phase.replace('_', ' ')}</span>
            </div>
          );
        })}
      </div>
    </section>
  );
}
