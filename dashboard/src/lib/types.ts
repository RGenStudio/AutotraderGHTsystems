/** Shared journal shapes aligned with the Python Trade Journal. */

export type KillSwitchState = {
  active: boolean;
  reason: string;
  engagedAt: string | null;
  updatedAt: string;
};

export type Decision = {
  id: number;
  createdAt: string;
  symbol: string | null;
  allowed: boolean;
  reason: string;
  action: string;
  idempotencyKey: string;
};

export type Trade = {
  id: number;
  createdAt: string;
  symbol: string;
  side: string;
  volume: number;
  entryPrice: number;
  exitPrice: number | null;
  stopPrice: number | null;
  takeProfit: number | null;
  pnl: number | null;
  pnlR: number | null;
  ticket: string;
  status: string;
  openedAt: string | null;
  closedAt: string | null;
};

export type Signal = {
  id: number;
  createdAt: string;
  symbol: string;
  strategy: string;
  side: string;
  entryPrice: number;
  stopPrice: number;
  takeProfit: number | null;
  reason: string;
};

export type SystemEvent = {
  id: number;
  createdAt: string;
  eventType: string;
  message: string;
};

export type EngineStatus = {
  state: "up" | "down" | "stale" | "unknown";
  lastEventType: string | null;
  lastEventAt: string | null;
  message: string;
};

export type PnlSummary = {
  openCount: number;
  closedCount: number;
  /** Sum of `trades.pnl` for non-open rows. Null when the journal was not read. */
  closedPnl: number | null;
};

export type JournalMode = "demo" | "live" | "unconfigured" | "error";

export type JournalSnapshot = {
  mode: JournalMode;
  generatedAt: string;
  note: string;
  error: string | null;
  killSwitch: KillSwitchState;
  /** `journal` is the engine row in kill_switch_state. `local` is the dashboard file flag. */
  killSwitchSource: "journal" | "local";
  decisions: Decision[];
  trades: Trade[];
  signals: Signal[];
  systemEvents: SystemEvent[];
  engine: EngineStatus;
  pnl: PnlSummary;
};

export type KillSwitchAction = "engage" | "clear";
