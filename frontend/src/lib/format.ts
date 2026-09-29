// Number, duration and time formats — DESIGN-SYSTEM.md §23.1.

/** Live elapsed or final duration, in the format from DESIGN-SYSTEM.md §23.1. */
export function formatDuration(seconds: number): string {
  if (seconds < 60) return `${seconds.toFixed(1)} s`;
  const minutes = Math.floor(seconds / 60);
  const rest = Math.round(seconds % 60);
  if (minutes < 60) return `${minutes}m ${String(rest).padStart(2, "0")}s`;
  return `${Math.floor(minutes / 60)}h ${String(minutes % 60).padStart(2, "0")}m`;
}

export function formatClock(seconds: number): string {
  const minutes = Math.floor(seconds / 60);
  return `${minutes}:${String(Math.floor(seconds % 60)).padStart(2, "0")}`;
}

const RELATIVE_ABSOLUTE = new Intl.DateTimeFormat("en-GB", {
  day: "numeric",
  month: "short",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});

/**
 * DESIGN-SYSTEM.md §23.1 — "just now" under a minute, then minutes, hours, days, then the
 * absolute date. Anything older than a week gets a real date, because "47d ago" helps nobody.
 */
export function formatRelativeTime(value: string | Date, now: Date = new Date()): string {
  const date = typeof value === "string" ? new Date(value) : value;
  if (Number.isNaN(date.getTime())) return "";

  const seconds = Math.round((now.getTime() - date.getTime()) / 1000);
  if (seconds < 0) return "just now";
  if (seconds < 60) return "just now";

  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes} min ago`;

  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;

  const days = Math.floor(hours / 24);
  if (days < 7) return `${days}d ago`;

  return formatAbsoluteTime(date);
}

/** `14 Sep 2026, 16:05` — 24-hour clock, day before month (§23.1). */
export function formatAbsoluteTime(value: string | Date): string {
  const date = typeof value === "string" ? new Date(value) : value;
  if (Number.isNaN(date.getTime())) return "";
  return RELATIVE_ABSOLUTE.format(date).replace(",", ",");
}

/** The zone a log table's timestamps are read in (§21 S-07 offers both). */
export type TimeZonePreference = "local" | "utc";

const TIME_OF_DAY = new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });
const TIME_OF_DAY_UTC = new Intl.DateTimeFormat("en-GB", {
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hour12: false,
  timeZone: "UTC",
});

/**
 * `16:05:02` — the log table's clock (§21 S-07), in the reader's own zone or in UTC.
 *
 * Seconds matter here in a way they do not elsewhere: steps finish within seconds of each other,
 * and a table that rounded to the minute would show several rows starting at the same time.
 */
export function formatTimeOfDay(value: string | Date, zone: TimeZonePreference = "local"): string {
  const date = typeof value === "string" ? new Date(value) : value;
  if (Number.isNaN(date.getTime())) return "";
  return (zone === "utc" ? TIME_OF_DAY_UTC : TIME_OF_DAY).format(date);
}

/** "1 step" / "5 steps" — numerals always, pluralised correctly (§23.1). */
export function pluralise(count: number, singular: string, plural = `${singular}s`): string {
  return `${count} ${count === 1 ? singular : plural}`;
}

/**
 * A file size as §23.1 writes it: 1 KB is 1000 bytes, and anything under 10 of its unit keeps one
 * decimal — "312 KB", "4.2 MB", "24 MB".
 */
export function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes < 0) return "";
  if (bytes < 1000) return `${Math.round(bytes)} B`;
  const units = ["KB", "MB", "GB", "TB"];
  let value = bytes / 1000;
  let unit = 0;
  // Step up on what will be *shown*, not on the raw value: 999,999 B rounds to 1000, which has to
  // read "1.0 MB" rather than "1000 KB".
  while (Math.round(value) >= 1000 && unit < units.length - 1) {
    value /= 1000;
    unit += 1;
  }
  return `${value < 10 ? value.toFixed(1) : Math.round(value)} ${units[unit]}`;
}
