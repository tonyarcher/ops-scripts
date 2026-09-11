/**
 * RFC 6238 TOTP (SHA-1, 6 digits, 30s). Any local authenticator app.
 * No Google account.
 */
import { createHmac, timingSafeEqual } from "node:crypto";

const ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";

export function decodeBase32(secret: string): Buffer {
  const clean = secret.toUpperCase().replace(/=+$/g, "").replace(/\s+/g, "");
  let bits = "";
  for (const ch of clean) {
    const idx = ALPHABET.indexOf(ch);
    if (idx < 0) {
      throw new Error("invalid base32");
    }
    bits += idx.toString(2).padStart(5, "0");
  }
  const bytes: number[] = [];
  for (let i = 0; i + 8 <= bits.length; i += 8) {
    bytes.push(Number.parseInt(bits.slice(i, i + 8), 2));
  }
  return Buffer.from(bytes);
}

export function totpAt(secret: Buffer, atMs: number, periodSec = 30): string {
  const counter = Math.floor(atMs / 1000 / periodSec);
  const buf = Buffer.alloc(8);
  buf.writeUInt32BE(Math.floor(counter / 0x100000000), 0);
  buf.writeUInt32BE(counter >>> 0, 4);
  const hmac = createHmac("sha1", secret).update(buf).digest();
  const offset = hmac[hmac.length - 1]! & 0xf;
  const bin =
    ((hmac[offset]! & 0x7f) << 24) |
    (hmac[offset + 1]! << 16) |
    (hmac[offset + 2]! << 8) |
    hmac[offset + 3]!;
  return String(bin % 1_000_000).padStart(6, "0");
}

export function totpOk(secretB32: string, code: string, atMs = Date.now()): boolean {
  const secret = decodeBase32(secretB32);
  const guess = code.replace(/\s+/g, "");
  if (!/^\d{6}$/.test(guess)) {
    return false;
  }
  const window = [0, -1, 1];
  const want = Buffer.from(guess);
  for (const w of window) {
    const ts = atMs + w * 30_000;
    if (ts < 0) {
      continue;
    }
    const have = Buffer.from(totpAt(secret, ts));
    if (have.length === want.length && timingSafeEqual(have, want)) {
      return true;
    }
  }
  return false;
}
