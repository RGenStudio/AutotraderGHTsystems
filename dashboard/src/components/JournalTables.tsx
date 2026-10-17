import type { Decision, SystemEvent, Trade } from "@/lib/types";
import { formatNum, formatPnl, formatUtc } from "./format";

function EmptyRow({ cols, label }: { cols: number; label: string }) {
  return (
    <tr>
      <td
        colSpan={cols}
        className="px-3 py-6 text-center text-sm text-[var(--text-dim)]"
      >
        {label}
      </td>
    </tr>
  );
}

export function DecisionsTable({ rows }: { rows: Decision[] }) {
  return (
    <section className="border border-[var(--border)] bg-[var(--bg-panel)]">
      <header className="border-b border-[var(--border)] px-4 py-3">
        <h2 className="m-0 text-sm font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
          Recent decisions
        </h2>
      </header>
      <div className="overflow-x-auto">
        <table className="min-w-[640px] text-left text-sm">
          <thead className="text-[11px] uppercase tracking-wide text-[var(--text-dim)]">
            <tr className="border-b border-[var(--border)]">
              <th className="px-3 py-2 font-medium">UTC</th>
              <th className="px-3 py-2 font-medium">Symbol</th>
              <th className="px-3 py-2 font-medium">Allowed</th>
              <th className="px-3 py-2 font-medium">Reason</th>
              <th className="px-3 py-2 font-medium">Action</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <EmptyRow cols={5} label="No decisions" />
            ) : (
              rows.map((row) => (
                <tr
                  key={row.id}
                  className="border-b border-[var(--border)]/70 last:border-0"
                >
                  <td className="px-3 py-2 font-mono text-[12px] tabular text-[var(--text-muted)]">
                    {formatUtc(row.createdAt)}
                  </td>
                  <td className="px-3 py-2 font-mono">{row.symbol ?? "—"}</td>
                  <td className="px-3 py-2">
                    <span
                      className={
                        row.allowed
                          ? "text-[var(--ok)]"
                          : "text-[var(--warn)]"
                      }
                    >
                      {row.allowed ? "yes" : "no"}
                    </span>
                  </td>
                  <td className="px-3 py-2 font-mono text-[12px]">{row.reason}</td>
                  <td className="px-3 py-2 font-mono text-[12px] text-[var(--text-muted)]">
                    {row.action || "—"}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export function TradesTable({ rows }: { rows: Trade[] }) {
  return (
    <section className="border border-[var(--border)] bg-[var(--bg-panel)]">
      <header className="border-b border-[var(--border)] px-4 py-3">
        <h2 className="m-0 text-sm font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
          Recent trades
        </h2>
      </header>
      <div className="overflow-x-auto">
        <table className="min-w-[720px] text-left text-sm">
          <thead className="text-[11px] uppercase tracking-wide text-[var(--text-dim)]">
            <tr className="border-b border-[var(--border)]">
              <th className="px-3 py-2 font-medium">Opened</th>
              <th className="px-3 py-2 font-medium">Symbol</th>
              <th className="px-3 py-2 font-medium">Side</th>
              <th className="px-3 py-2 font-medium">Vol</th>
              <th className="px-3 py-2 font-medium">Entry</th>
              <th className="px-3 py-2 font-medium">PnL</th>
              <th className="px-3 py-2 font-medium">Status</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <EmptyRow cols={7} label="No trades" />
            ) : (
              rows.map((row) => (
                <tr
                  key={row.id}
                  className="border-b border-[var(--border)]/70 last:border-0"
                >
                  <td className="px-3 py-2 font-mono text-[12px] tabular text-[var(--text-muted)]">
                    {formatUtc(row.openedAt ?? row.createdAt)}
                  </td>
                  <td className="px-3 py-2 font-mono">{row.symbol}</td>
                  <td className="px-3 py-2 font-mono">{row.side}</td>
                  <td className="px-3 py-2 font-mono tabular">
                    {formatNum(row.volume, 2)}
                  </td>
                  <td className="px-3 py-2 font-mono tabular">
                    {formatNum(row.entryPrice, 5)}
                  </td>
                  <td
                    className={`px-3 py-2 font-mono tabular ${
                      row.pnl !== null && row.pnl !== undefined
                        ? row.pnl >= 0
                          ? "text-[var(--ok)]"
                          : "text-[var(--danger)]"
                        : ""
                    }`}
                  >
                    {formatPnl(row.pnl)}
                    {row.pnlR !== null && row.pnlR !== undefined
                      ? ` (${formatPnl(row.pnlR)}R)`
                      : ""}
                  </td>
                  <td className="px-3 py-2 font-mono text-[12px]">{row.status}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export function EventsTable({ rows }: { rows: SystemEvent[] }) {
  return (
    <section className="border border-[var(--border)] bg-[var(--bg-panel)]">
      <header className="border-b border-[var(--border)] px-4 py-3">
        <h2 className="m-0 text-sm font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
          System events
        </h2>
      </header>
      <div className="overflow-x-auto">
        <table className="min-w-[560px] text-left text-sm">
          <thead className="text-[11px] uppercase tracking-wide text-[var(--text-dim)]">
            <tr className="border-b border-[var(--border)]">
              <th className="px-3 py-2 font-medium">UTC</th>
              <th className="px-3 py-2 font-medium">Type</th>
              <th className="px-3 py-2 font-medium">Message</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <EmptyRow cols={3} label="No events" />
            ) : (
              rows.map((row) => (
                <tr
                  key={row.id}
                  className="border-b border-[var(--border)]/70 last:border-0"
                >
                  <td className="px-3 py-2 font-mono text-[12px] tabular text-[var(--text-muted)]">
                    {formatUtc(row.createdAt)}
                  </td>
                  <td className="px-3 py-2 font-mono text-[12px]">{row.eventType}</td>
                  <td className="px-3 py-2 text-[var(--text-muted)]">{row.message}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}
