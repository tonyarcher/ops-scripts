import { readFileSync } from "node:fs";

export const MAX_TAG_LENGTH = 30;

export type SkippedTag = { raw: string; reason: string };
export type SourceResult = { tags: string[]; skipped: SkippedTag[] };

const whitespace = /\s/;

export function normalizeTag(
  raw: string,
): { ok: true; name: string } | { ok: false; reason: string } {
  let name = raw.trim();
  while (name.startsWith("#")) {
    name = name.slice(1);
  }
  name = name.toLowerCase();
  if (name.length === 0) {
    return { ok: false, reason: "empty after normalization" };
  }
  if (whitespace.test(name)) {
    return { ok: false, reason: "contains whitespace" };
  }
  if (name.length > MAX_TAG_LENGTH) {
    return { ok: false, reason: `longer than ${MAX_TAG_LENGTH} chars` };
  }
  return { ok: true, name };
}

export function parseTagList(text: string): SourceResult {
  const tags: string[] = [];
  const skipped: SkippedTag[] = [];
  const seen = new Set<string>();
  const lines = text.split(/\r?\n/);
  for (const line of lines) {
    const trimmed = line.trim();
    if (trimmed.length === 0) {
      continue;
    }
    if (trimmed.startsWith("//") || trimmed.startsWith(";")) {
      continue;
    }
    if (trimmed.length > 1 && trimmed.startsWith("#") && (trimmed[1] === " " || trimmed[1] === "\t")) {
      continue;
    }
    const normalized = normalizeTag(trimmed);
    if (!normalized.ok) {
      skipped.push({ raw: line, reason: normalized.reason });
      continue;
    }
    if (!seen.has(normalized.name)) {
      seen.add(normalized.name);
      tags.push(normalized.name);
    }
  }
  return { tags, skipped };
}

export function readTagsFromFile(filePath: string): SourceResult {
  const text = readFileSync(filePath, "utf8");
  return parseTagList(text);
}

export function parseNextLink(linkHeader: string | null): string | null {
  if (!linkHeader) {
    return null;
  }
  const parts = linkHeader.split(",");
  for (const part of parts) {
    const section = part.split(";");
    const urlMatch = section[0].trim().match(/^<([^>]+)>$/);
    if (!urlMatch) {
      continue;
    }
    const rels = section.slice(1).map((s) => s.trim());
    if (rels.some((r) => /^rel\s*=\s*"?next"?$/i.test(r))) {
      return urlMatch[1];
    }
  }
  return null;
}

function collectNames(tags: unknown): string[] {
  if (!Array.isArray(tags)) {
    return [];
  }
  const names: string[] = [];
  for (const tag of tags) {
    if (tag && typeof tag === "object" && "name" in tag && typeof tag.name === "string") {
      const normalized = normalizeTag(tag.name);
      if (normalized.ok) {
        names.push(normalized.name);
      }
    }
  }
  return names;
}

async function fetchJson(url: string, token: string | undefined, fetchImpl: typeof fetch): Promise<Response> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }
  return fetchImpl(url, { headers, signal: AbortSignal.timeout(30000) });
}

const MAX_FOLLOWED_PAGES = 100;

function assertSameOrigin(nextUrl: string, base: string): string {
  const resolved = new URL(nextUrl, base);
  const origin = new URL(base).origin;
  if (resolved.origin !== origin) {
    throw new Error(`refusing to follow pagination link off instance (${resolved.origin})`);
  }
  return resolved.toString();
}

export async function fetchFollowedTags(opts: {
  instance: string;
  token: string;
  fetchImpl?: typeof fetch;
}): Promise<string[]> {
  const base = opts.instance.replace(/\/+$/, "");
  const fetchImpl = opts.fetchImpl ?? fetch;
  const names: string[] = [];
  let next: string | null = `${base}/api/v1/followed_tags?limit=200`;
  let pages = 0;

  while (next) {
    pages++;
    if (pages > MAX_FOLLOWED_PAGES) {
      throw new Error(`fetchFollowedTags exceeded ${MAX_FOLLOWED_PAGES} pages`);
    }
    const response = await fetchJson(next, opts.token, fetchImpl);
    if (!response.ok) {
      throw new Error(`fetchFollowedTags failed with status ${response.status}`);
    }
    const page = collectNames(await response.json());
    names.push(...page);
    const link = parseNextLink(response.headers.get("link"));
    next = link ? assertSameOrigin(link, base) : null;
  }
  return names;
}

export async function fetchTrendingTags(opts: {
  instance: string;
  limit: number;
  token?: string;
  fetchImpl?: typeof fetch;
}): Promise<string[]> {
  const base = opts.instance.replace(/\/+$/, "");
  const fetchImpl = opts.fetchImpl ?? fetch;
  const names: string[] = [];
  let offset = 0;

  while (names.length < opts.limit) {
    const url = `${base}/api/v1/trends/tags?limit=20&offset=${offset}`;
    const response = await fetchJson(url, opts.token, fetchImpl);
    if (!response.ok) {
      throw new Error(`fetchTrendingTags failed with status ${response.status}`);
    }
    const page = collectNames(await response.json());
    names.push(...page);
    if (page.length === 0) {
      break;
    }
    offset += page.length;
  }
  return names.slice(0, opts.limit);
}

export function mergeTagLists(...lists: string[][]): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const list of lists) {
    for (const name of list) {
      if (!seen.has(name)) {
        seen.add(name);
        out.push(name);
      }
    }
  }
  return out;
}
