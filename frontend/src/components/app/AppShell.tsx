import { CircleHelp, Keyboard, KeyRound, LogOut, Monitor, Moon, Sun } from "lucide-react";
import type { ReactNode } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Avatar } from "@/design-system/components/Avatar";
import { IconButton } from "@/design-system/components/IconButton";
import { Menu, type MenuItem } from "@/design-system/components/Menu";
import { Tooltip } from "@/design-system/components/Tooltip";
import { useTheme, type ThemeChoice } from "@/design-system/theme";
import { useAuth } from "@/lib/auth";
import { Breadcrumb, type Crumb } from "./Breadcrumb";
import { Logo } from "./Logo";
import { ShortcutsDialog } from "./ShortcutsDialog";
import { useShortcutsDialog } from "./useShortcutsDialog";

// DESIGN-SYSTEM.md §10 and §19 — a 56 px top bar and no global sidebar.
export interface AppShellProps {
  crumbs: Crumb[];
  /** Page-specific controls, right-aligned before the help and user menu. */
  actions?: ReactNode;
  /** Filled by the canvas with save status. */
  status?: ReactNode;
  children: ReactNode;
  /** The canvas manages its own scrolling. */
  fullBleed?: boolean;
}

const THEME_ICONS: Record<ThemeChoice, typeof Sun> = { light: Sun, dark: Moon, system: Monitor };
const THEME_ORDER: ThemeChoice[] = ["light", "dark", "system"];
const THEME_LABELS: Record<ThemeChoice, string> = { light: "Light", dark: "Dark", system: "System" };

export function AppShell({ crumbs, actions, status, children, fullBleed = false }: AppShellProps) {
  const { email, signOut } = useAuth();
  const { theme, setTheme } = useTheme();
  const shortcuts = useShortcutsDialog();
  const navigate = useNavigate();

  const nextTheme = THEME_ORDER[(THEME_ORDER.indexOf(theme) + 1) % THEME_ORDER.length] ?? "system";
  const ThemeIcon = THEME_ICONS[theme];

  const menuItems: MenuItem[] = [
    {
      id: "connections",
      label: "Connections",
      icon: <KeyRound size={16} aria-hidden />,
      onSelect: () => navigate("/settings/connections"),
    },
    {
      id: "shortcuts",
      label: "Keyboard shortcuts",
      icon: <Keyboard size={16} aria-hidden />,
      shortcut: "?",
      onSelect: () => shortcuts.setOpen(true),
    },
    {
      id: "theme",
      label: `Theme: ${THEME_LABELS[theme]}`,
      icon: <ThemeIcon size={16} aria-hidden />,
      onSelect: () => setTheme(nextTheme),
    },
    {
      id: "signout",
      label: "Sign out",
      icon: <LogOut size={16} aria-hidden />,
      separated: true,
      onSelect: signOut,
    },
  ];

  return (
    <div className="flex h-full flex-col">
      <header className="flex h-14 shrink-0 items-center gap-3 border-b border-border bg-surface px-4">
        <Link to="/workflows" aria-label="Workflows" className="shrink-0 text-text hover:opacity-80">
          <Logo />
        </Link>
        <Breadcrumb items={crumbs} />
        {status}
        {actions}
        <Tooltip content="Keyboard shortcuts">
          <IconButton label="Keyboard shortcuts" icon={<CircleHelp size={18} aria-hidden />} onClick={() => shortcuts.setOpen(true)} />
        </Tooltip>
        <Menu
          items={menuItems}
          trigger={(props) => (
            <button
              {...props}
              type="button"
              className="flex items-center gap-2 rounded-full p-0.5 hover:bg-surface-hover"
              aria-label={`Account menu for ${email ?? "your account"}`}
            >
              <Avatar email={email ?? ""} />
            </button>
          )}
        />
      </header>
      <main className={fullBleed ? "flex min-h-0 flex-1" : "min-h-0 flex-1 overflow-y-auto"}>{children}</main>
      <ShortcutsDialog open={shortcuts.open} onClose={() => shortcuts.setOpen(false)} />
    </div>
  );
}

/** Standard page header for the centred layouts (DESIGN-SYSTEM.md §10). */
export function PageHeader({ title, description, actions }: { title: string; description?: string; actions?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-4">
      <div className="grid gap-1">
        <h1 className="text-heading-xl text-text">{title}</h1>
        {description && <p className="text-body-md text-text-muted">{description}</p>}
      </div>
      {actions}
    </div>
  );
}

/** Centred content column: 1200 px, with the gutters from §10. */
export function PageBody({ children, width = "default" }: { children: ReactNode; width?: "default" | "wide" | "narrow" }) {
  const widths = { narrow: "max-w-[960px]", default: "max-w-[1200px]", wide: "max-w-[1440px]" } as const;
  return <div className={`mx-auto grid w-full gap-6 px-4 py-8 md:px-8 ${widths[width]}`}>{children}</div>;
}
