import "server-only";

import { createClient } from "@supabase/supabase-js";
import postgres from "postgres";

import type { LiveBackend } from "./source";
import type {
  Decision,
  EngineStatus,
  JournalSnapshot,
  KillSwitchState,
  PnlSummary,
  Signal,
  SystemEvent,
  Trade,
} from "./types";

const ROW_LIMIT = 40;
const STALE_MS = 3 * 60 * 60 * 1000;

type Sql = ReturnType<typeof postgres>;

const globalForSql = globalThis as unknown as { journalSql?: Sql; journalSqlUrl?: string };

export function redactSecrets(text: string): string {
  let out = text.replace(/:\/\/([^:/@\s]+):([^@/\s]+)@/g, "://$1:***@");
  out = out.replace(/(password=)([^\s&]+)/gi, "$1***");
  const key = process.env.SUPABASE_SERVICE_ROLE_KEY?.trim();
  if (key && key.length > 6) out = out.split(key).join("***");
  const databaseUrl = process.env.DATABASE_URL?.trim();
  if (databaseUrl && databaseUrl.length > 6) out = out.split(databaseUrl).join("***");
  return out.slice(0, 500);
}

function asIso(value: unknown): string {
  if (value instanceof Date) return value.toISOString();
  if (typeof value === "string" && value.trim()) {
    const parsed = new Date(value);
    if (!Number.isNaN(parsed.getTime())) return parsed.toISOString();
    return value;
  }
  return new Date(0).toISOString();
}

function asIsoOrNull(value: unknown): string | null {
  if (value == null || value === "") return null;
  return asIso(value);
}

function asNum(value: unknown, fallback = 0): number {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) return parsed;
  }
  return fallback;
}

function asNumOrNull(value: unknown): number | null {
  if (value == null || value === "") return null;
  if (typeof value === "number") return Number.isFinite(value) ? value : null;
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function asBool(value: unknown): boolean {
  if (typeof value === "boolean") return value;
  if (value === 1 || value === "1" || value === "t" || value === "true") return true;
  return false;
}

function asText(value: unknown): string {
  if (value == null) return "";
  return String(value);
}

function mapDecision(row: Record<string, unknown>): Decision {
  return {
    id: asNum(row.id),
    createdAt: asIso(row.created_at),
    symbol: row.symbol == null || row.symbol === "" ? null : String(row.symbol),
    allowed: asBool(row.allowed),
    reason: asText(row.reason),
    action: asText(row.action),
    idempotencyKey: asText(row.idempotency_key),
  };
}

function mapTrade(row: Record<string, unknown>): Trade {
  return {
    id: asNum(row.id),
    createdAt: asIso(row.created_at),
    symbol: asText(row.symbol),
    side: asText(row.side),
    volume: asNum(row.volume),
    entryPrice: asNum(row.entry_price),
    exitPrice: asNumOrNull(row.exit_price),
    stopPrice: asNumOrNull(row.stop_price),
    takeProfit: asNumOrNull(row.take_profit),
    pnl: asNumOrNull(row.pnl),
    pnlR: asNumOrNull(row.pnl_r),
    ticket: asText(row.ticket),
    status: asText(row.status) || "open",
    openedAt: asIsoOrNull(row.opened_at),
    closedAt: asIsoOrNull(row.closed_at),
  };
}

function mapEvent(row: Record<string, unknown>): SystemEvent {
  return {
    id: asNum(row.id),
    createdAt: asIso(row.created_at),
    eventType: asText(row.event_type),
    message: asText(row.message),
  };
}

function mapSignal(row: Record<string, unknown>): Signal {
  return {
    id: asNum(row.id),
    createdAt: asIso(row.created_at),
    symbol: asText(row.symbol),
    strategy: asText(row.strategy),
    side: asText(row.side),
    entryPrice: asNum(row.entry_price),
    stopPrice: asNum(row.stop_price),
    takeProfit: asNumOrNull(row.take_profit),
    reason: asText(row.reason),
  };
}

function engineFromEvent(event: SystemEvent | null): EngineStatus {
  if (!event) {
    return {
      state: "unknown",
      lastEventType: null,
      lastEventAt: null,
      message: "No heartbeat yet. The Windows engine has not written system_events.",
    };
  }
  const age = Date.now() - new Date(event.createdAt).getTime();
  let state: EngineStatus["state"] = "unknown";
  if (event.eventType === "engine_down") state = "down";
  else if (event.eventType === "heartbeat" || event.eventType === "engine_up") {
    state = Number.isFinite(age) && age > STALE_MS ? "stale" : "up";
  }
  return {
    state,
    lastEventType: event.eventType,
    lastEventAt: event.createdAt,
    message: event.message,
  };
}

function emptyKillSwitch(): KillSwitchState {
  return {
    active: false,
    reason: "",
    engagedAt: null,
    updatedAt: new Date(0).toISOString(),
  };
}

function mapKillSwitch(row: Record<string, unknown> | undefined): KillSwitchState {
  if (!row) return emptyKillSwitch();
  return {
    active: asBool(row.active),
    reason: asText(row.reason),
    engagedAt: asIsoOrNull(row.engaged_at),
    updatedAt: asIso(row.updated_at),
  };
}

type JournalRows = {
  decisions: Decision[];
  trades: Trade[];
  signals: Signal[];
  systemEvents: SystemEvent[];
  killSwitch: KillSwitchState;
  pnl: PnlSummary;
  engine: EngineStatus;
};

function assemble(rows: JournalRows, note: string): JournalSnapshot {
  const openFirst = [...rows.trades].sort((a, b) => {
    const aOpen = a.status === "open" ? 0 : 1;
    const bOpen = b.status === "open" ? 0 : 1;
    return aOpen - bOpen;
  });
  const hasRows =
    rows.decisions.length + rows.trades.length + rows.signals.length + rows.systemEvents.length >
    0;
  return {
    mode: "live",
    generatedAt: new Date().toISOString(),
    note: hasRows
      ? note
      : "Connected to Postgres. The journal tables are empty until the Windows engine completes a cycle with DATABASE_URL set. This page does not place MT5 orders.",
    error: null,
    killSwitch: rows.killSwitch,
    killSwitchSource: "journal",
    decisions: rows.decisions,
    trades: openFirst,
    signals: rows.signals,
    systemEvents: rows.systemEvents,
    engine: rows.engine,
    pnl: rows.pnl,
  };
}

const LIVE_NOTE =
  "Live journal from Postgres (same tables as the Windows engine). Read-only on this page — it does not place MT5 orders.";

function sqlClient(url: string): Sql {
  if (globalForSql.journalSql && globalForSql.journalSqlUrl === url) {
    return globalForSql.journalSql;
  }
  if (globalForSql.journalSql) {
    void globalForSql.journalSql.end({ timeout: 1 });
  }
  const sql = postgres(url, {
    prepare: false,
    fetch_types: false,
    ssl: "require",
    max: 1,
    idle_timeout: 20,
    connect_timeout: 10,
    max_lifetime: 60,
    connection: {
      application_name: "ght-dashboard",
      statement_timeout: 8000,
    },
  });
  globalForSql.journalSql = sql;
  globalForSql.journalSqlUrl = url;
  return sql;
}

async function queryPostgres(url: string): Promise<JournalRows> {
  const sql = sqlClient(url);
  const [decisions, trades, signals, events, killRows, pnlRows] = await Promise.all([
    sql<Record<string, unknown>[]>`
      select id, created_at, symbol, allowed, reason, action, idempotency_key
      from decisions
      order by created_at desc
      limit ${ROW_LIMIT}
    `,
    sql<Record<string, unknown>[]>`
      select id, created_at, symbol, side, volume, entry_price, exit_price,
             stop_price, take_profit, pnl, pnl_r, ticket, status, opened_at, closed_at
      from trades
      order by created_at desc
      limit ${ROW_LIMIT}
    `,
    sql<Record<string, unknown>[]>`
      select id, created_at, symbol, strategy, side, entry_price, stop_price, take_profit, reason
      from signals
      order by created_at desc
      limit ${ROW_LIMIT}
    `,
    sql<Record<string, unknown>[]>`
      select id, created_at, event_type, message
      from system_events
      order by created_at desc
      limit ${ROW_LIMIT}
    `,
    sql<Record<string, unknown>[]>`
      select active, reason, engaged_at, updated_at
      from kill_switch_state
      where id = 1
    `,
    sql<Record<string, unknown>[]>`
      select
        count(*) filter (where status = 'open') as open_count,
        count(*) filter (where status <> 'open') as closed_count,
        coalesce(sum(pnl) filter (where status <> 'open'), 0) as closed_pnl
      from trades
    `,
  ]);
  const heartbeat = await sql<Record<string, unknown>[]>`
    select id, created_at, event_type, message
    from system_events
    where event_type in ('heartbeat', 'engine_up', 'engine_down')
    order by created_at desc
    limit 1
  `;
  const pnlRow = pnlRows[0] ?? {};
  const latestEngine = heartbeat[0] ? mapEvent(heartbeat[0]) : null;
  return {
    decisions: decisions.map(mapDecision),
    trades: trades.map(mapTrade),
    signals: signals.map(mapSignal),
    systemEvents: events.map(mapEvent),
    killSwitch: mapKillSwitch(killRows[0]),
    pnl: {
      openCount: asNum(pnlRow.open_count),
      closedCount: asNum(pnlRow.closed_count),
      closedPnl: asNum(pnlRow.closed_pnl),
    },
    engine: engineFromEvent(latestEngine),
  };
}

async function querySupabase(): Promise<JournalRows> {
  const url = process.env.SUPABASE_URL?.trim() ?? "";
  const key = process.env.SUPABASE_SERVICE_ROLE_KEY?.trim() ?? "";
  if (!url.startsWith("https://")) {
    throw new Error("SUPABASE_URL must be the https:// project URL from Supabase settings");
  }
  const client = createClient(url, key, {
    auth: { persistSession: false, autoRefreshToken: false },
  });

  const [decisions, trades, signals, events, killSwitch, heartbeat, pnlScan] = await Promise.all([
    client
      .from("decisions")
      .select("id, created_at, symbol, allowed, reason, action, idempotency_key")
      .order("created_at", { ascending: false })
      .limit(ROW_LIMIT),
    client
      .from("trades")
      .select(
        "id, created_at, symbol, side, volume, entry_price, exit_price, stop_price, take_profit, pnl, pnl_r, ticket, status, opened_at, closed_at",
      )
      .order("created_at", { ascending: false })
      .limit(ROW_LIMIT),
    client
      .from("signals")
      .select("id, created_at, symbol, strategy, side, entry_price, stop_price, take_profit, reason")
      .order("created_at", { ascending: false })
      .limit(ROW_LIMIT),
    client
      .from("system_events")
      .select("id, created_at, event_type, message")
      .order("created_at", { ascending: false })
      .limit(ROW_LIMIT),
    client
      .from("kill_switch_state")
      .select("active, reason, engaged_at, updated_at")
      .eq("id", 1)
      .maybeSingle(),
    client
      .from("system_events")
      .select("id, created_at, event_type, message")
      .in("event_type", ["heartbeat", "engine_up", "engine_down"])
      .order("created_at", { ascending: false })
      .limit(1)
      .maybeSingle(),
    client.from("trades").select("status, pnl").limit(5000),
  ]);

  for (const result of [decisions, trades, signals, events, killSwitch, heartbeat, pnlScan]) {
    if (result.error) {
      throw new Error(result.error.message);
    }
  }

  const tradeRows = (trades.data ?? []) as Record<string, unknown>[];
  let openCount = 0;
  let closedCount = 0;
  let closedPnl = 0;
  for (const row of (pnlScan.data ?? []) as Record<string, unknown>[]) {
    const status = asText(row.status);
    if (status === "open") openCount += 1;
    else {
      closedCount += 1;
      const pnl = asNumOrNull(row.pnl);
      if (pnl != null) closedPnl += pnl;
    }
  }

  const heartbeatRow = heartbeat.data as Record<string, unknown> | null;
  return {
    decisions: ((decisions.data ?? []) as Record<string, unknown>[]).map(mapDecision),
    trades: tradeRows.map(mapTrade),
    signals: ((signals.data ?? []) as Record<string, unknown>[]).map(mapSignal),
    systemEvents: ((events.data ?? []) as Record<string, unknown>[]).map(mapEvent),
    killSwitch: mapKillSwitch((killSwitch.data as Record<string, unknown> | null) ?? undefined),
    pnl: { openCount, closedCount, closedPnl },
    engine: engineFromEvent(heartbeatRow ? mapEvent(heartbeatRow) : null),
  };
}

export async function loadLiveSnapshot(backend: Exclude<LiveBackend, "none" | "invalid">): Promise<JournalSnapshot> {
  const rows = backend === "postgres" ? await queryPostgres(process.env.DATABASE_URL!.trim()) : await querySupabase();
  const via = backend === "postgres" ? "DATABASE_URL" : "SUPABASE_SERVICE_ROLE_KEY";
  return assemble(rows, `${LIVE_NOTE} Source: ${via}.`);
}

export function explainQueryFailure(err: unknown): string {
  const code =
    typeof err === "object" && err !== null && "code" in err ? String((err as { code: unknown }).code) : "";
  const message = redactSecrets(err instanceof Error ? err.message : String(err));
  if (
    code === "42P01" ||
    /does not exist/i.test(message) ||
    /schema cache/i.test(message) ||
    /could not find the table/i.test(message)
  ) {
    return (
      "Could not read the journal because the tables are missing. " +
      "Start the Windows engine once with DATABASE_URL set (session pooler, port 5432) so it can create them, then reload. " +
      message
    );
  }
  return (
    "Could not read the journal from Postgres. The dashboard did not substitute sample trades. " +
    "Check Vercel DATABASE_URL (Supabase transaction pooler, port 6543) or SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY, then redeploy. " +
    message
  );
}
