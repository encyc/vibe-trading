import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { CSSProperties, MouseEvent as ReactMouseEvent } from 'react';
import { AgentActivityPanel } from './components/AgentActivityPanel';
import { ChartPanel } from './components/ChartPanel';
import { DecisionOverviewPanel } from './components/DecisionOverviewPanel';
import { LogsPanel } from './components/LogsPanel';
import { TopBar } from './components/TopBar';
import { getBarTrace } from './services/api';
import { useTradingFeed } from './hooks/useTradingFeed';
import type { BarTrace, KlineData } from './types';

const SYMBOL = 'BTCUSDT';
type PanelKey = 'agent' | 'decision' | 'logs';
const DEFAULT_PANEL_ORDER: PanelKey[] = ['agent', 'decision', 'logs'];
const DEFAULT_PANEL_SIZE: Record<PanelKey, number> = { agent: 54, decision: 28, logs: 18 };
const PANEL_ORDER_STORAGE_KEY = 'vibe-panel-order-v1';
const PANEL_SIZE_STORAGE_KEY = 'vibe-panel-size-v1';
const SPLIT_STORAGE_KEY = 'vibe-main-split-v1';
const MIN_PANEL_SIZE = 12;
const AGENT_SCORECARDS = [
  { name: 'Technical', phase: 'analysts', accent: '#4f6fff' },
  { name: 'Fundamental', phase: 'analysts', accent: '#111111' },
  { name: 'Sentiment', phase: 'analysts', accent: '#00a88f' },
  { name: 'Research PM', phase: 'researchers', accent: '#8d5cff' },
  { name: 'Risk Team', phase: 'risk', accent: '#f0642f' },
  { name: 'Portfolio', phase: 'pm', accent: '#008f7a' },
];

function App() {
  const { snapshot, status, latestDecision, reconnectNow } = useTradingFeed();
  const [panelOrder, setPanelOrder] = useState<PanelKey[]>(DEFAULT_PANEL_ORDER);
  const [panelSizes, setPanelSizes] = useState<Record<PanelKey, number>>(DEFAULT_PANEL_SIZE);
  const [mainSplit, setMainSplit] = useState(58);
  const [draggingPanel, setDraggingPanel] = useState<PanelKey | null>(null);
  const [dragOverPanel, setDragOverPanel] = useState<PanelKey | null>(null);
  const [selectedKline, setSelectedKline] = useState<KlineData | null>(null);
  const [selectedBarTrace, setSelectedBarTrace] = useState<BarTrace | null>(null);

  const controlZoneRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    try {
      const rawOrder = window.localStorage.getItem(PANEL_ORDER_STORAGE_KEY);
      if (rawOrder) {
        const parsed = JSON.parse(rawOrder) as PanelKey[];
        const valid = parsed.filter((item) => DEFAULT_PANEL_ORDER.includes(item));
        if (valid.length === DEFAULT_PANEL_ORDER.length) {
          setPanelOrder(valid);
        }
      }

      const rawSize = window.localStorage.getItem(PANEL_SIZE_STORAGE_KEY);
      if (rawSize) {
        const parsed = JSON.parse(rawSize) as Record<string, number>;
        const next: Record<PanelKey, number> = {
          agent: Number(parsed.agent) || DEFAULT_PANEL_SIZE.agent,
          decision: Number(parsed.decision) || DEFAULT_PANEL_SIZE.decision,
          logs: Number(parsed.logs) || DEFAULT_PANEL_SIZE.logs,
        };
        const total = next.agent + next.decision + next.logs;
        if (total > 0) {
          setPanelSizes({
            agent: (next.agent / total) * 100,
            decision: (next.decision / total) * 100,
            logs: (next.logs / total) * 100,
          });
        }
      }

      const rawSplit = window.localStorage.getItem(SPLIT_STORAGE_KEY);
      if (rawSplit) {
        const parsed = Number(rawSplit);
        if (Number.isFinite(parsed) && parsed >= 35 && parsed <= 78) {
          setMainSplit(parsed);
        }
      }
    } catch {
      // ignore local storage parse errors
    }
  }, []);

  useEffect(() => {
    window.localStorage.setItem(PANEL_ORDER_STORAGE_KEY, JSON.stringify(panelOrder));
  }, [panelOrder]);

  useEffect(() => {
    window.localStorage.setItem(PANEL_SIZE_STORAGE_KEY, JSON.stringify(panelSizes));
  }, [panelSizes]);

  useEffect(() => {
    window.localStorage.setItem(SPLIT_STORAGE_KEY, String(mainSplit));
  }, [mainSplit]);

  useEffect(() => {
    if (!snapshot.klines.length) {
      setSelectedKline(null);
      setSelectedBarTrace(null);
      return;
    }

    if (!selectedKline) {
      setSelectedKline(snapshot.klines[snapshot.klines.length - 1]);
      return;
    }

    const selectedMs = selectedKline.open_time_ms ?? new Date(selectedKline.time).getTime();
    const stillExists = snapshot.klines.some((item) => (item.open_time_ms ?? new Date(item.time).getTime()) === selectedMs);
    if (!stillExists) {
      setSelectedKline(snapshot.klines[snapshot.klines.length - 1]);
    }
  }, [selectedKline, snapshot.klines]);

  useEffect(() => {
    if (!selectedKline) {
      setSelectedBarTrace(null);
      return;
    }

    const openTimeMs = selectedKline.open_time_ms ?? new Date(selectedKline.time).getTime();
    const symbol = selectedKline.symbol ?? SYMBOL;
    const interval = selectedKline.interval ?? '30m';

    let cancelled = false;

    const run = async () => {
      try {
        const trace = await getBarTrace(openTimeMs, symbol, interval);
        if (!cancelled) {
          setSelectedBarTrace(trace);
        }
      } catch {
        if (!cancelled) {
          setSelectedBarTrace(null);
        }
      }
    };

    void run();

    return () => {
      cancelled = true;
    };
  }, [selectedKline]);

  const panelContent = useMemo(
    () => ({
      agent: (
        <AgentActivityPanel
          phaseStatus={snapshot.phaseStatus}
          agentReports={snapshot.agentReports}
          logs={snapshot.logs}
          trace={selectedBarTrace}
        />
      ),
      decision: (
        <DecisionOverviewPanel
          klines={snapshot.klines}
          decisions={snapshot.decisions}
          selectedKline={selectedKline}
          trace={selectedBarTrace}
        />
      ),
      logs: <LogsPanel logs={selectedBarTrace?.logs ?? snapshot.logs} />,
    }),
    [
      selectedBarTrace,
      selectedKline,
      snapshot.agentReports,
      snapshot.decisions,
      snapshot.klines,
      snapshot.logs,
      snapshot.phaseStatus,
    ],
  );

  const movePanel = (from: PanelKey, to: PanelKey) => {
    if (from === to) {
      return;
    }

    setPanelOrder((prev) => {
      const fromIndex = prev.indexOf(from);
      const toIndex = prev.indexOf(to);
      if (fromIndex < 0 || toIndex < 0) {
        return prev;
      }

      const next = [...prev];
      next.splice(fromIndex, 1);
      next.splice(toIndex, 0, from);
      return next;
    });
  };

  const startMainResize = useCallback((event: ReactMouseEvent<HTMLDivElement>) => {
    event.preventDefault();
    const startX = event.clientX;
    const startSplit = mainSplit;

    const onMove = (moveEvent: MouseEvent) => {
      const deltaX = moveEvent.clientX - startX;
      const viewportWidth = window.innerWidth || 1;
      const deltaPct = (deltaX / viewportWidth) * 100;
      const next = Math.max(35, Math.min(78, startSplit + deltaPct));
      setMainSplit(next);
    };

    const onUp = () => {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
      document.body.classList.remove('resizing-active');
    };

    document.body.classList.add('resizing-active');
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
  }, [mainSplit]);

  const startPanelResize = useCallback((index: number, event: ReactMouseEvent<HTMLDivElement>) => {
    event.preventDefault();

    const currentPanel = panelOrder[index];
    const nextPanel = panelOrder[index + 1];
    if (!currentPanel || !nextPanel || !controlZoneRef.current) {
      return;
    }

    const zoneHeight = controlZoneRef.current.getBoundingClientRect().height || 1;
    const startY = event.clientY;
    const startCurrent = panelSizes[currentPanel];
    const startNext = panelSizes[nextPanel];

    const onMove = (moveEvent: MouseEvent) => {
      const deltaY = moveEvent.clientY - startY;
      const deltaPct = (deltaY / zoneHeight) * 100;

      let nextCurrent = startCurrent + deltaPct;
      let nextNext = startNext - deltaPct;

      if (nextCurrent < MIN_PANEL_SIZE) {
        nextNext -= MIN_PANEL_SIZE - nextCurrent;
        nextCurrent = MIN_PANEL_SIZE;
      }
      if (nextNext < MIN_PANEL_SIZE) {
        nextCurrent -= MIN_PANEL_SIZE - nextNext;
        nextNext = MIN_PANEL_SIZE;
      }

      setPanelSizes((prev) => ({
        ...prev,
        [currentPanel]: nextCurrent,
        [nextPanel]: nextNext,
      }));
    };

    const onUp = () => {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
      document.body.classList.remove('resizing-active');
    };

    document.body.classList.add('resizing-active');
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
  }, [panelOrder, panelSizes]);

  const controlRows = panelOrder.map((panel) => `${Math.max(8, panelSizes[panel]).toFixed(3)}fr`).join(' ');
  const selectedOpenTime = selectedKline ? new Date(selectedKline.time).toLocaleString() : 'NO BAR SELECTED';
  const traceReports = selectedBarTrace?.reports ?? snapshot.agentReports;
  const traceLogs = selectedBarTrace?.logs ?? snapshot.logs;
  const traceDecision = selectedBarTrace?.decision ?? latestDecision;

  return (
    <div className="app-shell trading-layout">
      <TopBar
        symbol={SYMBOL}
        klines={snapshot.klines}
        latestDecision={latestDecision}
        status={status}
        onReconnect={reconnectNow}
      />

      <main
        className="terminal-grid"
        style={{
          gridTemplateColumns: `${mainSplit}% 8px minmax(360px, ${100 - mainSplit}%)`,
        }}
      >
        <section className="chart-zone">
          <div className="chart-stage panel">
            <div className="panel-head chart-head">
              <h2>Total Account Value</h2>
              <span>{selectedOpenTime}</span>
            </div>

            <div className="chart-main">
              <ChartPanel
                klines={snapshot.klines}
                indicators={snapshot.indicators}
                decisions={snapshot.decisions}
                onBarSelect={setSelectedKline}
              />
            </div>

            <div className="chart-footer">
              <span>Loaded bars: {snapshot.klines.length}</span>
              <span>Last update: {status.lastMessageAt ? new Date(status.lastMessageAt).toLocaleTimeString() : '--'}</span>
            </div>

            <div className="agent-score-strip">
              {AGENT_SCORECARDS.map((agent) => {
                const reportCount = Object.keys(traceReports[agent.phase] ?? {}).length;
                const hasActivity = reportCount > 0 || traceLogs.some((row) => row.tag.toLowerCase().includes(agent.name.toLowerCase().split(' ')[0]));

                return (
                  <article key={agent.name} className="agent-score-card" style={{ '--agent-accent': agent.accent } as CSSProperties}>
                    <span className="agent-dot" />
                    <strong>{agent.name}</strong>
                    <em>{hasActivity ? 'ACTIVE' : 'WAITING'}</em>
                    <p>{reportCount} reports</p>
                  </article>
                );
              })}
              <article className="agent-score-card final-card">
                <span className="agent-dot" />
                <strong>Final</strong>
                <em>{traceDecision?.decision ?? 'N/A'}</em>
                <p>{traceDecision?.rationale ? 'decision recorded' : 'pending decision'}</p>
              </article>
            </div>
          </div>
        </section>

        <div className="main-resizer" onMouseDown={startMainResize} role="separator" aria-label="Resize main layout" />

        <section ref={controlZoneRef} className="control-zone" style={{ gridTemplateRows: controlRows }}>
          {panelOrder.map((panel, index) => (
            <div
              key={panel}
              className={`draggable-module ${dragOverPanel === panel ? 'drag-over' : ''}`}
              draggable
              onDragStart={(event) => {
                setDraggingPanel(panel);
                event.dataTransfer.setData('text/plain', panel);
                event.dataTransfer.effectAllowed = 'move';
              }}
              onDragEnd={() => {
                setDraggingPanel(null);
                setDragOverPanel(null);
              }}
              onDragOver={(event) => {
                event.preventDefault();
                if (dragOverPanel !== panel) {
                  setDragOverPanel(panel);
                }
              }}
              onDragLeave={() => {
                setDragOverPanel((prev) => (prev === panel ? null : prev));
              }}
              onDrop={(event) => {
                event.preventDefault();
                const source = (event.dataTransfer.getData('text/plain') || draggingPanel) as PanelKey | null;
                if (source) {
                  movePanel(source, panel);
                }
                setDraggingPanel(null);
                setDragOverPanel(null);
              }}
            >
              <div className="drag-hint">Drag</div>
              {panelContent[panel]}
              {index < panelOrder.length - 1 && (
                <div
                  className="panel-resizer"
                  onMouseDown={(event) => startPanelResize(index, event)}
                  role="separator"
                  aria-label="Resize panel"
                />
              )}
            </div>
          ))}
        </section>
      </main>
    </div>
  );
}

export default App;
