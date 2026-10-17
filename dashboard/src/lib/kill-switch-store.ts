import { promises as fs } from "fs";
import path from "path";
import type { KillSwitchState } from "./types";

/**
 * Demo/local kill-switch persistence.
 * On Vercel serverless the writable path is /tmp (ephemeral across instances).
 * Production journal sync (Supabase) is a later milestone — this only gates the UI flag.
 */

const DEFAULT_STATE: KillSwitchState = {
  active: false,
  reason: "",
  engagedAt: null,
  updatedAt: new Date(0).toISOString(),
};

function storePath(): string {
  const override = process.env.DASHBOARD_KILL_SWITCH_PATH?.trim();
  if (override) return override;
  // Prefer /tmp on serverless; fall back to .data under cwd for local dev.
  const base =
    process.env.VERCEL || process.env.AWS_LAMBDA_FUNCTION_NAME
      ? "/tmp"
      : path.join(process.cwd(), ".data");
  return path.join(base, "kill-switch.json");
}

async function ensureDir(filePath: string): Promise<void> {
  await fs.mkdir(path.dirname(filePath), { recursive: true });
}

export async function readKillSwitch(): Promise<KillSwitchState> {
  const file = storePath();
  try {
    const raw = await fs.readFile(file, "utf8");
    const parsed = JSON.parse(raw) as KillSwitchState;
    return {
      active: Boolean(parsed.active),
      reason: typeof parsed.reason === "string" ? parsed.reason : "",
      engagedAt: parsed.engagedAt ?? null,
      updatedAt: parsed.updatedAt ?? new Date().toISOString(),
    };
  } catch {
    return { ...DEFAULT_STATE, updatedAt: new Date().toISOString() };
  }
}

export async function writeKillSwitch(state: KillSwitchState): Promise<KillSwitchState> {
  const file = storePath();
  await ensureDir(file);
  const next: KillSwitchState = {
    ...state,
    updatedAt: new Date().toISOString(),
  };
  await fs.writeFile(file, JSON.stringify(next, null, 2), "utf8");
  return next;
}

export async function engageKillSwitch(reason: string): Promise<KillSwitchState> {
  const trimmed = reason.trim();
  if (!trimmed) {
    throw new Error("kill switch reason must be non-empty");
  }
  const current = await readKillSwitch();
  if (current.active) {
    return current;
  }
  return writeKillSwitch({
    active: true,
    reason: trimmed,
    engagedAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
  });
}

export async function clearKillSwitch(): Promise<KillSwitchState> {
  return writeKillSwitch({
    active: false,
    reason: "",
    engagedAt: null,
    updatedAt: new Date().toISOString(),
  });
}
