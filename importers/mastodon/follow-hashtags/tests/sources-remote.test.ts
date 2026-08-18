import { test } from "node:test";
import assert from "node:assert/strict";
import type { ServerResponse } from "node:http";
import { fetchFollowedTags, fetchTrendingTags } from "../sources.ts";
import { startMockMastodon } from "./mock-mastodon.ts";

function sendJson(
  res: ServerResponse,
  status: number,
  body: unknown,
  headers: Record<string, string> = {},
): void {
  res.writeHead(status, { "Content-Type": "application/json", ...headers });
  res.end(JSON.stringify(body));
}

test("fetchFollowedTags: follows Link rel=next pagination", async () => {
  let serverUrl = "";
  const mock = await startMockMastodon((_req, res, url) => {
    if (url.pathname === "/api/v1/followed_tags") {
      if (url.searchParams.get("max_id") === "2") {
        sendJson(res, 200, [{ name: "bird" }]);
      } else {
        sendJson(res, 200, [{ name: "Cats" }, { name: "dogs" }], {
          Link: `<${serverUrl}/api/v1/followed_tags?limit=200&max_id=2>; rel="next"`,
        });
      }
    } else {
      sendJson(res, 404, { error: "not found" });
    }
  });
  serverUrl = mock.url;
  try {
    const names = await fetchFollowedTags({ instance: mock.url, token: "test-token" });
    assert.deepEqual(names, ["cats", "dogs", "bird"]);
    assert.equal(mock.calls.length, 2);
  } finally {
    await mock.close();
  }
});

test("fetchFollowedTags: strips trailing slash from instance", async () => {
  let serverUrl = "";
  const mock = await startMockMastodon((_req, res, url) => {
    if (url.pathname === "/api/v1/followed_tags") {
      sendJson(res, 200, [{ name: "cats" }]);
    } else {
      sendJson(res, 404, { error: "not found" });
    }
  });
  serverUrl = mock.url;
  try {
    const names = await fetchFollowedTags({
      instance: `${mock.url}/`,
      token: "test-token",
    });
    assert.deepEqual(names, ["cats"]);
  } finally {
    await mock.close();
  }
});

test("fetchFollowedTags: refuses off-origin next links", async () => {
  const mock = await startMockMastodon((_req, res) => {
    sendJson(res, 200, [{ name: "cats" }], {
      Link: `<https://evil.example/collect>; rel="next"`,
    });
  });
  try {
    await assert.rejects(
      fetchFollowedTags({ instance: mock.url, token: "test-token" }),
      /off instance/,
    );
    assert.equal(mock.calls.length, 1);
  } finally {
    await mock.close();
  }
});

test("fetchFollowedTags: throws on non-2xx", async () => {
  const mock = await startMockMastodon((_req, res) => {
    sendJson(res, 500, { error: "boom" });
  });
  try {
    await assert.rejects(
      fetchFollowedTags({ instance: mock.url, token: "test-token" }),
      /500/,
    );
  } finally {
    await mock.close();
  }
});

test("fetchTrendingTags: pages until limit reached", async () => {
  const mock = await startMockMastodon((_req, res, url) => {
    if (url.pathname === "/api/v1/trends/tags") {
      const offset = Number(url.searchParams.get("offset") ?? "0");
      const tags = Array.from({ length: 20 }, (_, i) => ({
        name: `tag${offset + i}`,
      }));
      sendJson(res, 200, tags);
    } else {
      sendJson(res, 404, { error: "not found" });
    }
  });
  try {
    const names = await fetchTrendingTags({ instance: mock.url, limit: 25 });
    assert.equal(names.length, 25);
    assert.equal(names[0], "tag0");
    assert.equal(names[24], "tag24");
    assert.equal(mock.calls.length, 2);
  } finally {
    await mock.close();
  }
});

test("fetchTrendingTags: stops on empty page", async () => {
  const mock = await startMockMastodon((_req, res, url) => {
    if (url.pathname === "/api/v1/trends/tags") {
      const offset = Number(url.searchParams.get("offset") ?? "0");
      if (offset === 0) {
        sendJson(res, 200, [{ name: "only" }]);
      } else {
        sendJson(res, 200, []);
      }
    } else {
      sendJson(res, 404, { error: "not found" });
    }
  });
  try {
    const names = await fetchTrendingTags({ instance: mock.url, limit: 100 });
    assert.deepEqual(names, ["only"]);
  } finally {
    await mock.close();
  }
});