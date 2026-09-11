import assert from "node:assert/strict";
import { test } from "node:test";
import { decodeBase32, totpAt, totpOk } from "./totp.ts";

test("rfc6238-ish known secret", () => {
  const secret = decodeBase32("JBSWY3DPEHPK3PXP");
  const code = totpAt(secret, 0);
  assert.equal(code.length, 6);
  assert.equal(totpOk("JBSWY3DPEHPK3PXP", code, 0), true);
  assert.equal(totpOk("JBSWY3DPEHPK3PXP", "000000", 0), false);
});
