export default function Loading() {
  return (
    <div className="mx-auto min-h-screen max-w-6xl px-4 py-6 sm:px-6 sm:py-8">
      <p className="m-0 text-xs font-semibold uppercase tracking-[0.18em] text-[var(--accent)]">
        ght.systems
      </p>
      <h1 className="mt-1 mb-0 text-2xl font-semibold tracking-tight sm:text-3xl">
        AutoTrader ops
      </h1>
      <p className="mt-4 mb-0 text-sm text-[var(--text-muted)]" role="status">
        Loading the journal…
      </p>
    </div>
  );
}
