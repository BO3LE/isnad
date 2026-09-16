import { Link } from "react-router-dom";

// DESIGN-SYSTEM.md §14.22 — the breadcrumb carries the navigation; there is no global sidebar.
export interface Crumb {
  label: string;
  to?: string;
}

export function Breadcrumb({ items }: { items: Crumb[] }) {
  const last = items.at(-1);
  return (
    <nav aria-label="Breadcrumb" className="min-w-0 flex-1">
      {/* Small screens: one step back. */}
      <Link
        to={items.at(-2)?.to ?? "/workflows"}
        className="text-body-md text-text-muted hover:text-text hover:no-underline md:hidden"
      >
        ← {items.at(-2)?.label ?? "Workflows"}
      </Link>
      <ol className="hidden min-w-0 items-center gap-1.5 text-body-md md:flex">
        {items.map((item, index) => (
          <li key={`${item.label}-${index}`} className="flex min-w-0 items-center gap-1.5">
            {index > 0 && (
              <span aria-hidden className="text-text-subtle">
                /
              </span>
            )}
            {item.to && item !== last ? (
              <Link to={item.to} className="shrink-0 text-text-muted hover:text-text">
                {item.label}
              </Link>
            ) : (
              <span aria-current="page" className="truncate font-medium text-text">
                {item.label}
              </span>
            )}
          </li>
        ))}
      </ol>
    </nav>
  );
}
