"use client";

import { useState, useTransition } from "react";
import type { KillSwitchState } from "@/lib/types";
import { formatUtc } from "./format";

type Props = {
  initial: KillSwitchState;
  onChanged?: (state: KillSwitchState) => void;
};

export function KillSwitchPanel({ initial, onChanged }: Props) {
  const [state, setState] = useState(initial);
  const [reason, setReason] = useState("dashboard_operator");
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

  function apply(next: KillSwitchState) {
    setState(next);
    onChanged?.(next);
  }

  function post(action: "engage" | "clear") {
    setError(null);
    startTransition(async () => {
      try {
        const res = await fetch("/api/kill-switch", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            action,
            reason: action === "engage" ? reason : undefined,
          }),
        });
        const body = (await res.json()) as KillSwitchState & { error?: string };
        if (!res.ok) {
          setError(body.error ?? `HTTP ${res.status}`);
          return;
        }
        apply(body);
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      }
    });
  }

  return (
    <section
      aria-labelledby="kill-switch-heading"
      className="border border-[var(--border)] bg-[var(--bg-panel)] p-4 sm:p-5"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2
            id="kill-switch-heading"
            className="m-0 text-sm font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]"
          >
            Kill switch
          </h2>
          <p className="mt-1 mb-0 text-sm text-[var(--text-dim)]">
            Pauses new entries in the dashboard flag. Does not place or cancel MT5
            orders.
          </p>
        </div>
        <span
          className={`inline-flex items-center gap-2 border px-2.5 py-1 text-xs font-semibold uppercase tracking-wide ${
            state.active
              ? "border-[var(--danger)] text-[var(--danger)]"
              : "border-[var(--ok)] text-[var(--ok)]"
          }`}
        >
          <span
            className={`h-2 w-2 ${state.active ? "bg-[var(--danger)]" : "bg-[var(--ok)]"}`}
            aria-hidden
          />
          {state.active ? "Engaged" : "Clear"}
        </span>
      </div>

      <dl className="mt-4 grid gap-2 text-sm sm:grid-cols-2">
        <div>
          <dt className="text-[var(--text-dim)]">Reason</dt>
          <dd className="m-0 font-mono text-[13px]">
            {state.active ? state.reason || "—" : "—"}
          </dd>
        </div>
        <div>
          <dt className="text-[var(--text-dim)]">Engaged at (UTC)</dt>
          <dd className="m-0 font-mono text-[13px] tabular">
            {formatUtc(state.engagedAt)}
          </dd>
        </div>
      </dl>

      <div className="mt-4 flex flex-col gap-3 sm:flex-row sm:items-end">
        <label className="flex min-w-0 flex-1 flex-col gap-1 text-sm">
          <span className="text-[var(--text-dim)]">Engage reason</span>
          <input
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            disabled={pending || state.active}
            className="border border-[var(--border-strong)] bg-[var(--bg)] px-3 py-2 text-[var(--text)] outline-none focus:border-[var(--accent)] disabled:opacity-50"
            placeholder="operator review"
            maxLength={200}
          />
        </label>
        <div className="flex gap-2">
          <button
            type="button"
            disabled={pending || state.active}
            onClick={() => post("engage")}
            className="border border-[var(--danger)] bg-transparent px-4 py-2 text-sm font-semibold text-[var(--danger)] transition hover:bg-[var(--danger)] hover:text-[var(--bg)] disabled:cursor-not-allowed disabled:opacity-40"
          >
            Engage
          </button>
          <button
            type="button"
            disabled={pending || !state.active}
            onClick={() => post("clear")}
            className="border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-4 py-2 text-sm font-semibold text-[var(--text)] transition hover:border-[var(--accent)] disabled:cursor-not-allowed disabled:opacity-40"
          >
            Clear
          </button>
        </div>
      </div>
      {error ? (
        <p className="mt-3 mb-0 text-sm text-[var(--danger)]" role="alert">
          {error}
        </p>
      ) : null}
    </section>
  );
}
