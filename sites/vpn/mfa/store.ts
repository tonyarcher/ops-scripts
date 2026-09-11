import { mkdirSync, readFileSync, readdirSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";

export type Session = { exp: number; peer: string };
export type Passkey = {
  id: string;
  publicKey: string;
  counter: number;
  transports?: string[];
};

export function readText(path: string): string | undefined {
  try {
    return readFileSync(path, "utf8").trim();
  } catch {
    return undefined;
  }
}

export function writeJson(path: string, value: unknown): void {
  mkdirSync(dirname(path), { recursive: true, mode: 0o700 });
  writeFileSync(path, JSON.stringify(value), { encoding: "utf8", mode: 0o600 });
}

export function loadSessions(path: string): Record<string, Session> {
  const raw = readText(path);
  if (!raw) {
    return {};
  }
  const parsed = JSON.parse(raw) as Record<string, Session>;
  const now = Date.now();
  const live: Record<string, Session> = {};
  for (const [ip, row] of Object.entries(parsed)) {
    if (row.exp > now) {
      live[ip] = row;
    }
  }
  return live;
}

export function saveSessions(path: string, rows: Record<string, Session>): void {
  writeJson(path, rows);
}

export function loadTotpSecrets(dir: string): Record<string, string> {
  const out: Record<string, string> = {};
  let names: string[] = [];
  try {
    names = readdirSync(dir);
  } catch {
    return out;
  }
  for (const name of names) {
    const secret = readText(join(dir, name));
    if (secret) {
      out[name] = secret;
    }
  }
  return out;
}

export function loadPasskeys(dir: string, peer: string): Passkey[] {
  const raw = readText(join(dir, `${peer}.json`));
  if (!raw) {
    return [];
  }
  return JSON.parse(raw) as Passkey[];
}

export function savePasskeys(dir: string, peer: string, keys: Passkey[]): void {
  writeJson(join(dir, `${peer}.json`), keys);
}

export function peerForAddress(
  peersDir: string,
  ip: string,
): string | undefined {
  let names: string[] = [];
  try {
    names = readdirSync(peersDir);
  } catch {
    return undefined;
  }
  for (const name of names) {
    const conf = readText(join(peersDir, name, "client.conf"));
    if (!conf) {
      continue;
    }
    const match = /^Address = ([0-9.]+)\//m.exec(conf);
    if (match?.[1] === ip) {
      return name;
    }
  }
  return undefined;
}
