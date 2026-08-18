// Bulk-follow Mastodon hashtags from a file, another account's followed_tags,
// and/or trending tags.
//
// Default dry-run. Pass --apply to POST.
//
// Run:
//   node follow-hashtags.ts --instance URL --file tags.txt
//   bun run follow-hashtags.ts ...
//
// Env: MASTODON_INSTANCE, MASTODON_ACCESS_TOKEN,
//      MASTODON_SOURCE_INSTANCE, MASTODON_SOURCE_TOKEN
//
// Token needs write:follows (and read:follows to copy source follows).
// Never commit tokens. State in tmp/follow-hashtags.db.

import { parseArgs } from "node:util";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { readTagsFromFile, fetchFollowedTags, fetchTrendingTags, mergeTagLists } from "./sources.ts";
import { createMastodonClient, type MastodonClient } from "./mastodon-client.ts";
import { openProgressStore } from "./state.ts";
import { runImporter, type ImportSummary } from "./importer.ts";

export type CliOptions = {
  help: boolean;
  instance: string | undefined;
  token: string | undefined;
  file: string | undefined;
  sourceInstance: string | undefined;
  sourceToken: string | undefined;
  trends: number | undefined;
  delayMs: number;
  max: number | undefined;
  apply: boolean;
  state: string;
  retryFailed: boolean;
  batchSize: number;
};

const USAGE = `Usage: node follow-hashtags.ts [options]

Bulk-follow Mastodon hashtags from a file, another account's followed_tags,
and/or trending tags. Default is dry-run; pass --apply to actually POST.

Options:
  --instance <url>        Mastodon instance (env MASTODON_INSTANCE)
  --token <token>         Access token (env MASTODON_ACCESS_TOKEN)
  --file <path>           Text file with one hashtag per line
  --source-instance <url> Copy followed_tags from this instance (env MASTODON_SOURCE_INSTANCE)
  --source-token <token>  Token for the source instance (env MASTODON_SOURCE_TOKEN)
  --trends <n>            Follow the top n trending tags on --instance
  --delay-ms <ms>         Min delay between requests (default 1500)
  --max <n>               Only follow the first n new tags
  --apply                 Actually POST follows (default is dry-run)
  --state <path>          SQLite state file (default tmp/follow-hashtags.db)
  --retry-failed          Retry tags previously marked error
  --batch-size <n>        Log a batch line every n tags (default 25)
  --help                  Show this help

Examples:
  node follow-hashtags.ts --file sample-tags.txt
  node follow-hashtags.ts --instance https://example.social --file sample-tags.txt --apply
  node follow-hashtags.ts --instance https://new.social --source-instance https://old.social --apply
  node follow-hashtags.ts --instance https://example.social --trends 20
`;

export function parseCli(argv: string[]): CliOptions {
  const { values } = parseArgs({
    args: argv,
    options: {
      instance: { type: "string" },
      token: { type: "string" },
      file: { type: "string" },
      "source-instance": { type: "string" },
      "source-token": { type: "string" },
      trends: { type: "string" },
      "delay-ms": { type: "string", default: "1500" },
      max: { type: "string" },
      apply: { type: "boolean", default: false },
      state: { type: "string", default: "tmp/follow-hashtags.db" },
      "retry-failed": { type: "boolean", default: false },
      "batch-size": { type: "string", default: "25" },
      help: { type: "boolean", default: false },
    },
  });

  return {
    help: values.help ?? false,
    instance: values.instance ?? process.env.MASTODON_INSTANCE,
    token: values.token ?? process.env.MASTODON_ACCESS_TOKEN,
    file: values.file,
    sourceInstance: values["source-instance"] ?? process.env.MASTODON_SOURCE_INSTANCE,
    sourceToken: values["source-token"] ?? process.env.MASTODON_SOURCE_TOKEN,
    trends: parseOptionalInt(values.trends),
    delayMs: parseRequiredInt(values["delay-ms"], 1500),
    max: parseOptionalInt(values.max),
    apply: values.apply ?? false,
    state: values.state ?? "tmp/follow-hashtags.db",
    retryFailed: values["retry-failed"] ?? false,
    batchSize: parseRequiredInt(values["batch-size"], 25),
  };
}

function parseOptionalInt(raw: string | undefined): number | undefined {
  if (raw === undefined) {
    return undefined;
  }
  if (!/^\d+$/.test(raw)) {
    return Number.NaN;
  }
  return Number(raw);
}

function parseRequiredInt(raw: string | undefined, fallback: number): number {
  if (raw === undefined) {
    return fallback;
  }
  if (!/^\d+$/.test(raw)) {
    return Number.NaN;
  }
  return Number(raw);
}

export function validateCli(opts: CliOptions): string | null {
  if (opts.help) {
    return null;
  }
  if (!opts.file && !opts.sourceInstance && opts.trends === undefined) {
    return "need at least one of --file, --source-instance, --trends";
  }
  if (opts.apply && (!opts.instance || !opts.token)) {
    return "--apply requires --instance and --token";
  }
  if (opts.sourceInstance && !opts.sourceToken) {
    return "--source-instance requires --source-token";
  }
  if (opts.trends !== undefined && !opts.instance) {
    return "--trends requires --instance";
  }
  if (opts.trends !== undefined && (!Number.isInteger(opts.trends) || opts.trends < 1)) {
    return "--trends must be a positive integer";
  }
  if (!Number.isInteger(opts.delayMs) || opts.delayMs < 0) {
    return "--delay-ms must be an integer >= 0";
  }
  if (!Number.isInteger(opts.batchSize) || opts.batchSize < 1) {
    return "--batch-size must be an integer >= 1";
  }
  if (opts.max !== undefined && (!Number.isInteger(opts.max) || opts.max < 0)) {
    return "--max must be an integer >= 0";
  }
  return null;
}

function printSummary(summary: ImportSummary): void {
  console.log("summary:");
  console.log(`  followed:   ${summary.followed}`);
  console.log(`  already:    ${summary.already}`);
  console.log(`  skipped:    ${summary.skipped}`);
  console.log(`  failed:     ${summary.failed}`);
  console.log(`  dryRun:     ${summary.dryRun}`);
  console.log(`  invalid:    ${summary.invalid}`);
  console.log(`  durationMs: ${summary.durationMs}`);
}

export async function main(argv: string[]): Promise<number> {
  const opts = parseCli(argv);
  if (opts.help) {
    console.log(USAGE);
    return 0;
  }
  const validationError = validateCli(opts);
  if (validationError) {
    console.error(`error: ${validationError}`);
    console.error(USAGE);
    return 1;
  }

  const tagLists: string[][] = [];
  const invalid: { raw: string; reason: string }[] = [];

  if (opts.file) {
    const result = readTagsFromFile(opts.file);
    tagLists.push(result.tags);
    invalid.push(...result.skipped);
  }
  if (opts.sourceInstance) {
    const followed = await fetchFollowedTags({
      instance: opts.sourceInstance,
      token: opts.sourceToken ?? "",
    });
    tagLists.push(followed);
  }
  if (opts.trends !== undefined) {
    const trending = await fetchTrendingTags({
      instance: opts.instance ?? "",
      limit: opts.trends,
      token: opts.token,
    });
    tagLists.push(trending);
  }

  const tags = mergeTagLists(...tagLists);
  console.log(`loaded ${tags.length} tags, skipped ${invalid.length} invalid`);

  const store = openProgressStore(opts.state);

  let stopped = false;
  const onSigint = (): void => {
    stopped = true;
  };
  process.on("SIGINT", onSigint);

  let client: MastodonClient;
  if (opts.apply) {
    client = createMastodonClient({
      instance: opts.instance ?? "",
      token: opts.token ?? "",
      minDelayMs: opts.delayMs,
    });
  } else {
    client = {
      followTag: async () => {
        throw new Error("followTag called in dry-run mode");
      },
      requestCount: () => 0,
    };
  }

  try {
    const summary = await runImporter({
      config: {
        apply: opts.apply,
        max: opts.max,
        retryFailed: opts.retryFailed,
        batchSize: opts.batchSize,
      },
      tags,
      invalid,
      client,
      store,
      log: (msg) => console.log(msg),
      shouldStop: () => stopped,
    });
    printSummary(summary);
    if (stopped) {
      return 130;
    }
    if (summary.failed > 0) {
      return 1;
    }
    return 0;
  } catch (err) {
    if (stopped) {
      return 130;
    }
    console.error(`fatal: ${err instanceof Error ? err.message : String(err)}`);
    return 1;
  } finally {
    process.removeListener("SIGINT", onSigint);
    store.close();
  }
}

function isMainModule(): boolean {
  const entry = process.argv[1];
  if (!entry) {
    return false;
  }
  try {
    const self = fileURLToPath(import.meta.url);
    const resolved = resolve(entry);
    if (process.platform === "win32") {
      return self.toLowerCase() === resolved.toLowerCase();
    }
    return self === resolved;
  } catch {
    return false;
  }
}

if (isMainModule()) {
  const code = await main(process.argv.slice(2));
  process.exitCode = code;
}