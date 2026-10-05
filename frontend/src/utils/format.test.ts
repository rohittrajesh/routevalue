import { describe, expect, it } from "vitest";

import {
  formatDecisionReason,
  formatDistance,
  formatDuration,
  formatMoney,
  formatEligibilityReason,
} from "./format";

describe("formatDistance", () => {
  it("converts meters to miles", () => {
    expect(formatDistance(1609.344)).toBe("1.0 mi");
  });
});

describe("formatDuration", () => {
  it("formats minutes", () => {
    expect(formatDuration(1500)).toBe("25 min");
  });

  it("formats hours and minutes", () => {
    expect(formatDuration(4500)).toBe("1 hr 15 min");
  });
});

describe("formatMoney", () => {
  it("formats money values", () => {
    expect(formatMoney("4.5")).toBe("$4.50");
  });

  it("handles unavailable values", () => {
    expect(formatMoney(null)).toBe("Unavailable");
  });
});

describe("formatDecisionReason", () => {
  it("formats a standard RouteValue decision", () => {
    expect(formatDecisionReason("faster_and_cheaper")).toBe(
      "Faster and cheaper than the next-best personalized-cost alternative.",
    );
  });
});

describe("formatEligibilityReason", () => {
  it("formats a missing toll reason", () => {
    expect(formatEligibilityReason("missing_toll_cost")).toBe(
      "Toll information is unavailable for this route.",
    );
  });

  it("formats a missing energy reason", () => {
    expect(formatEligibilityReason("missing_energy_estimate")).toBe(
      "Fuel-cost information is unavailable for this route.",
    );
  });
});
