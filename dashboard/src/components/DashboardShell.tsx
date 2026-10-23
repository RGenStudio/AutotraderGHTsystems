"use client";

import { useState } from "react";
import type { JournalSnapshot } from "@/lib/types";
import { KillSwitchPanel } from "./KillSwitchPanel";
import { JournalSummary } from "./JournalSummary";
import { DecisionsTable, EventsTable, SignalsTable, TradesTable } from "./JournalTables";
import { LogoutButton } from "./LogoutButton";
import { formatUtc } from "./format";

type Props = {
  snapshot: JournalSnapshot;
  authConfigured: boolean;
};

export function DashboardShell({ snapshot, authConfigured }: Props) {
  const [killSwitch, setKillSwitch] = useState(snapshot.killSwitch);
  const journalOwned = snapshot.killSwitchSource === "journal";
  const bannerClass =
    snapshot.mode === "error"
      ? "border-[var(--danger)]"
      : snapshot.mode === "live"
        ? "border-[var(--ok)]"
        : "border-[var(--warn)]";
  const empty =
    snapshot.mode === "live"
      ? {
          decisions: "No decisions in the journal yet",
          trades: "No trades in the journal yet",
          signals: "No signals in the journal yet",
          events: "No system events yet",
        }
      : snapshot.mode === "demo"
        ? {
            decisions: "No decisions",
            trades: "No trades",
            signals: "No signals",
            events: "No events",
          }
        : {
            decisions: "Not loaded",
            trades: "Not loaded",
            signals: "Not loaded",
            events: "Not loaded",
          };

  return (
    <div className="mx-auto min-h-screen max-w-6xl px-4 py-6 sm:px-6 sm:py-8">
      <header className="mb-6 flex flex-wrap items-end justify-between gap-4 border-b border-[var(--border)] pb-5">
        <div>
          <p className="m-0 text-xs font-semibold uppercase tracking-[0.18em] text-[var(--accent)]">
            ght.systems
          </p>
          <h1 className="mt-1 mb-0 text-2xl font-semibold tracking-tight sm:text-3xl">
            AutoTrader ops
          </h1>
          <p className="mt-2 mb-0 max-w-xl text-sm text-[var(--text-muted)]">
            Read-only journal view + kill switch. Python engine on Windows remains
            source of truth — this app cannot send MT5 orders.
          </p>
        </div>
        <div className="flex flex-col items-end gap-2 text-right">
          <div className="flex flex-wrap items-center justify-end gap-2">
            <span className="border border-[var(--border)] px-2 py-1 font-mono text-[11px] uppercase tracking-wide text-[var(--text-muted)]">
              mode={snapshot.mode}
            </span>
            <span className="border border-[var(--border)] px-2 py-1 font-mono text-[11px] uppercase tracking-wide text-[var(--text-muted)]">
              paper
            </span>
            {authConfigured ? <LogoutButton /> : null}
          </div>
          <p className="m-0 font-mono text-[11px] text-[var(--text-dim)]">
            snapshot {formatUtc(snapshot.generatedAt)}
          </p>
        </div>
      </header>

      <p
        className={`mb-5 border-l-2 bg-[var(--bg-elevated)] px-3 py-2 text-sm text-[var(--text-muted)] ${bannerClass}`}
        role={snapshot.mode === "error" ? "alert" : "status"}
      >
        {snapshot.note}
      </p>

      <div className="mb-6">
        <JournalSummary engine={snapshot.engine} pnl={snapshot.pnl} />
      </div>

      <div className="mb-6">
        <KillSwitchPanel
          initial={journalOwned ? snapshot.killSwitch : killSwitch}
          onChanged={journalOwned ? undefined : setKillSwitch}
          readOnly={journalOwned}
        />
      </div>

      <div className="grid gap-5">
        <TradesTable rows={snapshot.trades} emptyLabel={empty.trades} />
        <DecisionsTable rows={snapshot.decisions} emptyLabel={empty.decisions} />
        <SignalsTable rows={snapshot.signals} emptyLabel={empty.signals} />
        <EventsTable rows={snapshot.systemEvents} emptyLabel={empty.events} />
      </div>

      <footer className="mt-8 border-t border-[var(--border)] pt-4 text-xs text-[var(--text-dim)]">
        Not financial advice. Demo / paper monitoring only. Endpoints:{" "}
        <code className="font-mono text-[var(--text-muted)]">GET /api/journal</code>,{" "}
        <code className="font-mono text-[var(--text-muted)]">
          GET|POST /api/kill-switch
        </code>
        . No order/execution APIs.
      </footer>
    </div>
  );
}
