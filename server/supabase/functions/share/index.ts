// POST /functions/v1/share
//
// {"install": "<uuid4>", "kind": "capture" | "comparison", "id": "<local id>", "schema": 1,
//  "app": "<frametrace version>", "data": {...}, "csv": {"bytes": n, "sha256": "<hex>"}}
//
// Upserts one submission by (contributor, kind, id). A changed bundle replaces the stored one
// and is exported again. For a capture whose CSV the server doesn't have yet, the reply carries
// a signed upload URL (valid 2 h): PUT the gzipped CSV there.
//
// -> {"ok": true, "changed": bool, "csv_upload": "<url>" | null, "csv_deferred": bool}
//    csv_deferred: too many CSVs are waiting for the export; send this one again later.

import {
  admin,
  captureColumns,
  contributor,
  CSV_WAITING_PER_CONTRIBUTOR,
  CSV_WAITING_TOTAL,
  DAILY_LIMIT,
  MAX_CSV_BYTES,
  readJson,
  reply,
  SCHEMA,
  sha256,
  validInstall,
  validLocalId,
  validSha,
} from "../_shared/common.ts";

Deno.serve(async (req) => {
  const body = await readJson(req);
  if (body instanceof Response) return body;
  const { install, kind, id, schema, app, data, csv } = body as Record<string, any>;
  if (!validInstall(install)) return reply({ error: "install must be a random UUID (v4)" }, 400);
  if (kind !== "capture" && kind !== "comparison") return reply({ error: "unknown kind" }, 400);
  if (!validLocalId(id)) return reply({ error: "bad id" }, 400);
  if (schema !== SCHEMA) return reply({ error: `schema ${SCHEMA} expected` }, 400);
  if (!data || typeof data !== "object" || Array.isArray(data)) {
    return reply({ error: "data must be an object" }, 400);
  }
  const wantCsv = kind === "capture" && csv && validSha(csv.sha256) &&
    Number.isInteger(csv.bytes) && csv.bytes > 0 && csv.bytes <= MAX_CSV_BYTES;
  if (csv && !wantCsv) return reply({ error: "bad csv description (max 50 MB)" }, 400);

  const db = admin();
  const who = await contributor(db, install);

  // An install whose data was deleted starts over with a new ID (the app does that itself).
  const { data: gone } = await db.from("deletions").select("contributor").eq("contributor", who)
    .maybeSingle();
  if (gone) return reply({ error: "this install's data was deleted: use a new install ID" }, 410);

  const since = new Date(Date.now() - 86_400_000).toISOString();
  const { count } = await db
    .from("submissions")
    .select("id", { count: "exact", head: true })
    .eq("contributor", who)
    .gte("updated_at", since);
  if ((count ?? 0) >= DAILY_LIMIT) return reply({ error: "daily limit reached, try tomorrow" }, 429);

  const { data: row } = await db
    .from("submissions")
    .select("id, data_sha256, csv_sha256, csv_state")
    .eq("contributor", who)
    .eq("kind", kind)
    .eq("local_id", id)
    .maybeSingle();

  const dataSha = await sha256(JSON.stringify(data));
  const haveCsv = row && row.csv_sha256 === csv?.sha256 &&
    (row.csv_state === "stored" || row.csv_state === "archived");
  let needCsv = Boolean(wantCsv && !haveCsv);
  let deferred = false;
  if (needCsv) {
    // CSVs signed in the last day and not archived yet (an upload that never finished stops
    // counting after a day).
    const waiting = ["pending", "stored"];
    const { count: mine } = await db.from("submissions")
      .select("id", { count: "exact", head: true })
      .eq("contributor", who).in("csv_state", waiting).gte("updated_at", since);
    const { count: all } = await db.from("submissions")
      .select("id", { count: "exact", head: true })
      .in("csv_state", waiting).gte("updated_at", since);
    if ((mine ?? 0) >= CSV_WAITING_PER_CONTRIBUTOR || (all ?? 0) >= CSV_WAITING_TOTAL) {
      needCsv = false;
      deferred = true;
    }
  }
  if (row && row.data_sha256 === dataSha && !needCsv) {
    return reply({ ok: true, changed: false, csv_upload: null, csv_deferred: deferred });
  }

  const record: Record<string, unknown> = {
    contributor: who,
    kind,
    local_id: id,
    schema,
    app_version: typeof app === "string" ? app.slice(0, 40) : null,
    ...captureColumns(data), // a comparison carries its game too (no system: gpu, cpu stay null)
    data,
    data_sha256: dataSha,
    updated_at: new Date().toISOString(),
    exported_at: null,
  };
  const path = `${who}/${id}.csv.gz`;
  if (needCsv) {
    Object.assign(record, {
      csv_path: path,
      csv_sha256: csv.sha256,
      csv_bytes: csv.bytes,
      csv_state: "pending",
    });
  }
  const { error } = await db
    .from("submissions")
    .upsert(record, { onConflict: "contributor,kind,local_id" });
  if (error) return reply({ error: "could not save", detail: error.message }, 500);

  let upload: string | null = null;
  if (needCsv) {
    const signed = await db.storage.from("csv").createSignedUploadUrl(path, { upsert: true });
    if (signed.error) return reply({ error: "could not sign the upload" }, 500);
    upload = signed.data.signedUrl;
  }
  return reply({ ok: true, changed: true, csv_upload: upload, csv_deferred: deferred });
});
