// DESIGN-SYSTEM.md §14.21 — initials only; there are no profile pictures in this system.
export function Avatar({ email, size = 32 }: { email: string; size?: number }) {
  const initials = email
    .split("@")[0]
    ?.split(/[.\-_+]/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("");

  return (
    <span
      aria-hidden
      style={{ width: size, height: size }}
      className="grid shrink-0 place-items-center rounded-full bg-bg-sunken text-caption font-semibold text-text"
    >
      {initials || "?"}
    </span>
  );
}
