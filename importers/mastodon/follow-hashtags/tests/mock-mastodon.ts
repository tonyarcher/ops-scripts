import { createServer, type IncomingMessage, type Server, type ServerResponse } from "node:http";

export type MockCall = { method: string; url: string; path: string };

export function startMockMastodon(
  handler: (req: IncomingMessage, res: ServerResponse, url: URL) => void,
): Promise<{
  url: string;
  close: () => Promise<void>;
  calls: MockCall[];
}> {
  const calls: MockCall[] = [];
  const server: Server = createServer((req, res) => {
    const url = new URL(req.url ?? "/", "http://127.0.0.1");
    calls.push({ method: req.method ?? "", url: url.href, path: url.pathname });
    handler(req, res, url);
  });

  return new Promise((resolvePromise, reject) => {
    server.once("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      if (address === null || typeof address === "string") {
        reject(new Error("mock server did not bind to a port"));
        return;
      }
      resolvePromise({
        url: `http://127.0.0.1:${address.port}`,
        close: () =>
          new Promise<void>((resolveClose, rejectClose) => {
            server.close((err) => {
              if (err) {
                rejectClose(err);
              } else {
                resolveClose();
              }
            });
          }),
        calls,
      });
    });
  });
}