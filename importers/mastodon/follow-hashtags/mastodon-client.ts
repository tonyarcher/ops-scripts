const DEFAULT_RATE_LIMIT_BUFFER = 5;
const DEFAULT_MAX_RETRIES = 3;
const DEFAULT_REQUEST_TIMEOUT_MS = 30000;

export class FatalApiError extends Error {
  readonly fatal: true;
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.fatal = true;
    this.status = status;
  }
}

export type FollowKind = "followed" | "already" | "error";
export type FollowResult = {
  kind: FollowKind;
  name: string;
  status?: number;
  message?: string;
};

export type Clock = {
  now: () => number;
  sleep: (ms: number) => Promise<void>;
};

export type MastodonClient = {
  followTag(name: string): Promise<FollowResult>;
  requestCount: () => number;
};

const defaultClock: Clock = {
  now: () => Date.now(),
  sleep: (ms) => new Promise((resolve) => setTimeout(resolve, ms)),
};

type RateInfo = {
  remaining: number | null;
  resetMs: number | null;
};

function parseReset(header: string | null): number | null {
  if (!header) {
    return null;
  }
  const trimmed = header.trim();
  if (trimmed.length === 0) {
    return null;
  }
  const numeric = Number(trimmed);
  if (Number.isFinite(numeric)) {
    if (numeric > 1e12) {
      return numeric;
    }
    return numeric * 1000;
  }
  const parsed = Date.parse(trimmed);
  return Number.isNaN(parsed) ? null : parsed;
}

export function createMastodonClient(opts: {
  instance: string;
  token: string;
  minDelayMs: number;
  rateLimitBuffer?: number;
  maxRetries?: number;
  requestTimeoutMs?: number;
  fetchImpl?: typeof fetch;
  clock?: Clock;
}): MastodonClient {
  const base = opts.instance.replace(/\/+$/, "");
  const token = opts.token;
  const minDelayMs = opts.minDelayMs;
  const rateLimitBuffer = opts.rateLimitBuffer ?? DEFAULT_RATE_LIMIT_BUFFER;
  const maxRetries = opts.maxRetries ?? DEFAULT_MAX_RETRIES;
  const requestTimeoutMs = opts.requestTimeoutMs ?? DEFAULT_REQUEST_TIMEOUT_MS;
  const fetchImpl = opts.fetchImpl ?? fetch;
  const clock = opts.clock ?? defaultClock;

  const maxSleepMs = 5 * 60 * 1000;
  let requestCount = 0;
  let lastRequestStart: number | null = null;
  let lastRate: RateInfo = { remaining: null, resetMs: null };

  async function boundedSleep(ms: number): Promise<void> {
    if (ms <= 0) {
      return;
    }
    await clock.sleep(Math.min(ms, maxSleepMs));
  }

  async function request(path: string): Promise<Response> {
    if (minDelayMs > 0 && lastRequestStart !== null) {
      const elapsed = clock.now() - lastRequestStart;
      if (elapsed < minDelayMs) {
        await boundedSleep(minDelayMs - elapsed);
      }
    }

    const lastReset = lastRate.resetMs;
    const lastRemaining = lastRate.remaining;
    const nowAfterPace = clock.now();
    if (
      lastRemaining !== null &&
      lastRemaining < rateLimitBuffer &&
      lastReset !== null &&
      lastReset > nowAfterPace
    ) {
      await boundedSleep(lastReset - nowAfterPace + 250);
    }

    const url = `${base}${path}`;
    let lastError: unknown;

    for (let attempt = 0; ; attempt++) {
      lastRequestStart = clock.now();
      requestCount++;

      let response: Response;
      let networkError = false;
      try {
        response = await fetchImpl(url, {
          method: "POST",
          headers: {
            Authorization: `Bearer ${token}`,
            Accept: "application/json",
          },
          signal: AbortSignal.timeout(requestTimeoutMs),
        });
      } catch (err) {
        networkError = true;
        lastError = err;
      }

      if (networkError) {
        if (attempt + 1 >= maxRetries) {
          throw new Error(
            `request to ${path} failed after ${attempt + 1} attempts: ${String(lastError)}`,
          );
        }
        await backoffSleep(attempt, null);
        continue;
      }

      const header = response.headers;
      const remainingHeader = header.get("x-ratelimit-remaining");
      const remaining = remainingHeader === null ? null : Number(remainingHeader);
      const resetMs = parseReset(header.get("x-ratelimit-reset"));
      if (remaining !== null && Number.isFinite(remaining)) {
        lastRate = { remaining, resetMs };
      }

      if (response.status === 401 || response.status === 403) {
        const label = response.status === 401 ? "unauthorized" : "forbidden";
        throw new FatalApiError(`${label} (${response.status})`, response.status);
      }

      if (response.status === 429) {
        if (attempt + 1 >= maxRetries) {
          throw new Error(`request to ${path} rate-limited after ${attempt + 1} attempts`);
        }
        const retryAfter = header.get("retry-after");
        await backoffSleep(attempt, retryAfter, resetMs);
        continue;
      }

      if (response.status >= 500) {
        if (attempt + 1 >= maxRetries) {
          throw new Error(`request to ${path} failed with status ${response.status}`);
        }
        await backoffSleep(attempt, null, resetMs);
        continue;
      }

      return response;
    }
  }

  async function backoffSleep(
    attempt: number,
    retryAfter: string | null,
    resetMs: number | null = null,
  ): Promise<void> {
    if (retryAfter !== null) {
      const seconds = Number(retryAfter);
      if (Number.isFinite(seconds) && seconds > 0) {
        await boundedSleep(seconds * 1000);
        return;
      }
    }
    if (resetMs !== null) {
      const now = clock.now();
      if (resetMs > now) {
        await boundedSleep(resetMs - now);
        return;
      }
    }
    const jitter = Math.random() * 250;
    await boundedSleep(1000 * 2 ** attempt + jitter);
  }

  async function followTag(name: string): Promise<FollowResult> {
    const path = `/api/v1/tags/${encodeURIComponent(name)}/follow`;
    const response = await request(path);
    if (response.status === 200) {
      return { kind: "followed", name };
    }
    let message: string | undefined;
    if (response.status >= 400 && response.status < 500) {
      try {
        const body = (await response.json()) as { error?: unknown };
        if (typeof body.error === "string") {
          message = body.error;
        }
      } catch {
        // ignore body parse failure
      }
    }
    // Pre-4.1 Mastodon returned 422 "Duplicate record" when already following.
    // On 4.1+ follow is idempotent (200); any other 422 is a validation error.
    if (response.status === 422 && message !== undefined && /duplicate record/i.test(message)) {
      return { kind: "already", name, status: 422, message };
    }
    if (response.status >= 400 && response.status < 500) {
      return { kind: "error", name, status: response.status, message };
    }
    return { kind: "error", name, status: response.status };
  }

  return {
    followTag,
    requestCount: () => requestCount,
  };
}
