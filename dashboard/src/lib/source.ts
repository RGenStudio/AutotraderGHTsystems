import "server-only";

/**
 * Where the dashboard reads the journal from.
 * Never expose DATABASE_URL or the service-role key to the browser.
 */

export type DataSource = "live" | "demo" | "unconfigured" | "misconfigured";

export type LiveBackend = "postgres" | "supabase" | "invalid" | "none";

function postgresUri(value: string | undefined): boolean {
  const raw = value?.trim() ?? "";
  return /^postgres(ql)?:\/\//i.test(raw);
}

/** Which server-side credential, if any, can read the journal. */
export function liveBackend(): LiveBackend {
  const databaseUrl = process.env.DATABASE_URL?.trim() ?? "";
  if (databaseUrl) {
    return postgresUri(databaseUrl) ? "postgres" : "invalid";
  }
  const supabaseUrl = process.env.SUPABASE_URL?.trim() ?? "";
  const serviceKey = process.env.SUPABASE_SERVICE_ROLE_KEY?.trim() ?? "";
  if (supabaseUrl && serviceKey) return "supabase";
  return "none";
}

/**
 * Vercel without database env is "unconfigured" even if DASHBOARD_DATA_MODE=demo,
 * so https://ght.systems does not present sample trades as the journal.
 * Local `next dev` still shows demo data unless the mode is set to something else.
 */
export function describeDataSource(): DataSource {
  const backend = liveBackend();
  if (backend === "invalid") return "misconfigured";
  if (backend === "postgres" || backend === "supabase") return "live";
  if (process.env.VERCEL === "1") return "unconfigured";
  const raw = (process.env.DASHBOARD_DATA_MODE ?? "demo").trim().toLowerCase();
  return raw === "demo" ? "demo" : "unconfigured";
}

export function getDataMode(): DataSource {
  return describeDataSource();
}
