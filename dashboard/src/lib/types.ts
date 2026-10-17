/** Shared journal shapes aligned with the Python Trade Journal (M4). */

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

export type SystemEvent = {
  id: number;
  createdAt: string;
  eventType: string;
  message: string;
};

export type JournalSnapshot = {
  mode: "demo" | "api";
  generatedAt: string;
  note: string;
  killSwitch: KillSwitchState;
  decisions: Decision[];
  trades: Trade[];
  systemEvents: SystemEvent[];
};

export type KillSwitchAction = "engage" | "clear";
