import { X } from "lucide-react";
import { useRef, useState, type KeyboardEvent } from "react";

// DESIGN-SYSTEM.md §14.6 — a list of short values as removable chips. Enter, comma or leaving the
// field adds what was typed; Backspace in an empty field removes the last chip.
export interface TagInputProps {
  id?: string;
  label: string;
  value: string[];
  onChange: (value: string[]) => void;
  /** Checks one item before it is added; return a message to refuse it. */
  check?: (item: string) => string | null;
  /** Reports a refused item (or null once the problem is gone) so the field can show it. */
  onError?: (message: string | null) => void;
  placeholder?: string;
  invalid?: boolean;
  describedBy?: string;
  disabled?: boolean;
  onFocus?: () => void;
}

export function TagInput({ id, label, value, onChange, check, onError, placeholder, invalid, describedBy, disabled, onFocus }: TagInputProps) {
  const [draft, setDraft] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  function commit(): boolean {
    const items = draft
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean);
    if (items.length === 0) return false;
    for (const item of items) {
      const problem = check?.(item) ?? null;
      if (problem) {
        onError?.(problem);
        return false;
      }
    }
    onError?.(null);
    const next = [...value];
    for (const item of items) if (!next.includes(item)) next.push(item);
    onChange(next);
    setDraft("");
    return true;
  }

  function onKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "Enter" || event.key === ",") {
      event.preventDefault();
      commit();
    } else if (event.key === "Backspace" && draft === "" && value.length > 0) {
      onChange(value.slice(0, -1));
    }
  }

  return (
    <div
      onClick={() => inputRef.current?.focus()}
      className={`flex min-h-9 w-full flex-wrap items-center gap-1.5 rounded-sm border bg-surface px-2 py-1.5 transition-colors duration-100 ease-standard ${
        invalid
          ? "border-status-failed-solid"
          : "border-border-strong focus-within:border-focus hover:border-border-hover"
      } ${disabled ? "cursor-not-allowed bg-bg-sunken" : "cursor-text"}`}
    >
      <ul className="contents list-none" aria-label={label}>
        {value.map((item) => (
          <li key={item} className="inline-flex h-[22px] items-center gap-1 rounded-xs bg-bg-sunken pl-2 pr-0.5 text-caption text-text">
            {item}
            <button
              type="button"
              disabled={disabled}
              aria-label={`Remove ${item}`}
              onClick={(event) => {
                event.stopPropagation();
                onChange(value.filter((other) => other !== item));
              }}
              className="grid h-[18px] w-[18px] place-items-center rounded-xs text-text-muted hover:bg-surface-hover hover:text-text"
            >
              <X size={12} aria-hidden />
            </button>
          </li>
        ))}
      </ul>
      <input
        ref={inputRef}
        id={id}
        value={draft}
        disabled={disabled}
        aria-invalid={invalid || undefined}
        aria-describedby={describedBy}
        placeholder={value.length === 0 ? placeholder : undefined}
        onChange={(event) => {
          setDraft(event.target.value);
          if (invalid) onError?.(null);
        }}
        onKeyDown={onKeyDown}
        onFocus={onFocus}
        onBlur={commit}
        className="h-6 min-w-[8ch] flex-1 bg-transparent text-body-md text-text outline-none placeholder:text-text-subtle"
      />
    </div>
  );
}
