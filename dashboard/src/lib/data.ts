import { DEMO_DECISIONS, DEMO_EVENTS, DEMO_NOTE, DEMO_TRADES } from "./demo-data";
import { readKillSwitch } from "./kill-switch-store";
import type { Decision, JournalSnapshot, SystemEvent, Trade } from "./types";

export type DataMode = "demo" | "api";

export function getDataMode(): DataMode {
  const raw = (process.env.DASHBOARD_DATA_MODE ?? "demo").trim().toLowerCase();
  return raw === "api" ? "api" : "demo";
}

function demoSnapshot(killSwitch: JournalSnapshot["killSwitch"]): JournalSnapshot {
  return {
    mode: "demo",
    generatedAt: new Date().toISOString(),
    note: DEMO_NOTE,
    killSwitch,
    decisions: DEMO_DECISIONS,
    trades: DEMO_TRADES,
    systemEvents: DEMO_EVENTS,
  };
}

/**
 * Optional `api` mode: fetch JSON from ENGINE_JOURNAL_URL (HTTPS).
 * Expected shape matches JournalSnapshot fields (decisions/trades/systemEvents).
 * When unset or fetch fails, falls back to demo with a note — never invents orders.
 */
async function apiSnapshot(
  killSwitch: JournalSnapshot["killSwitch"],
): Promise<JournalSnapshot> {
  const url = process.env.ENGINE_JOURNAL_URL?.trim();
  if (!url) {
    return {
      ...demoSnapshot(killSwitch),
      mode: "api",
      note:
        "DASHBOARD_DATA_MODE=api but ENGINE_JOURNAL_URL is unset — showing demo data. Wire Supabase/engine sync later.",
    };
  }

  try {
    const res = await fetch(url, {
      headers: { Accept: "application/json" },
      next: { revalidate: 30 },
    });
    if (!res.ok) {
      throw new Error(`journal HTTP ${res.status}`);
    }
    const body = (await res.json()) as {
      decisions?: Decision[];
      trades?: Trade[];
      systemEvents?: SystemEvent[];
      killSwitch?: JournalSnapshot["killSwitch"];
      note?: string;
    };
    return {
      mode: "api",
      generatedAt: new Date().toISOString(),
      note:
        body.note ??
        "Live journal feed via ENGINE_JOURNAL_URL. Dashboard still cannot place MT5 orders.",
      killSwitch: body.killSwitch ?? killSwitch,
      decisions: body.decisions ?? [],
      trades: body.trades ?? [],
      systemEvents: body.systemEvents ?? [],
    };
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    return {
      ...demoSnapshot(killSwitch),
      mode: "api",
      note: `ENGINE_JOURNAL_URL fetch failed (${message}) — demo fallback. Production sync via Supabase is later.`,
    };
  }
}

export async function loadJournal(): Promise<JournalSnapshot> {
  const killSwitch = await readKillSwitch();
  if (getDataMode() === "api") {
    return apiSnapshot(killSwitch);
  }
  return demoSnapshot(killSwitch);
}
