import { NextResponse } from "next/server";
import { getDataMode } from "@/lib/data";

/** Public liveness probe — no secrets, no journal payload. */
export async function GET() {
  return NextResponse.json({
    ok: true,
    service: "ght-dashboard",
    dataMode: getDataMode(),
    placesOrders: false,
  });
}
