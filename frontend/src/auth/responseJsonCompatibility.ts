/** Neon Auth's session cache requires static Response.json (Safari 17+). */
export function ensureResponseJson(): void {
  if (typeof Response.json === "function") return;

  Object.defineProperty(Response, "json", {
    configurable: true,
    writable: true,
    value(data: unknown, init?: ResponseInit): Response {
      const body = JSON.stringify(data);
      if (body === undefined) {
        throw new TypeError("The supplied value is not JSON serializable.");
      }
      const headers = new Headers(init?.headers);
      if (!headers.has("Content-Type")) {
        headers.set("Content-Type", "application/json");
      }
      return new Response(body, { ...init, headers });
    },
  });
}
