import { test } from "node:test";
import assert from "node:assert/strict";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { rmSync } from "node:fs";
import { openProgressStore } from "../state.ts";

test("state: memory store upsert, get, attempts, summary", () => {
  const store = openProgressStore(":memory:");
  assert.equal(store.get("cats"), undefined);

  store.upsert("cats", "pending");
  const row = store.get("cats");
  assert.ok(row);
  assert.equal(row.name, "cats");
  assert.equal(row.status, "pending");
  assert.equal(row.attempts, 1);
  assert.equal(row.lastError, null);

  store.upsert("cats", "done");
  const row2 = store.get("cats");
  assert.ok(row2);
  assert.equal(row2.status, "done");
  assert.equal(row2.attempts, 2);

  store.upsert("dogs", "error", "boom");
  const row3 = store.get("dogs");
  assert.ok(row3);
  assert.equal(row3.status, "error");
  assert.equal(row3.lastError, "boom");

  const summary = store.summary();
  assert.deepEqual(summary, {
    pending: 0,
    done: 1,
    already: 0,
    error: 1,
    invalid: 0,
  });

  store.close();
});

test("state: file-backed store persists", () => {
  const dir = tmpdir();
  const dbPath = join(dir, `follow-hashtags-test-${process.pid}-${Date.now()}.db`);
  try {
    const store = openProgressStore(dbPath);
    store.upsert("cats", "done");
    store.close();

    const reopened = openProgressStore(dbPath);
    const row = reopened.get("cats");
    assert.ok(row);
    assert.equal(row.status, "done");
    assert.equal(reopened.summary().done, 1);
    reopened.close();
  } finally {
    for (const suffix of ["", "-wal", "-shm"]) {
      try {
        rmSync(`${dbPath}${suffix}`, { force: true });
      } catch {
        // Windows can keep a just-closed sqlite file locked briefly.
      }
    }
  }
});