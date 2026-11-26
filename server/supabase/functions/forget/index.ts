// POST /functions/v1/forget  {"install": "<uuid4>"}
//
// Deletes everything an install shared: its rows and its CSVs. The contributor key goes on
// the deletions list, so the next export also removes it from the public dataset (the data
// branch and the CSV release assets).
//
// -> {"ok": true, "deleted": n}

import { admin, contributor, readJson, reply, validInstall } from "../_shared/common.ts";

Deno.serve(async (req) => {
  const body = await readJson(req);
  if (body instanceof Response) return body;
  if (!validInstall(body.install)) return reply({ error: "install must be a random UUID (v4)" }, 400);

  const db = admin();
  const who = await contributor(db, body.install as string);

  const { data: rows, error } = await db
    .from("submissions")
    .select("id, csv_path")
    .eq("contributor", who);
  if (error) return reply({ error: "could not read" }, 500);

  const paths = (rows ?? []).map((r) => r.csv_path).filter((p): p is string => Boolean(p));
  for (let i = 0; i < paths.length; i += 100) {
    await db.storage.from("csv").remove(paths.slice(i, i + 100));
  }
  const { error: delError } = await db.from("submissions").delete().eq("contributor", who);
  if (delError) return reply({ error: "could not delete" }, 500);
  await db.from("deletions").upsert({
    contributor: who,
    deleted_at: new Date().toISOString(),
    rows_deleted: rows?.length ?? 0,
  });
  return reply({ ok: true, deleted: rows?.length ?? 0 });
});
