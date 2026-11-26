// Shared by the Frametrace edge functions: the admin client, validation, hashing, replies.
// The functions use the service role; the tables have RLS on and no policies, so nothing
// else can read or write them.

import { createClient, type SupabaseClient } from "npm:@supabase/supabase-js@2";

export const SCHEMA = 1;
export const MAX_BODY_BYTES = 512 * 1024; // the JSON bundle; the CSV goes straight to storage
export const MAX_CSV_BYTES = 50 * 1024 * 1024; // the bucket's own limit
export const DAILY_LIMIT = 2000; // submissions per contributor per 24 h
// CSVs wait in the bucket until the daily export moves them out. These caps keep a large
// first-time backfill inside the free plan's 1 GB (about 3 MB per CSV): over them, the app is
// told to send the CSV later; the JSON still goes in at once.
export const CSV_WAITING_PER_CONTRIBUTOR = 40;
export const CSV_WAITING_TOTAL = 250;
export const PUBLIC_KEY_LEN = 16; // hex characters of the contributor key in the public dataset

const UUID4 = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const LOCAL_ID = /^[A-Za-z0-9._~-]{1,170}$/;
const HEX64 = /^[0-9a-f]{64}$/;

export function admin(): SupabaseClient {
  const url = Deno.env.get("SUPABASE_URL")!;
  let key = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");
  if (!key) {
    const keys = JSON.parse(Deno.env.get("SUPABASE_SECRET_KEYS") ?? "{}");
    key = keys["default"];
  }
  return createClient(url, key!, { auth: { persistSession: false } });
}

export function reply(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", "Cache-Control": "no-store" },
  });
}

export async function readJson(req: Request): Promise<Record<string, unknown> | Response> {
  if (req.method !== "POST") return reply({ error: "POST only" }, 405);
  const text = await req.text();
  if (text.length > MAX_BODY_BYTES) return reply({ error: "request too large" }, 413);
  try {
    const body = JSON.parse(text);
    if (body && typeof body === "object" && !Array.isArray(body)) return body;
  } catch {
    // fall through
  }
  return reply({ error: "the body must be a JSON object" }, 400);
}

export const validInstall = (v: unknown): v is string => typeof v === "string" && UUID4.test(v);
export const validLocalId = (v: unknown): v is string => typeof v === "string" && LOCAL_ID.test(v);
export const validSha = (v: unknown): v is string => typeof v === "string" && HEX64.test(v);

function hex(buf: ArrayBuffer): string {
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

export async function sha256(text: string): Promise<string> {
  return hex(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text)));
}

let saltCache: string | null = null;

/** The contributor key: HMAC-SHA256 of the install ID with a salt only the database knows. */
export async function contributor(db: SupabaseClient, install: string): Promise<string> {
  if (!saltCache) {
    const { data, error } = await db
      .from("config")
      .select("value")
      .eq("key", "contributor_salt")
      .single();
    if (error || !data) throw new Error("contributor salt missing");
    saltCache = data.value as string;
  }
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(saltCache),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const sig = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(install.toLowerCase()));
  return hex(sig);
}

const short = (v: unknown, n = 120) => (typeof v === "string" && v ? v.slice(0, n) : null);

/** Columns the export and queries filter on, copied out of a capture bundle. */
export function captureColumns(data: Record<string, any>) {
  const game = data.game ?? {};
  const system = data.system ?? {};
  const gpus: Array<Record<string, any>> = Array.isArray(system.gpus) ? system.gpus : [];
  const discrete = gpus.find((g) => /\b(RTX|GTX|Radeon RX|RX \d|Arc [AB]\d)/i.test(g?.name ?? ""));
  return {
    game: short(game.name) ?? short(game.exe),
    exe: short((game.exe ?? data.capture?.app ?? "").toLowerCase()),
    store_id: short(game.store_id, 40),
    build: short(game.build, 40),
    gpu: short((discrete ?? gpus[0])?.name),
    cpu: short(system.cpu),
  };
}
