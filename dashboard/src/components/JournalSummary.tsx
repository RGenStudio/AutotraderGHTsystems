import type { EngineStatus, PnlSummary } from "@/lib/types";
import { formatPnl, formatUtc } from "./format";

function engineLabel(state: EngineStatus["state"]): string {
  if (state === "up") return "Up";
  if (state === "down") return "Down";
  if (state === "stale") return "Stale";
  return "Unknown";
}

function engineClass(state: EngineStatus["state"]): string {
  if (state === "up") return "text-[var(--ok)]";
  if (state === "down") return "text-[var(--danger)]";
  if (state === "stale") return "text-[var(--warn)]";
  return "text-[var(--text-muted)]";
}

export function JournalSummary({
  engine,
  pnl,
}: {
  engine: EngineStatus;
  pnl: PnlSummary;
}) {
  const cards = [
    {
      label: "Engine",
      value: engineLabel(engine.state),
      valueClass: engineClass(engine.state),
      detail: engine.lastEventAt
        ? `${engine.lastEventType ?? "event"} ${formatUtc(engine.lastEventAt)}`
        : engine.message,
    },
    {
      label: "Open trades",
      value: String(pnl.openCount),
      valueClass: "text-[var(--text)]",
      detail: "status = open",
    },
    {
      label: "Closed trades",
      value: String(pnl.closedCount),
      valueClass: "text-[var(--text)]",
      detail: "paper fills in the journal",
    },
    {
      label: "Paper PnL",
      value: formatPnl(pnl.closedPnl),
      valueClass:
        pnl.closedPnl == null
          ? "text-[var(--text-muted)]"
          : pnl.closedPnl >= 0
            ? "text-[var(--ok)]"
            : "text-[var(--danger)]",
      detail: "sum of closed trades.pnl",
    },
  ];

  return (
    <section aria-label="Journal summary" className="grid grid-cols-2 gap-3 sm:grid-cols-4">
      {cards.map((card) => (
        <article
          key={card.label}
          className="border border-[var(--border)] bg-[var(--bg-panel)] px-3 py-3 sm:px-4"
        >
          <p className="m-0 text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-dim)]">
            {card.label}
          </p>
          <p className={`mt-1 mb-0 font-mono text-xl tabular ${card.valueClass}`}>{card.value}</p>
          <p className="mt-1 mb-0 text-[12px] text-[var(--text-muted)]">{card.detail}</p>
        </article>
      ))}
    </section>
  );
}
