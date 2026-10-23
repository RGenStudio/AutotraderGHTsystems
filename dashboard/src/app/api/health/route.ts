import { NextResponse } from "next/server";
import { describeDataSource } from "@/lib/source";

/** Public liveness probe — no secrets, no journal payload. */
export async function GET() {
  return NextResponse.json({
    ok: true,
    service: "ght-dashboard",
    dataMode: describeDataSource(),
    placesOrders: false,
  });
}
