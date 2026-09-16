import type { StatusMeta } from "./statusMeta";

/** Color + icon + label — never color alone (DESIGN-SYSTEM.md §13). */
export function StatusChip({ meta, label }: { meta: StatusMeta; label?: string }) {
  const Icon = meta.icon;
  return (
    <span
      className={`inline-flex h-[22px] w-fit items-center gap-1 justify-self-start whitespace-nowrap rounded-xs px-1.5 text-caption bg-status-${meta.tone}-bg text-status-${meta.tone}-fg`}
      data-tone={meta.tone}
    >
      <Icon aria-hidden size={13} strokeWidth={1.75} className={meta.spin ? "animate-spin" : undefined} />
      {label ?? meta.label}
    </span>
  );
}
