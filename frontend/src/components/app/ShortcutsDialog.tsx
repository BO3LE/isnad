import { Dialog } from "@/design-system/components/Dialog";
import { Kbd } from "@/design-system/components/Kbd";

// DESIGN-SYSTEM.md §13 — opened with "?" from anywhere, and from the user menu.
// Canvas-only shortcuts are listed here but implemented with the canvas in Part 3.
const GROUPS: { title: string; rows: { keys: string[]; action: string }[] }[] = [
  {
    title: "Anywhere",
    rows: [
      { keys: ["?"], action: "Keyboard shortcuts" },
      { keys: ["Esc"], action: "Close dialog, menu or drawer" },
      { keys: ["Tab"], action: "Move through the page" },
    ],
  },
  {
    title: "Canvas",
    rows: [
      { keys: ["Enter"], action: "Configure the focused step" },
      { keys: ["C"], action: "Start a connection" },
      { keys: ["⌫"], action: "Delete the selected step or connection" },
      { keys: ["⌘", "D"], action: "Duplicate the step" },
      { keys: ["⌘", "Z"], action: "Undo" },
      { keys: ["⌘", "↵"], action: "Run workflow" },
      { keys: ["+", "-", "0"], action: "Zoom in, out, fit" },
    ],
  },
  {
    title: "Logs",
    rows: [{ keys: ["F"], action: "Focus the filter" }],
  },
];

export function ShortcutsDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  return (
    <Dialog open={open} onClose={onClose} title="Keyboard shortcuts" size="content">
      <div className="grid gap-5">
        {GROUPS.map((group) => (
          <section key={group.title} className="grid gap-2">
            <h3 className="text-overline uppercase text-text-muted">{group.title}</h3>
            <dl className="grid gap-1.5">
              {group.rows.map((row) => (
                <div key={row.action} className="flex items-center justify-between gap-4 text-body-md">
                  <dt className="text-text">{row.action}</dt>
                  <dd className="flex gap-1">
                    {row.keys.map((key) => (
                      <Kbd key={key}>{key}</Kbd>
                    ))}
                  </dd>
                </div>
              ))}
            </dl>
          </section>
        ))}
      </div>
    </Dialog>
  );
}
