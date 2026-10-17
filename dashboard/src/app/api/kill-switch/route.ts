import { NextRequest, NextResponse } from "next/server";
import {
  clearKillSwitch,
  engageKillSwitch,
  readKillSwitch,
} from "@/lib/kill-switch-store";

/**
 * Kill-switch control only.
 * This app exposes no MT5 order or execution APIs.
 * Engaging here sets a dashboard flag (demo file /tmp). Engine-side sync via
 * Supabase or shared store is a later milestone.
 */

export async function GET() {
  const state = await readKillSwitch();
  return NextResponse.json(state);
}

export async function POST(request: NextRequest) {
  let action = "";
  let reason = "";
  const contentType = request.headers.get("content-type") ?? "";
  if (contentType.includes("application/json")) {
    const body = (await request.json()) as { action?: string; reason?: string };
    action = (body.action ?? "").trim().toLowerCase();
    reason = body.reason ?? "";
  } else {
    const form = await request.formData();
    action = String(form.get("action") ?? "")
      .trim()
      .toLowerCase();
    reason = String(form.get("reason") ?? "");
  }

  try {
    if (action === "engage") {
      const state = await engageKillSwitch(reason || "dashboard_operator");
      return NextResponse.json(state);
    }
    if (action === "clear") {
      const state = await clearKillSwitch();
      return NextResponse.json(state);
    }
    return NextResponse.json(
      { error: "action must be engage or clear" },
      { status: 400 },
    );
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    return NextResponse.json({ error: message }, { status: 400 });
  }
}
