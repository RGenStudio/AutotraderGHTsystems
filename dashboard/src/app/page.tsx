import { isAuthConfigured } from "@/lib/auth";
import { loadJournal } from "@/lib/data";
import { DashboardShell } from "@/components/DashboardShell";

export const dynamic = "force-dynamic";

export default async function HomePage() {
  const snapshot = await loadJournal();
  return (
    <DashboardShell
      snapshot={snapshot}
      authConfigured={isAuthConfigured()}
    />
  );
}
