// POST /functions/v1/export, called only by the export workflow of github.com/melle62/frametrace-data.
//
// Authentication: a GitHub Actions OIDC token in the `x-github-oidc` header, audience
// "frametrace-export", issued to the main branch of that repository. No shared secret exists.
//
// {"action": "pull", "limit": 100, "after": "<updated_at of the last row seen>"}
//   -> {"rows": [...], "deletions": [{"contributor": "<16 hex>", "deleted_at": "..."}]}
//   Rows not exported yet (oldest change first), after the cursor when one is given. A row's
//   contributor is the 16-character public key; csv_url is a signed download URL (1 h) when
//   the CSV is in the bucket.
//
// {"action": "ack", "rows": [{"id": "...", "updated_at": "...", "csv_archive": "<release>/<asset>"}]}
//   -> {"ok": true, "acked": n}
//   Marks rows exported (only if they didn't change since the pull). With csv_archive, the CSV
//   now lives in a release asset of the dataset, so it's removed from the bucket.

import { createRemoteJWKSet, jwtVerify } from "npm:jose@5";
import { admin, PUBLIC_KEY_LEN, readJson, reply } from "../_shared/common.ts";

const ISSUER = "https://token.actions.githubusercontent.com";
const AUDIENCE = "frametrace-export";
const REPOSITORY = "melle62/frametrace-data";
const JWKS = createRemoteJWKSet(new URL(`${ISSUER}/.well-known/jwks`));

async function authorized(req: Request): Promise<boolean> {
  const token = req.headers.get("x-github-oidc");
  if (!token) return false;
  try {
    const { payload } = await jwtVerify(token, JWKS, { issuer: ISSUER, audience: AUDIENCE });
    return payload.repository === REPOSITORY && payload.ref === "refs/heads/main";
  } catch {
    return false;
  }
}

Deno.serve(async (req) => {
  if (!(await authorized(req))) return reply({ error: "not authorized" }, 401);
  const body = await readJson(req);
  if (body instanceof Response) return body;
  const db = admin();

  if (body.action === "pull") {
    const limit = Math.min(Math.max(Number(body.limit) || 100, 1), 200);
    let query = db
      .from("submissions")
      .select(
        "id, contributor, kind, local_id, schema, app_version, game, exe, store_id, build, gpu, cpu, data, data_sha256, csv_path, csv_sha256, csv_bytes, csv_state, csv_archive, created_at, updated_at",
      )
      .is("exported_at", null);
    if (typeof body.after === "string" && body.after) query = query.gt("updated_at", body.after);
    const { data: rows, error } = await query.order("updated_at", { ascending: true }).limit(limit);
    if (error) return reply({ error: "could not read" }, 500);
    const out = [];
    for (const r of rows ?? []) {
      let csvUrl: string | null = null;
      if (r.csv_path && (r.csv_state === "pending" || r.csv_state === "stored")) {
        const signed = await db.storage.from("csv").createSignedUrl(r.csv_path, 3600);
        if (!signed.error && signed.data?.signedUrl) {
          csvUrl = signed.data.signedUrl;
          if (r.csv_state === "pending") {
            await db.from("submissions").update({ csv_state: "stored" }).eq("id", r.id);
          }
        }
      }
      const { contributor, csv_path: _path, ...rest } = r;
      out.push({ ...rest, contributor: contributor.slice(0, PUBLIC_KEY_LEN), csv_url: csvUrl });
    }
    const { data: deletions } = await db.from("deletions").select("contributor, deleted_at");
    return reply({
      rows: out,
      deletions: (deletions ?? []).map((d) => ({
        contributor: d.contributor.slice(0, PUBLIC_KEY_LEN),
        deleted_at: d.deleted_at,
      })),
    });
  }

  if (body.action === "ack") {
    const items = Array.isArray(body.rows) ? body.rows.slice(0, 500) : [];
    let acked = 0;
    for (const item of items as Array<Record<string, unknown>>) {
      if (typeof item.id !== "string" || typeof item.updated_at !== "string") continue;
      const update: Record<string, unknown> = { exported_at: new Date().toISOString() };
      const archive = typeof item.csv_archive === "string" ? item.csv_archive.slice(0, 200) : null;
      let path: string | null = null;
      if (archive) {
        const { data: row } = await db.from("submissions").select("csv_path").eq("id", item.id)
          .maybeSingle();
        path = row?.csv_path ?? null;
        Object.assign(update, { csv_state: "archived", csv_archive: archive, csv_path: null });
      }
      const { data: done } = await db
        .from("submissions")
        .update(update)
        .eq("id", item.id)
        .eq("updated_at", item.updated_at)
        .select("id");
      if (done?.length) {
        acked += 1;
        if (path) await db.storage.from("csv").remove([path]);
      }
    }
    return reply({ ok: true, acked });
  }

  return reply({ error: "action must be pull or ack" }, 400);
});
