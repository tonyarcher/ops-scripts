import { test } from "node:test";
import assert from "node:assert/strict";
import type { IncomingMessage, ServerResponse } from "node:http";
import { createMastodonClient, FatalApiError, type Clock } from "../mastodon-client.ts";
import { startMockMastodon } from "./mock-mastodon.ts";

function makeFakeClock(start = 0): {
  clock: Clock;
  sleeps: number[];
  advance: (ms: number) => void;
} {
  let current = start;
  const sleeps: number[] = [];
  return {
    clock: {
      now: () => current,
      sleep: async (ms: number) => {
        sleeps.push(ms);
        current += ms;
      },
    },
    sleeps,
    advance: (ms: number) => {
      current += ms;
    },
  };
}

function sendJson(
  res: ServerResponse,
  status: number,
  body: unknown,
  headers: Record<string, string> = {},
): void {
  res.writeHead(status, { "Content-Type": "application/json", ...headers });
  res.end(JSON.stringify(body));
}

test("client: 200 follow returns followed and sends Bearer token", async () => {
  const mock = await startMockMastodon((req, res) => {
    assert.equal(req.headers.authorization, "Bearer test-token");
    sendJson(res, 200, { name: "cats" });
  });
  try {
    const client = createMastodonClient({
      instance: mock.url,
      token: "test-token",
      minDelayMs: 0,
      clock: makeFakeClock().clock,
    });
    const result = await client.followTag("cats");
    assert.equal(result.kind, "followed");
    assert.equal(result.name, "cats");
    assert.equal(mock.calls.length, 1);
    assert.equal(mock.calls[0].path, "/api/v1/tags/cats/follow");
  } finally {
    await mock.close();
  }
});

test("client: 422 Duplicate record returns already", async () => {
  const mock = await startMockMastodon((_req, res) => {
    sendJson(res, 422, { error: "Duplicate record" });
  });
  try {
    const client = createMastodonClient({
      instance: mock.url,
      token: "test-token",
      minDelayMs: 0,
      clock: makeFakeClock().clock,
    });
    const result = await client.followTag("cats");
    assert.equal(result.kind, "already");
    assert.equal(result.status, 422);
  } finally {
    await mock.close();
  }
});

test("client: 422 validation error is not treated as already", async () => {
  const mock = await startMockMastodon((_req, res) => {
    sendJson(res, 422, { error: "Validation failed" });
  });
  try {
    const client = createMastodonClient({
      instance: mock.url,
      token: "test-token",
      minDelayMs: 0,
      clock: makeFakeClock().clock,
    });
    const result = await client.followTag("cats");
    assert.equal(result.kind, "error");
    assert.equal(result.status, 422);
    assert.equal(result.message, "Validation failed");
  } finally {
    await mock.close();
  }
});

test("client: 401 throws FatalApiError", async () => {
  const mock = await startMockMastodon((_req, res) => {
    sendJson(res, 401, { error: "unauthorized" });
  });
  try {
    const client = createMastodonClient({
      instance: mock.url,
      token: "test-token",
      minDelayMs: 0,
      clock: makeFakeClock().clock,
    });
    await assert.rejects(
      client.followTag("cats"),
      (err: unknown) => {
        assert.ok(err instanceof FatalApiError);
        assert.equal(err.fatal, true);
        assert.equal(err.status, 401);
        assert.ok(!err.message.includes("test-token"));
        return true;
      },
    );
  } finally {
    await mock.close();
  }
});

test("client: 403 throws FatalApiError", async () => {
  const mock = await startMockMastodon((_req, res) => {
    sendJson(res, 403, { error: "forbidden" });
  });
  try {
    const client = createMastodonClient({
      instance: mock.url,
      token: "test-token",
      minDelayMs: 0,
      clock: makeFakeClock().clock,
    });
    await assert.rejects(
      client.followTag("cats"),
      (err: unknown) => {
        assert.ok(err instanceof FatalApiError);
        assert.equal(err.status, 403);
        return true;
      },
    );
  } finally {
    await mock.close();
  }
});

test("client: 500 then 200 retries and succeeds", async () => {
  const fake = makeFakeClock();
  let calls = 0;
  const mock = await startMockMastodon((_req, res) => {
    calls++;
    if (calls === 1) {
      sendJson(res, 500, { error: "boom" });
    } else {
      sendJson(res, 200, { name: "cats" });
    }
  });
  try {
    const client = createMastodonClient({
      instance: mock.url,
      token: "test-token",
      minDelayMs: 0,
      clock: fake.clock,
    });
    const result = await client.followTag("cats");
    assert.equal(result.kind, "followed");
    assert.equal(client.requestCount(), 2);
    assert.ok(fake.sleeps.length >= 1);
    assert.ok(fake.sleeps[0] >= 1000);
  } finally {
    await mock.close();
  }
});

test("client: 429 with Retry-After sleeps then succeeds", async () => {
  const fake = makeFakeClock();
  let calls = 0;
  const mock = await startMockMastodon((_req, res) => {
    calls++;
    if (calls === 1) {
      sendJson(res, 429, { error: "rate limited" }, { "Retry-After": "2" });
    } else {
      sendJson(res, 200, { name: "cats" });
    }
  });
  try {
    const client = createMastodonClient({
      instance: mock.url,
      token: "test-token",
      minDelayMs: 0,
      clock: fake.clock,
    });
    const result = await client.followTag("cats");
    assert.equal(result.kind, "followed");
    assert.ok(fake.sleeps.some((ms) => ms >= 2000));
  } finally {
    await mock.close();
  }
});

test("client: rate-limit remaining 0 with future reset sleeps before next request", async () => {
  const fake = makeFakeClock();
  const futureResetMs = 10_000;
  let calls = 0;
  const mock = await startMockMastodon((_req, res) => {
    calls++;
    if (calls === 1) {
      sendJson(
        res,
        200,
        { name: "cats" },
        { "X-RateLimit-Remaining": "0", "X-RateLimit-Reset": new Date(futureResetMs).toISOString() },
      );
    } else {
      sendJson(res, 200, { name: "dogs" });
    }
  });
  try {
    const client = createMastodonClient({
      instance: mock.url,
      token: "test-token",
      minDelayMs: 0,
      clock: fake.clock,
    });
    await client.followTag("cats");
    const sleepsBefore = fake.sleeps.length;
    await client.followTag("dogs");
    assert.ok(fake.sleeps.length > sleepsBefore);
    const sleep = fake.sleeps[fake.sleeps.length - 1];
    assert.equal(sleep, futureResetMs + 250);
  } finally {
    await mock.close();
  }
});

test("client: minDelayMs enforces delay between requests", async () => {
  const fake = makeFakeClock();
  const mock = await startMockMastodon((_req, res) => {
    sendJson(res, 200, { name: "cats" });
  });
  try {
    const client = createMastodonClient({
      instance: mock.url,
      token: "test-token",
      minDelayMs: 1000,
      clock: fake.clock,
    });
    await client.followTag("cats");
    await client.followTag("dogs");
    assert.ok(fake.sleeps.some((ms) => ms >= 1000));
  } finally {
    await mock.close();
  }
});

test("client: 404 returns error kind without throwing", async () => {
  const mock = await startMockMastodon((_req, res) => {
    sendJson(res, 404, { error: "not found" });
  });
  try {
    const client = createMastodonClient({
      instance: mock.url,
      token: "test-token",
      minDelayMs: 0,
      clock: makeFakeClock().clock,
    });
    const result = await client.followTag("cats");
    assert.equal(result.kind, "error");
    assert.equal(result.status, 404);
    assert.equal(result.message, "not found");
  } finally {
    await mock.close();
  }
});

test("client: requestCount counts retries", async () => {
  const fake = makeFakeClock();
  let calls = 0;
  const mock = await startMockMastodon((_req, res) => {
    calls++;
    if (calls <= 2) {
      sendJson(res, 500, { error: "boom" });
    } else {
      sendJson(res, 200, { name: "cats" });
    }
  });
  try {
    const client = createMastodonClient({
      instance: mock.url,
      token: "test-token",
      minDelayMs: 0,
      clock: fake.clock,
    });
    const result = await client.followTag("cats");
    assert.equal(result.kind, "followed");
    assert.equal(client.requestCount(), 3);
  } finally {
    await mock.close();
  }
});