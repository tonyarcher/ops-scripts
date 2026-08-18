import { test } from "node:test";
import assert from "node:assert/strict";
import { runImporter, type ImportConfig } from "../importer.ts";
import { openProgressStore } from "../state.ts";
import { FatalApiError, type FollowResult, type MastodonClient } from "../mastodon-client.ts";

function makeClient(
  handler: (name: string) => Promise<FollowResult>,
): { client: MastodonClient; calls: string[] } {
  const calls: string[] = [];
  return {
    client: {
      followTag: async (name: string) => {
        calls.push(name);
        return handler(name);
      },
      requestCount: () => calls.length,
    },
    calls,
  };
}

const baseConfig: ImportConfig = {
  apply: true,
  retryFailed: false,
  batchSize: 25,
};

test("importer: dry-run never calls followTag and writes nothing", async () => {
  const store = openProgressStore(":memory:");
  const { client, calls } = makeClient(async () => {
    throw new Error("followTag should not be called in dry-run");
  });
  const summary = await runImporter({
    config: { ...baseConfig, apply: false },
    tags: ["cats", "dogs"],
    invalid: [{ raw: "bad tag", reason: "contains whitespace" }],
    client,
    store,
  });
  assert.equal(calls.length, 0);
  assert.equal(summary.dryRun, 2);
  assert.equal(summary.followed, 0);
  assert.equal(store.summary().done, 0);
  assert.equal(store.summary().invalid, 0);
  store.close();
});

test("importer: apply follows and records done", async () => {
  const store = openProgressStore(":memory:");
  const { client, calls } = makeClient(async (name) => ({ kind: "followed", name }));
  const summary = await runImporter({
    config: baseConfig,
    tags: ["cats", "dogs"],
    invalid: [],
    client,
    store,
  });
  assert.deepEqual(calls, ["cats", "dogs"]);
  assert.equal(summary.followed, 2);
  assert.equal(store.summary().done, 2);
  store.close();
});

test("importer: resume skips already-done tags", async () => {
  const store = openProgressStore(":memory:");
  store.upsert("cats", "done");
  store.upsert("dogs", "already");
  const { client, calls } = makeClient(async (name) => ({ kind: "followed", name }));
  const summary = await runImporter({
    config: baseConfig,
    tags: ["cats", "dogs", "birds"],
    invalid: [],
    client,
    store,
  });
  assert.deepEqual(calls, ["birds"]);
  assert.equal(summary.followed, 1);
  assert.ok(summary.skipped >= 2);
  store.close();
});

test("importer: retryFailed controls error retry", async () => {
  const store = openProgressStore(":memory:");
  store.upsert("cats", "error", "previous failure");

  const noRetry = await runImporter({
    config: baseConfig,
    tags: ["cats"],
    invalid: [],
    client: makeClient(async (name) => ({ kind: "followed", name })).client,
    store,
  });
  assert.equal(noRetry.followed, 0);
  assert.equal(noRetry.skipped, 1);

  const retry = await runImporter({
    config: { ...baseConfig, retryFailed: true },
    tags: ["cats"],
    invalid: [],
    client: makeClient(async (name) => ({ kind: "followed", name })).client,
    store,
  });
  assert.equal(retry.followed, 1);
  assert.equal(store.get("cats")?.status, "done");
  store.close();
});

test("importer: max limits processed tags", async () => {
  const store = openProgressStore(":memory:");
  const { client, calls } = makeClient(async (name) => ({ kind: "followed", name }));
  const summary = await runImporter({
    config: { ...baseConfig, max: 2 },
    tags: ["a", "b", "c", "d", "e"],
    invalid: [],
    client,
    store,
  });
  assert.deepEqual(calls, ["a", "b"]);
  assert.equal(summary.followed, 2);
  assert.equal(summary.skipped, 3);
  store.close();
});

test("importer: invalid tags recorded as invalid", async () => {
  const store = openProgressStore(":memory:");
  const { client } = makeClient(async (name) => ({ kind: "followed", name }));
  const summary = await runImporter({
    config: baseConfig,
    tags: ["cats"],
    invalid: [{ raw: "bad tag", reason: "contains whitespace" }],
    client,
    store,
  });
  assert.equal(summary.invalid, 1);
  const row = store.get("bad tag");
  assert.ok(row);
  assert.equal(row.status, "invalid");
  assert.equal(row.lastError, "contains whitespace");
  store.close();
});

test("importer: FatalApiError aborts the run", async () => {
  const store = openProgressStore(":memory:");
  const { client } = makeClient(async () => {
    throw new FatalApiError("unauthorized (401)", 401);
  });
  await assert.rejects(
    runImporter({
      config: baseConfig,
      tags: ["cats"],
      invalid: [],
      client,
      store,
    }),
    (err: unknown) => {
      assert.ok(err instanceof FatalApiError);
      return true;
    },
  );
  store.close();
});

test("importer: shouldStop breaks early", async () => {
  const store = openProgressStore(":memory:");
  const { client, calls } = makeClient(async (name) => ({ kind: "followed", name }));
  let stopAfter = 1;
  const summary = await runImporter({
    config: baseConfig,
    tags: ["a", "b", "c"],
    invalid: [],
    client,
    store,
    shouldStop: () => calls.length >= stopAfter,
  });
  assert.equal(calls.length, 1);
  assert.equal(summary.followed, 1);
  store.close();
});