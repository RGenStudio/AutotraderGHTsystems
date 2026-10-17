"use client";

import { useRouter } from "next/navigation";
import { useTransition } from "react";

export function LogoutButton() {
  const router = useRouter();
  const [pending, startTransition] = useTransition();

  return (
    <button
      type="button"
      disabled={pending}
      onClick={() => {
        startTransition(async () => {
          await fetch("/api/auth/logout", { method: "POST" });
          router.push("/login");
          router.refresh();
        });
      }}
      className="border border-[var(--border)] px-3 py-1.5 text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)] transition hover:border-[var(--border-strong)] hover:text-[var(--text)] disabled:opacity-50"
    >
      Log out
    </button>
  );
}
