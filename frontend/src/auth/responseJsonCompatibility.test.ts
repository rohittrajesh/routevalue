import { afterEach, describe, expect, it } from "vitest";
import { ensureResponseJson } from "./responseJsonCompatibility";

const originalDescriptor = Object.getOwnPropertyDescriptor(Response, "json")!;

afterEach(() => {
  Object.defineProperty(Response, "json", originalDescriptor);
});

function emulateOlderBrowser(): void {
  Object.defineProperty(Response, "json", {
    configurable: true,
    value: undefined,
  });
  ensureResponseJson();
}

describe("static Response.json compatibility", () => {
  it("preserves the native implementation", () => {
    const native = Response.json;
    ensureResponseJson();
    expect(Response.json).toBe(native);
  });

  it("returns JSON with the supplied response options without mutating headers", async () => {
    emulateOlderBrowser();
    const headers = new Headers({ "X-Fixture": "yes" });
    const response = Response.json(
      { value: "fixture" },
      { status: 201, statusText: "Created", headers },
    );
    expect(response.status).toBe(201);
    expect(response.statusText).toBe("Created");
    expect(response.headers.get("Content-Type")).toBe("application/json");
    expect(response.headers.get("X-Fixture")).toBe("yes");
    expect(headers.has("Content-Type")).toBe(false);
    await expect(response.json()).resolves.toEqual({ value: "fixture" });
  });

  it("preserves an explicit content type and is idempotent", () => {
    emulateOlderBrowser();
    const implementation = Response.json;
    ensureResponseJson();
    expect(Response.json).toBe(implementation);
    expect(
      Response.json(null, {
        headers: { "Content-Type": "application/problem+json" },
      }).headers.get("Content-Type"),
    ).toBe("application/problem+json");
  });

  it("rejects non-JSON values and invalid response options", () => {
    emulateOlderBrowser();
    const circular: { self?: unknown } = {};
    circular.self = circular;
    expect(() => Response.json(undefined)).toThrow(TypeError);
    expect(() => Response.json(circular)).toThrow(TypeError);
    expect(() => Response.json(1n)).toThrow(TypeError);
    expect(() => Response.json({}, { status: 204 })).toThrow(TypeError);
  });
});
