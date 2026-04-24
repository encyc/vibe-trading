import type { BarTrace, LogEntry, PhaseStatus } from '../types';

interface AgentActivityPanelProps {
  phaseStatus: PhaseStatus;
  agentReports: Record<string, Record<string, string>>;
  logs: LogEntry[];
  trace?: BarTrace | null;
}

interface AgentCard {
  label: string;
  aliases: string[];
}

interface AgentPhase {
  key: string;
  title: string;
  agents: AgentCard[];
}

const PHASES: AgentPhase[] = [
  {
    key: 'analysts',
    title: 'Phase 1 · Analysts',
    agents: [
      { label: 'Technical Analyst', aliases: ['technical', 'technical analyst'] },
      { label: 'Fundamental Analyst', aliases: ['fundamental', 'fundamental analyst'] },
      { label: 'News Analyst', aliases: ['news', 'news analyst'] },
      { label: 'Sentiment Analyst', aliases: ['sentiment', 'sentiment analyst'] },
    ],
  },
  {
    key: 'researchers',
    title: 'Phase 2 · Researchers',
    agents: [
      { label: 'Bull Researcher', aliases: ['bull', 'bull researcher'] },
      { label: 'Bear Researcher', aliases: ['bear', 'bear researcher'] },
      { label: 'Research Manager', aliases: ['research manager', 'manager'] },
    ],
  },
  {
    key: 'risk',
    title: 'Phase 3 · Risk Team',
    agents: [
      { label: 'Aggressive Analyst', aliases: ['aggressive', 'aggressive analyst'] },
      { label: 'Neutral Analyst', aliases: ['neutral', 'neutral analyst'] },
      { label: 'Conservative Analyst', aliases: ['conservative', 'conservative analyst'] },
    ],
  },
  {
    key: 'trader',
    title: 'Phase 4 · Execution Plan',
    agents: [{ label: 'Trader', aliases: ['trader'] }],
  },
  {
    key: 'pm',
    title: 'Final · Portfolio Manager',
    agents: [{ label: 'Portfolio Manager', aliases: ['portfolio manager'] }],
  },
];

const phaseMap: Record<string, string> = {
  ANALYZING: 'analysts',
  DEBATING: 'researchers',
  ASSESSING_RISK: 'risk',
  PLANNING: 'trader',
  COMPLETED: 'pm',
};

function normalize(value: string): string {
  return value.trim().toLowerCase();
}

function pickReport(phaseBucket: Record<string, string> | undefined, aliases: string[]): string | null {
  if (!phaseBucket) {
    return null;
  }

  const normalizedAliases = aliases.map(normalize);
  for (const [key, value] of Object.entries(phaseBucket)) {
    const keyNormalized = normalize(key);
    if (normalizedAliases.some((alias) => keyNormalized.includes(alias))) {
      return value;
    }
  }
  return null;
}

function pickAgentLog(logs: LogEntry[], aliases: string[]): string | null {
  const normalizedAliases = aliases.map(normalize);

  for (let i = logs.length - 1; i >= 0; i -= 1) {
    const row = logs[i];
    const tag = normalize(row.tag || '');
    if (normalizedAliases.some((alias) => tag.includes(alias))) {
      return row.message;
    }
  }
  return null;
}

function phaseStateLabel(phaseStatus: PhaseStatus, phaseKey: string): string {
  const phaseToStatusKey: Record<string, string> = {
    analysts: 'ANALYZING',
    researchers: 'DEBATING',
    risk: 'ASSESSING_RISK',
    trader: 'PLANNING',
    pm: 'COMPLETED',
  };
  const state = phaseStatus[phaseToStatusKey[phaseKey] ?? phaseKey.toUpperCase()];
  if (typeof state === 'string' || !state) {
    return 'pending';
  }
  return state.status;
}

export function AgentActivityPanel({ phaseStatus, agentReports, logs, trace }: AgentActivityPanelProps) {
  const effectivePhaseStatus = trace?.phase_status ?? phaseStatus;
  const effectiveReports = trace?.reports ?? agentReports;
  const effectiveLogs = trace?.logs ?? logs;
  const currentPhase = phaseMap[effectivePhaseStatus.current || ''] ?? '';

  return (
    <section className="panel agent-activity-panel">
      <div className="panel-head">
        <h2>Agent Monitor</h2>
        <span>{effectivePhaseStatus.current || 'IDLE'}</span>
      </div>

      <div className="agent-phase-list">
        {PHASES.map((phase) => {
          const phaseBucket = effectiveReports[phase.key];
          const active = phase.key === currentPhase;
          const phaseState = phaseStateLabel(effectivePhaseStatus, phase.key);

          return (
            <article key={phase.key} className={`agent-phase ${active ? 'active' : ''}`}>
              <header>
                <strong>{phase.title}</strong>
                <em>{phaseState}</em>
              </header>

              <div className="agent-cards">
                {phase.agents.map((agent) => {
                  const report = pickReport(phaseBucket, agent.aliases);
                  const logHint = pickAgentLog(effectiveLogs, agent.aliases);
                  const content = report || logHint || 'Waiting for this agent output...';

                  return (
                    <div key={agent.label} className="agent-card">
                      <p className="agent-name">{agent.label}</p>
                      <p className="agent-content">{content}</p>
                    </div>
                  );
                })}
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}
