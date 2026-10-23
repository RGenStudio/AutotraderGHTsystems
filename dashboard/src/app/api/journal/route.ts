import { NextResponse } from "next/server";
import { loadJournal } from "@/lib/data";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

/** Read-only journal snapshot. Never accepts order payloads. */
export async function GET() {
  const snapshot = await loadJournal();
  return NextResponse.json(snapshot);
}
