import { test } from "node:test";
import assert from "node:assert/strict";
import {
  normalizeTag,
  parseTagList,
  mergeTagLists,
  parseNextLink,
  MAX_TAG_LENGTH,
} from "../sources.ts";

test("normalizeTag: strips leading # and lowercases", () => {
  assert.deepEqual(normalizeTag("#Dogs"), { ok: true, name: "dogs" });
});

test("normalizeTag: trims whitespace", () => {
  assert.deepEqual(normalizeTag("  OpenSource  "), { ok: true, name: "opensource" });
});

test("normalizeTag: rejects empty and whitespace-only", () => {
  assert.equal(normalizeTag("").ok, false);
  assert.equal(normalizeTag("   ").ok, false);
  assert.equal(normalizeTag("#").ok, false);
});

test("normalizeTag: rejects too-long tags", () => {
  const long = "a".repeat(MAX_TAG_LENGTH + 1);
  const result = normalizeTag(long);
  assert.equal(result.ok, false);
});

test("normalizeTag: rejects tags with whitespace", () => {
  assert.equal(normalizeTag("two words").ok, false);
  assert.equal(normalizeTag("cats\tdogs").ok, false);
});

test("normalizeTag: accepts unicode letters and underscore", () => {
  assert.deepEqual(normalizeTag("café"), { ok: true, name: "café" });
  assert.deepEqual(normalizeTag("snake_case"), { ok: true, name: "snake_case" });
});

test("parseTagList: skips comments and blank lines, keeps #cats", () => {
  const text = [
    "// x",
    "; y",
    "# note",
    "",
    "  ",
    "#cats",
    "cats",
  ].join("\r\n");
  const result = parseTagList(text);
  assert.deepEqual(result.tags, ["cats"]);
  assert.deepEqual(result.skipped, []);
});

test("parseTagList: dedupes by normalized name keeping first", () => {
  const result = parseTagList("Cats\ncats\n#CATS\nDogs");
  assert.deepEqual(result.tags, ["cats", "dogs"]);
});

test("parseTagList: collects skipped with reasons", () => {
  const result = parseTagList("valid\n\nbad tag\n");
  assert.deepEqual(result.tags, ["valid"]);
  assert.equal(result.skipped.length, 1);
  assert.equal(result.skipped[0].raw, "bad tag");
  assert.ok(result.skipped[0].reason.length > 0);
});

test("mergeTagLists: dedupes keeping first occurrence", () => {
  assert.deepEqual(mergeTagLists(["a", "b"], ["b", "c"], ["a"]), ["a", "b", "c"]);
});

test("parseNextLink: extracts rel=next URL", () => {
  const header =
    '<https://x/api/v1/followed_tags?limit=200&max_id=2>; rel="next", <https://x/api/v1/followed_tags?limit=200&min_id=1>; rel="prev"';
  assert.equal(
    parseNextLink(header),
    "https://x/api/v1/followed_tags?limit=200&max_id=2",
  );
});

test("parseNextLink: returns null when no next", () => {
  assert.equal(parseNextLink('<https://x/page>; rel="prev"'), null);
  assert.equal(parseNextLink(null), null);
  assert.equal(parseNextLink(""), null);
});