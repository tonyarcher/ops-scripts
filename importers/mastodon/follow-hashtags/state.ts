import { createRequire } from "node:module";
import { mkdirSync } from "node:fs";
import { dirname } from "node:path";

type Prepared = {
  get: (...params: unknown[]) => unknown;
  run: (...params: unknown[]) => unknown;
  all: (...params: unknown[]) => unknown[];
};

type RawDb = {
  exec: (sql: string) => void;
  prepare: (sql: string) => Prepared;
  close: () => void;
};

function openRawDb(dbPath: string): RawDb {
  const require = createRequire(import.meta.url);
  try {
    const sqlite = require("node:sqlite") as { DatabaseSync: new (path: string) => RawDb };
    return new sqlite.DatabaseSync(dbPath);
  } catch {
    const sqlite = require("bun:sqlite") as { Database: new (path: string) => RawDb };
    return new sqlite.Database(dbPath);
  }
}

export type TagStatus = "pending" | "done" | "already" | "error" | "invalid";
export type TagRow = {
  name: string;
  status: TagStatus;
  attempts: number;
  lastError: string | null;
  updatedAt: string;
};
export type StatusCounts = {
  pending: number;
  done: number;
  already: number;
  error: number;
  invalid: number;
};
export type ProgressStore = {
  get(name: string): TagRow | undefined;
  upsert(name: string, status: TagStatus, error?: string | null): void;
  summary(): StatusCounts;
  close(): void;
};

const EMPTY_COUNTS: StatusCounts = {
  pending: 0,
  done: 0,
  already: 0,
  error: 0,
  invalid: 0,
};

export function openProgressStore(dbPath: string): ProgressStore {
  if (dbPath !== ":memory:") {
    mkdirSync(dirname(dbPath), { recursive: true });
  }
  const db = openRawDb(dbPath);
  db.exec(`
    CREATE TABLE IF NOT EXISTS tags (
      name TEXT PRIMARY KEY,
      status TEXT NOT NULL,
      attempts INTEGER NOT NULL DEFAULT 0,
      last_error TEXT,
      updated_at TEXT NOT NULL
    );
  `);

  const getStmt = db.prepare("SELECT name, status, attempts, last_error, updated_at FROM tags WHERE name = ?");
  const upsertStmt = db.prepare(`
    INSERT INTO tags (name, status, attempts, last_error, updated_at)
    VALUES (?, ?, 1, ?, ?)
    ON CONFLICT(name) DO UPDATE SET
      status = excluded.status,
      attempts = tags.attempts + 1,
      last_error = excluded.last_error,
      updated_at = excluded.updated_at
  `);
  const summaryStmt = db.prepare("SELECT status, COUNT(*) AS count FROM tags GROUP BY status");

  return {
    get(name: string): TagRow | undefined {
      const row = getStmt.get(name) as
        | { name: string; status: string; attempts: number; last_error: string | null; updated_at: string }
        | undefined;
      if (!row) {
        return undefined;
      }
      return {
        name: row.name,
        status: row.status as TagStatus,
        attempts: row.attempts,
        lastError: row.last_error,
        updatedAt: row.updated_at,
      };
    },
    upsert(name: string, status: TagStatus, error: string | null = null): void {
      upsertStmt.run(name, status, error, new Date().toISOString());
    },
    summary(): StatusCounts {
      const counts: StatusCounts = { ...EMPTY_COUNTS };
      const rows = summaryStmt.all() as { status: string; count: number }[];
      for (const row of rows) {
        const key = row.status as keyof StatusCounts;
        if (key in counts) {
          counts[key] = row.count;
        }
      }
      return counts;
    },
    close(): void {
      db.close();
    },
  };
}