/**
 * Optional MFA portal for ops-vpn HTTP on the tunnel.
 * TOTP + passkeys (platform or hardware). No IdP.
 *
 * Run: node --experimental-strip-types server.ts
 */
import { createServer, type IncomingMessage, type ServerResponse } from "node:http";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import {
  generateAuthenticationOptions,
  generateRegistrationOptions,
  verifyAuthenticationResponse,
  verifyRegistrationResponse,
} from "@simplewebauthn/server";
import {
  loadPasskeys,
  loadSessions,
  loadTotpSecrets,
  peerForAddress,
  savePasskeys,
  saveSessions,
  type Passkey,
  type Session,
} from "./store.ts";
import { totpOk } from "./totp.ts";

const configDir = process.env.WG_CONFIG_DIR || "/config";
const listenIp = process.env.MFA_BIND || "127.0.0.1";
const listenPort = Number(process.env.MFA_PORT || "9090");
const rpID = process.env.WG_MFA_HOST || "vpn.ops";
const originHttps = `https://${rpID}:8443`;
const ttlMs = Math.max(1, Number(process.env.WG_MFA_TTL_HOURS || "12")) * 3600_000;
const page = readFileSync(join(import.meta.dirname, "page.html"), "utf8");

const totpDir = join(configDir, "mfa", "totp");
const keysDir = join(configDir, "mfa", "webauthn");
const sessionPath = join(configDir, "mfa", "sessions.json");
const peersDir = join(configDir, "peers");
const caPath = join(configDir, "mfa", "tls", "ca.crt");

const challenges = new Map<string, { kind: string; challenge: string; exp: number }>();
const fails = new Map<string, { n: number; reset: number }>();

function clientIp(req: IncomingMessage): string {
  const fwd = req.headers["x-forwarded-for"];
  if (typeof fwd === "string" && fwd.trim()) {
    return fwd.split(",")[0]!.trim();
  }
  return (req.socket.remoteAddress || "").replace("::ffff:", "");
}

function json(res: ServerResponse, status: number, body: unknown): void {
  const data = JSON.stringify(body);
  res.writeHead(status, {
    "content-type": "application/json",
    "content-length": Buffer.byteLength(data),
  });
  res.end(data);
}

function limited(ip: string): boolean {
  const now = Date.now();
  const row = fails.get(ip);
  if (!row || row.reset < now) {
    fails.set(ip, { n: 1, reset: now + 10 * 60_000 });
    return false;
  }
  row.n += 1;
  return row.n > 8;
}

function unlock(ip: string, peer: string): void {
  const rows = loadSessions(sessionPath);
  rows[ip] = { exp: Date.now() + ttlMs, peer };
  saveSessions(sessionPath, rows);
}

function isOpen(ip: string): boolean {
  const row: Session | undefined = loadSessions(sessionPath)[ip];
  return Boolean(row && row.exp > Date.now());
}

function peerOf(ip: string): string | undefined {
  return peerForAddress(peersDir, ip);
}

function readBody(req: IncomingMessage): Promise<string> {
  return new Promise((resolve, reject) => {
    const chunks: Buffer[] = [];
    req.on("data", (c) => chunks.push(c as Buffer));
    req.on("end", () => resolve(Buffer.concat(chunks).toString("utf8")));
    req.on("error", reject);
  });
}

async function handleTotp(req: IncomingMessage, res: ServerResponse, ip: string): Promise<void> {
  if (limited(ip)) {
    json(res, 429, { error: "too many attempts" });
    return;
  }
  const peer = peerOf(ip);
  if (!peer) {
    json(res, 403, { error: "unknown tunnel IP" });
    return;
  }
  const body = JSON.parse(await readBody(req)) as { code?: string };
  const secret = loadTotpSecrets(totpDir)[peer];
  if (!secret || !totpOk(secret, body.code || "")) {
    json(res, 401, { error: "bad code" });
    return;
  }
  unlock(ip, peer);
  json(res, 200, { ok: true });
}

async function handleRegOptions(res: ServerResponse, ip: string): Promise<void> {
  const peer = peerOf(ip);
  if (!peer || !isOpen(ip)) {
    json(res, 401, { error: "unlock with TOTP first" });
    return;
  }
  const existing = loadPasskeys(keysDir, peer);
  const options = await generateRegistrationOptions({
    rpName: "ops-vpn",
    rpID,
    userName: peer,
    userID: new TextEncoder().encode(peer),
    attestationType: "none",
    excludeCredentials: existing.map((k) => ({ id: k.id })),
    authenticatorSelection: {
      residentKey: "preferred",
      userVerification: "preferred",
    },
  });
  challenges.set(ip, { kind: "reg", challenge: options.challenge, exp: Date.now() + 120_000 });
  json(res, 200, options);
}

async function handleRegister(req: IncomingMessage, res: ServerResponse, ip: string): Promise<void> {
  const peer = peerOf(ip);
  const ch = challenges.get(ip);
  if (!peer || !isOpen(ip) || !ch || ch.kind !== "reg" || ch.exp < Date.now()) {
    json(res, 401, { error: "register session expired" });
    return;
  }
  const body = JSON.parse(await readBody(req));
  const verification = await verifyRegistrationResponse({
    response: body,
    expectedChallenge: ch.challenge,
    expectedOrigin: originHttps,
    expectedRPID: rpID,
  });
  if (!verification.verified || !verification.registrationInfo) {
    json(res, 401, { error: "webauthn register failed" });
    return;
  }
  const cred = verification.registrationInfo.credential;
  const keys = loadPasskeys(keysDir, peer);
  const row: Passkey = {
    id: cred.id,
    publicKey: Buffer.from(cred.publicKey).toString("base64"),
    counter: cred.counter,
    transports: cred.transports,
  };
  keys.push(row);
  savePasskeys(keysDir, peer, keys);
  challenges.delete(ip);
  json(res, 200, { ok: true });
}

async function handleLoginOptions(res: ServerResponse, ip: string): Promise<void> {
  const peer = peerOf(ip);
  if (!peer) {
    json(res, 403, { error: "unknown tunnel IP" });
    return;
  }
  const keys = loadPasskeys(keysDir, peer);
  if (keys.length === 0) {
    json(res, 400, { error: "no passkey registered" });
    return;
  }
  const options = await generateAuthenticationOptions({
    rpID,
    allowCredentials: keys.map((k) => ({ id: k.id })),
    userVerification: "preferred",
  });
  challenges.set(ip, { kind: "login", challenge: options.challenge, exp: Date.now() + 120_000 });
  json(res, 200, options);
}

async function handleLogin(req: IncomingMessage, res: ServerResponse, ip: string): Promise<void> {
  if (limited(ip)) {
    json(res, 429, { error: "too many attempts" });
    return;
  }
  const peer = peerOf(ip);
  const ch = challenges.get(ip);
  if (!peer || !ch || ch.kind !== "login" || ch.exp < Date.now()) {
    json(res, 401, { error: "login session expired" });
    return;
  }
  const body = JSON.parse(await readBody(req)) as { id?: string };
  const passkey = loadPasskeys(keysDir, peer).find((k) => k.id === body.id);
  if (!passkey) {
    json(res, 401, { error: "unknown key" });
    return;
  }
  const verification = await verifyAuthenticationResponse({
    response: body,
    expectedChallenge: ch.challenge,
    expectedOrigin: originHttps,
    expectedRPID: rpID,
    credential: {
      id: passkey.id,
      publicKey: new Uint8Array(Buffer.from(passkey.publicKey, "base64")),
      counter: passkey.counter,
      transports: passkey.transports as never,
    },
  });
  if (!verification.verified) {
    json(res, 401, { error: "webauthn failed" });
    return;
  }
  const keys = loadPasskeys(keysDir, peer).map((k) =>
    k.id === passkey.id
      ? { ...k, counter: verification.authenticationInfo.newCounter }
      : k,
  );
  savePasskeys(keysDir, peer, keys);
  challenges.delete(ip);
  unlock(ip, peer);
  json(res, 200, { ok: true });
}

async function route(req: IncomingMessage, res: ServerResponse): Promise<void> {
  const ip = clientIp(req);
  const url = new URL(req.url || "/", "http://mfa.local");
  const path = url.pathname;
  if (req.method === "GET" && (path === "/" || path === "/index.html")) {
    res.writeHead(200, { "content-type": "text/html; charset=utf-8" });
    res.end(page);
    return;
  }
  if (req.method === "GET" && path === "/ca.crt") {
    try {
      const body = readFileSync(caPath);
      res.writeHead(200, { "content-type": "application/x-x509-ca-cert" });
      res.end(body);
    } catch {
      json(res, 404, { error: "no CA yet" });
    }
    return;
  }
  if (req.method === "GET" && path === "/whoami") {
    json(res, 200, { ip, peer: peerOf(ip) || null, open: isOpen(ip) });
    return;
  }
  if (req.method === "GET" && path === "/auth") {
    res.writeHead(isOpen(ip) ? 200 : 401);
    res.end();
    return;
  }
  if (req.method === "POST" && path === "/totp") {
    await handleTotp(req, res, ip);
    return;
  }
  if (req.method === "GET" && path === "/webauthn/register/options") {
    await handleRegOptions(res, ip);
    return;
  }
  if (req.method === "POST" && path === "/webauthn/register") {
    await handleRegister(req, res, ip);
    return;
  }
  if (req.method === "GET" && path === "/webauthn/login/options") {
    await handleLoginOptions(res, ip);
    return;
  }
  if (req.method === "POST" && path === "/webauthn/login") {
    await handleLogin(req, res, ip);
    return;
  }
  json(res, 404, { error: "not found" });
}

const server = createServer((req, res) => {
  void route(req, res).catch((err: unknown) => {
    const msg = err instanceof Error ? err.message : "error";
    if (!res.headersSent) {
      json(res, 500, { error: msg });
    }
  });
});

server.listen(listenPort, listenIp, () => {
  process.stdout.write(`mfa listening ${listenIp}:${listenPort} rp=${rpID}\n`);
});
