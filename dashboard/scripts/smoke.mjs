#!/usr/bin/env node
/**
 * Lightweight smoke checks for the ops dashboard.
 * Ensures build artifacts / source never expose order-placement APIs.
 */
import { readdirSync, readFileSync, statSync } from "fs";
import { join } from "path";

const root = join(import.meta.dirname, "..");
const apiRoot = join(root, "src", "app", "api");

const FORBIDDEN = [
  /["'`]\/api\/orders?["'`]/i,
  /["'`]\/api\/execute["'`]/i,
  /["'`]\/api\/trade\/(open|close|place)["'`]/i,
  /order_send\s*\(/i,
];

function walk(dir) {
  const out = [];
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    const st = statSync(p);
    if (st.isDirectory()) out.push(...walk(p));
    else if (/\.(ts|tsx|js|mjs)$/.test(name)) out.push(p);
  }
  return out;
}

const apiDirs = readdirSync(apiRoot);
const allowed = new Set(["health", "auth", "journal", "kill-switch"]);
for (const name of apiDirs) {
  if (!allowed.has(name)) {
    console.error(`Unexpected API route group: ${name}`);
    process.exit(1);
  }
}

let hits = 0;
for (const file of walk(join(root, "src"))) {
  const text = readFileSync(file, "utf8");
  for (const re of FORBIDDEN) {
    if (re.test(text)) {
      console.error(`Forbidden pattern ${re} in ${file}`);
      hits += 1;
    }
  }
}

if (hits > 0) {
  process.exit(1);
}

console.log("smoke ok: api surface limited; no place-order endpoints");
