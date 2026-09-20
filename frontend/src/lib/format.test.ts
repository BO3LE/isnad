import { formatBytes, formatDuration, formatRelativeTime, pluralise } from "./format";

const NOW = new Date("2026-09-16T12:00:00Z");
const ago = (seconds: number) => new Date(NOW.getTime() - seconds * 1000);

describe("formatRelativeTime (§23.1)", () => {
  it("says just now under a minute", () => {
    expect(formatRelativeTime(ago(5), NOW)).toBe("just now");
    expect(formatRelativeTime(ago(59), NOW)).toBe("just now");
  });

  it("counts minutes, then hours, then days", () => {
    expect(formatRelativeTime(ago(12 * 60), NOW)).toBe("12 min ago");
    expect(formatRelativeTime(ago(3 * 3600), NOW)).toBe("3h ago");
    expect(formatRelativeTime(ago(2 * 86400), NOW)).toBe("2d ago");
  });

  // "47d ago" helps nobody — past a week it becomes a real date.
  it("switches to an absolute date after a week", () => {
    expect(formatRelativeTime(ago(30 * 86400), NOW)).toMatch(/\d{4}/);
  });

  it("does not produce a negative age from clock skew", () => {
    expect(formatRelativeTime(new Date(NOW.getTime() + 5000), NOW)).toBe("just now");
  });

  it("returns an empty string for an unusable date rather than 'Invalid Date'", () => {
    expect(formatRelativeTime("not a date", NOW)).toBe("");
  });
});

describe("pluralise", () => {
  it("pluralises correctly", () => {
    expect(pluralise(1, "step")).toBe("1 step");
    expect(pluralise(5, "step")).toBe("5 steps");
    expect(pluralise(0, "step")).toBe("0 steps");
  });
});

describe("formatDuration", () => {
  it("uses one decimal under a minute and m/s above", () => {
    expect(formatDuration(18.4)).toBe("18.4 s");
    expect(formatDuration(84.2)).toBe("1m 24s");
  });
});

describe("formatBytes", () => {
  it("writes sizes the way §23.1 does — 1 KB is 1000 bytes", () => {
    expect(formatBytes(312_000)).toBe("312 KB");
    expect(formatBytes(24_000_000)).toBe("24 MB");
  });

  it("keeps one decimal under ten of a unit", () => {
    expect(formatBytes(4_200_000)).toBe("4.2 MB");
    expect(formatBytes(4036)).toBe("4.0 KB");
  });

  it("leaves small files in bytes, and says nothing about a size it cannot read", () => {
    expect(formatBytes(0)).toBe("0 B");
    expect(formatBytes(999)).toBe("999 B");
    expect(formatBytes(-1)).toBe("");
    expect(formatBytes(Number.NaN)).toBe("");
  });
});
