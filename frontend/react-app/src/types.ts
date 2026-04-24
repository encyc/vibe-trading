export type DecisionAction = 'BUY' | 'SELL' | 'HOLD' | 'STRONG_BUY' | 'STRONG_SELL';

export interface KlineData {
  time: string;
  open_time_ms?: number;
  symbol?: string;
  interval?: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface IndicatorsData {
  rsi: Array<number | null>;
  macd: Array<number | null>;
  macd_signal: Array<number | null>;
  macd_hist: Array<number | null>;
  sma_20: Array<number | null>;
  sma_50: Array<number | null>;
  ema_12: Array<number | null>;
  ema_26: Array<number | null>;
  bb_upper: Array<number | null>;
  bb_middle: Array<number | null>;
  bb_lower: Array<number | null>;
  atr: Array<number | null>;
}

export interface DecisionData {
  index: number;
  time: string;
  open_time_ms?: number;
  symbol?: string;
  interval?: string;
  close: number;
  decision: DecisionAction;
  rationale: string;
}

export interface LogEntry {
  timestamp: string;
  level: 'info' | 'warning' | 'error' | 'debug';
  tag: string;
  message: string;
  open_time_ms?: number;
  symbol?: string;
  interval?: string;
}

export interface PhaseState {
  status: 'running' | 'completed' | 'error';
  duration?: number;
}

export type PhaseStatus = Record<string, PhaseState | string> & {
  current: string;
};

export interface AgentReport {
  agent: string;
  phase: string;
  content: string;
}

export interface InitPayload {
  klines: KlineData[];
  indicators: IndicatorsData;
  decisions: DecisionData[];
  logs: LogEntry[];
  phase_status: PhaseStatus;
  agent_reports: Record<string, Record<string, string>>;
}

export type WsMessage =
  | { type: 'init'; data: InitPayload }
  | { type: 'kline'; data: KlineData }
  | { type: 'decision'; data: DecisionData }
  | { type: 'log'; data: LogEntry }
  | { type: 'phase'; data: { phase: string; status: 'running' | 'completed' | 'error'; duration?: number } }
  | { type: 'report'; data: AgentReport }
  | { type: 'reset'; data?: Record<string, never> }
  | { type: 'decision_tree'; data: unknown }
  | { type: 'heartbeat'; data?: Record<string, never> };

export interface TradingSnapshot {
  klines: KlineData[];
  indicators: IndicatorsData;
  decisions: DecisionData[];
  logs: LogEntry[];
  phaseStatus: PhaseStatus;
  agentReports: Record<string, Record<string, string>>;
}

export type ConnectionState = 'connecting' | 'connected' | 'reconnecting' | 'offline' | 'error';

export interface FeedStatus {
  state: ConnectionState;
  reconnectAttempt: number;
  lastMessageAt: number | null;
  error: string | null;
}

export interface SystemStatus {
  connected_clients: number;
  total_klines: number;
  total_decisions: number;
  current_phase: string | null;
}

export interface BarTrace {
  symbol: string;
  interval: string;
  open_time_ms: number;
  bar_time: string;
  kline: KlineData;
  phase_status: PhaseStatus;
  decision: DecisionData | null;
  reports: Record<string, Record<string, string>>;
  logs: LogEntry[];
  updated_at: string;
}

export const EMPTY_INDICATORS: IndicatorsData = {
  rsi: [],
  macd: [],
  macd_signal: [],
  macd_hist: [],
  sma_20: [],
  sma_50: [],
  ema_12: [],
  ema_26: [],
  bb_upper: [],
  bb_middle: [],
  bb_lower: [],
  atr: [],
};

export const EMPTY_SNAPSHOT: TradingSnapshot = {
  klines: [],
  indicators: EMPTY_INDICATORS,
  decisions: [],
  logs: [],
  phaseStatus: { current: '' },
  agentReports: {},
};