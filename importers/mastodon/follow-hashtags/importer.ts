import type { FatalApiError, MastodonClient } from "./mastodon-client.ts";
import type { ProgressStore } from "./state.ts";

export type ImportConfig = {
  apply: boolean;
  max?: number;
  retryFailed: boolean;
  batchSize: number;
};
export type ImportSummary = {
  followed: number;
  already: number;
  skipped: number;
  failed: number;
  dryRun: number;
  invalid: number;
  durationMs: number;
};

export async function runImporter(opts: {
  config: ImportConfig;
  tags: string[];
  invalid: { raw: string; reason: string }[];
  client: MastodonClient;
  store: ProgressStore;
  log?: (msg: string) => void;
  now?: () => number;
  shouldStop?: () => boolean;
}): Promise<ImportSummary> {
  const log = opts.log ?? (() => {});
  const now = opts.now ?? Date.now;
  const shouldStop = opts.shouldStop ?? (() => false);
  const config = opts.config;

  const start = now();
  const summary: ImportSummary = {
    followed: 0,
    already: 0,
    skipped: 0,
    failed: 0,
    dryRun: 0,
    invalid: opts.invalid.length,
    durationMs: 0,
  };

  if (config.apply) {
    for (const item of opts.invalid) {
      opts.store.upsert(item.raw, "invalid", item.reason);
    }
  }

  const work: string[] = [];
  for (const name of opts.tags) {
    const row = opts.store.get(name);
    if (row) {
      if (row.status === "done" || row.status === "already" || row.status === "invalid") {
        summary.skipped++;
        continue;
      }
      if (row.status === "error" && !config.retryFailed) {
        summary.skipped++;
        continue;
      }
    }
    work.push(name);
  }

  const total = work.length;
  let limited = work;
  if (config.max !== undefined && config.max >= 0 && work.length > config.max) {
    limited = work.slice(0, config.max);
    summary.skipped += work.length - config.max;
  }

  let processed = 0;
  for (const name of limited) {
    if (shouldStop()) {
      break;
    }
    processed++;

    if (!config.apply) {
      log(`dry-run would follow #${name}`);
      summary.dryRun++;
    } else {
      try {
        const result = await opts.client.followTag(name);
        if (result.kind === "followed") {
          opts.store.upsert(name, "done");
          summary.followed++;
        } else if (result.kind === "already") {
          opts.store.upsert(name, "already");
          summary.already++;
        } else {
          opts.store.upsert(name, "error", result.message ?? null);
          summary.failed++;
        }
      } catch (err) {
        if ((err as FatalApiError).fatal === true) {
          throw err;
        }
        opts.store.upsert(name, "error", err instanceof Error ? err.message : String(err));
        summary.failed++;
      }
    }

    if (processed % config.batchSize === 0) {
      log(
        `batch ${processed}/${total} followed=${summary.followed} already=${summary.already} failed=${summary.failed} dryRun=${summary.dryRun}`,
      );
    }
  }

  summary.durationMs = now() - start;
  return summary;
}