"use client";

import { FormEvent, useState, useTransition } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense } from "react";

function LoginForm() {
  const router = useRouter();
  const search = useSearchParams();
  const nextPath = search.get("next") || "/";
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    startTransition(async () => {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password }),
      });
      if (!res.ok) {
        setError("Invalid password");
        return;
      }
      router.replace(nextPath.startsWith("/") ? nextPath : "/");
      router.refresh();
    });
  }

  return (
    <form
      onSubmit={onSubmit}
      className="w-full max-w-sm border border-[var(--border)] bg-[var(--bg-panel)] p-6"
    >
      <label className="flex flex-col gap-2 text-sm">
        <span className="text-[var(--text-dim)]">Dashboard password</span>
        <input
          type="password"
          name="password"
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="border border-[var(--border-strong)] bg-[var(--bg)] px-3 py-2 outline-none focus:border-[var(--accent)]"
          required
        />
      </label>
      {error ? (
        <p className="mt-3 mb-0 text-sm text-[var(--danger)]" role="alert">
          {error}
        </p>
      ) : null}
      <button
        type="submit"
        disabled={pending}
        className="mt-4 w-full border border-[var(--accent)] bg-[var(--accent-dim)] px-4 py-2.5 text-sm font-semibold text-[var(--text)] transition hover:bg-[var(--accent)] disabled:opacity-50"
      >
        {pending ? "Checking…" : "Enter"}
      </button>
    </form>
  );
}

export default function LoginPage() {
  return (
    <main className="mx-auto flex min-h-screen max-w-lg flex-col justify-center px-4 py-10">
      <p className="m-0 text-xs font-semibold uppercase tracking-[0.18em] text-[var(--accent)]">
        ght.systems
      </p>
      <h1 className="mt-2 mb-1 text-2xl font-semibold">Ops dashboard</h1>
      <p className="mt-0 mb-6 text-sm text-[var(--text-muted)]">
        Password gate via <code className="font-mono">DASHBOARD_PASSWORD</code>.
        Read-only monitoring — no order placement.
      </p>
      <Suspense
        fallback={
          <div className="h-40 border border-[var(--border)] bg-[var(--bg-panel)]" />
        }
      >
        <LoginForm />
      </Suspense>
    </main>
  );
}
