import "server-only";

import {
  DEMO_DECISIONS,
  DEMO_EVENTS,
  DEMO_NOTE,
  DEMO_SIGNALS,
  DEMO_TRADES,
} from "./demo-data";
import { explainQueryFailure, loadLiveSnapshot } from "./journal-db";
import { readKillSwitch } from "./kill-switch-store";
import { describeDataSource, liveBackend } from "./source";
import type { JournalSnapshot, PnlSummary } from "./types";

export { describeDataSource as getDataMode } from "./source";

const NO_ENGINE = {
  state: "unknown" as const,
  lastEventType: null,
  lastEventAt: null,
  message: "Journal database is not connected from this server.",
};

function pnlFromDemoTrades(): PnlSummary {
  let openCount = 0;
  let closedCount = 0;
  let closedPnl = 0;
  for (const trade of DEMO_TRADES) {
    if (trade.status === "open") openCount += 1;
    else {
      closedCount += 1;
      if (trade.pnl != null) closedPnl += trade.pnl;
    }
  }
  return { openCount, closedCount, closedPnl };
}

function demoSnapshot(killSwitch: JournalSnapshot["killSwitch"]): JournalSnapshot {
  const heartbeat = DEMO_EVENTS.find((row) => row.eventType === "heartbeat") ?? null;
  return {
    mode: "demo",
    generatedAt: new Date().toISOString(),
    note: DEMO_NOTE,
    error: null,
    killSwitch,
    killSwitchSource: "local",
    decisions: DEMO_DECISIONS,
    trades: DEMO_TRADES,
    signals: DEMO_SIGNALS,
    systemEvents: DEMO_EVENTS,
    engine: {
      state: "up",
      lastEventType: heartbeat?.eventType ?? "heartbeat",
      lastEventAt: heartbeat?.createdAt ?? null,
      message: heartbeat?.message ?? "Sample heartbeat",
    },
    pnl: pnlFromDemoTrades(),
  };
}

function blankSnapshot(
  mode: JournalSnapshot["mode"],
  note: string,
  error: string | null,
): JournalSnapshot {
  return {
    mode,
    generatedAt: new Date().toISOString(),
    note,
    error,
    killSwitch: {
      active: false,
      reason: "",
      engagedAt: null,
      updatedAt: new Date(0).toISOString(),
    },
    killSwitchSource: "local",
    decisions: [],
    trades: [],
    signals: [],
    systemEvents: [],
    engine: mode === "error" ? { ...NO_ENGINE, message: "Journal query failed." } : NO_ENGINE,
    pnl: { openCount: 0, closedCount: 0, closedPnl: null },
  };
}

function unconfiguredSnapshot(): JournalSnapshot {
  return blankSnapshot(
    "unconfigured",
    "Database not configured. On Vercel, set DATABASE_URL to the Supabase transaction pooler URI (port 6543), or set both SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY. Those values are server-only — never NEXT_PUBLIC_. The Windows engine uses its own DATABASE_URL (session pooler, port 5432). This page is not showing sample trades.",
    null,
  );
}

function misconfiguredSnapshot(): JournalSnapshot {
  return blankSnapshot(
    "error",
    "DATABASE_URL is set but it is not a Postgres URI. This dashboard cannot open the engine's SQLite file. Use the Supabase transaction pooler URI (port 6543, sslmode=require) or SUPABASE_URL plus SUPABASE_SERVICE_ROLE_KEY.",
    "DATABASE_URL is not a postgres:// or postgresql:// URI",
  );
}

export async function loadJournal(): Promise<JournalSnapshot> {
  const backend = liveBackend();
  if (backend === "invalid") return misconfiguredSnapshot();
  if (backend === "postgres" || backend === "supabase") {
    try {
      return await loadLiveSnapshot(backend);
    } catch (err) {
      const detail = explainQueryFailure(err);
      return {
        ...blankSnapshot("error", detail, detail),
        killSwitchSource: "journal",
      };
    }
  }
  if (describeDataSource() === "demo") {
    return demoSnapshot(await readKillSwitch());
  }
  return unconfiguredSnapshot();
}
