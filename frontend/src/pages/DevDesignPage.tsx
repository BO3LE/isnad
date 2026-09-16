import { Ellipsis, Play, Plus, Trash2 } from "lucide-react";
import { useState, type ReactNode } from "react";
import { Badge } from "@/design-system/components/Badge";
import { Banner } from "@/design-system/components/Banner";
import { Button, type ButtonVariant } from "@/design-system/components/Button";
import { Card } from "@/design-system/components/Card";
import { ConfirmDialog, Dialog } from "@/design-system/components/Dialog";
import { EmptyState } from "@/design-system/components/EmptyState";
import { Field } from "@/design-system/components/Field";
import { IconButton } from "@/design-system/components/IconButton";
import { Input, NumberInput, PasswordInput, SearchInput, Textarea } from "@/design-system/components/Input";
import { Kbd } from "@/design-system/components/Kbd";
import { Menu } from "@/design-system/components/Menu";
import { ProgressBar, Spinner } from "@/design-system/components/Progress";
import { Segmented } from "@/design-system/components/Segmented";
import { Select } from "@/design-system/components/Select";
import { Skeleton, SkeletonCard } from "@/design-system/components/Skeleton";
import { Switch } from "@/design-system/components/Switch";
import { Tabs } from "@/design-system/components/Tabs";
import { useToast } from "@/design-system/components/toast-context";
import { Tooltip } from "@/design-system/components/Tooltip";
import { ChainRule } from "@/design-system/patterns/ChainRule";
import { Contour } from "@/design-system/patterns/Contour";
import { HandoffLines } from "@/design-system/patterns/HandoffLines";
import { StatusChip } from "@/design-system/status/StatusChip";
import { nodeStatusMeta, runStatusMeta } from "@/design-system/status/statusMeta";
import { useTheme, type ThemeChoice } from "@/design-system/theme";
import { formatDuration } from "@/lib/format";

// P-12 (FRONTEND-PAGES-PLAN.md) · DESIGN-SYSTEM.md §25 — every component in every state, both themes.
// Development builds only. Also the visual-regression target for Playwright in W10.

function Section({ title, note, children }: { title: string; note?: string; children: ReactNode }) {
  return (
    <section className="grid gap-4 border-t border-border pt-8">
      <div className="grid gap-1">
        <h2 className="text-heading-lg text-text">{title}</h2>
        {note && <p className="text-body-sm text-text-muted">{note}</p>}
      </div>
      {children}
    </section>
  );
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid gap-2">
      <p className="text-overline uppercase text-text-muted">{label}</p>
      <div className="flex flex-wrap items-center gap-3">{children}</div>
    </div>
  );
}

const BUTTON_VARIANTS: ButtonVariant[] = ["primary", "accent", "secondary", "ghost", "danger", "dangerSecondary", "link"];
const THEME_OPTIONS: { value: ThemeChoice; label: string }[] = [
  { value: "light", label: "Light" },
  { value: "dark", label: "Dark" },
  { value: "system", label: "System" },
];

// §05 — every token in the scale, so the JIT emits them and a change here is visible immediately.
const TYPE_SCALE: { cls: string; token: string; spec: string }[] = [
  { cls: "text-display-lg", token: "display-lg", spec: "56 / 62 · 500 · −2%" },
  { cls: "text-display-md", token: "display-md", spec: "44 / 48 · 500 · −2%" },
  { cls: "font-serif text-display-md", token: "display-md serif", spec: "44 / 48 · 400" },
  { cls: "text-heading-xl", token: "heading-xl", spec: "32 / 38 · 600 · −1%" },
  { cls: "text-heading-lg", token: "heading-lg", spec: "24 / 30 · 600 · −1%" },
  { cls: "text-heading-md", token: "heading-md", spec: "18 / 24 · 600 · −0.5%" },
  { cls: "text-heading-sm", token: "heading-sm", spec: "15 / 22 · 600" },
  { cls: "text-body-lg", token: "body-lg", spec: "16 / 24 · 400" },
  { cls: "text-body-md", token: "body-md", spec: "14 / 21 · 400 — app default" },
  { cls: "text-body-md-strong", token: "body-md-strong", spec: "14 / 21 · 500" },
  { cls: "text-body-sm", token: "body-sm", spec: "13 / 18 · 400 · +0.5%" },
  { cls: "text-caption", token: "caption", spec: "12 / 16 · 500 · +0.5%" },
  { cls: "text-overline uppercase", token: "overline", spec: "11 / 16 · 600 · +6%" },
  { cls: "font-mono text-mono-md", token: "mono-md", spec: "13 / 20 · 400" },
  { cls: "font-mono text-mono-sm", token: "mono-sm", spec: "12 / 16 · 400" },
];

export function DevDesignPage() {
  const toast = useToast();
  const { theme, setTheme } = useTheme();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [length, setLength] = useState<"short" | "medium" | "long">("medium");
  const [approval, setApproval] = useState(true);
  const [tab, setTab] = useState("overview");
  const [topic, setTopic] = useState("");

  return (
    <div className="mx-auto grid w-full max-w-[1200px] gap-8 px-4 py-8 md:px-8">
      <header className="grid gap-2">
        <Badge>Development only</Badge>
        <h1 className="text-heading-xl text-text">Design system</h1>
        <p className="max-w-[60ch] text-body-md text-text-muted">
          Every shared component, in every state. Check changes here before using them in a page, and keep both themes
          working (DESIGN-SYSTEM.md §29).
        </p>
        <div className="flex items-center gap-3 pt-2">
          <Segmented label="Theme" options={THEME_OPTIONS} value={theme} onChange={setTheme} />
        </div>
      </header>

      <Section title="Typography" note="The §05 scale. Serif never below 24 px and never in a control.">
        <div className="grid gap-4">
          {TYPE_SCALE.map((row) => (
            <div key={row.token} className="grid items-baseline gap-1 border-b border-border pb-3 last:border-0 md:grid-cols-[200px_1fr]">
              <div className="grid gap-0.5">
                <span className="font-mono text-mono-sm text-text">{row.token}</span>
                <span className="text-caption text-text-muted">{row.spec}</span>
              </div>
              <p className={`truncate text-text ${row.cls}`}>Your pipeline, one canvas</p>
            </div>
          ))}
        </div>
      </Section>

      <Section title="Buttons" note="One Primary and at most one Accent (Run) per view.">
        <Row label="Variants">
          {BUTTON_VARIANTS.map((variant) => (
            <Button key={variant} variant={variant}>
              {variant}
            </Button>
          ))}
        </Row>
        <Row label="Sizes">
          <Button size="sm">Small</Button>
          <Button size="md">Medium</Button>
          <Button size="lg">Large</Button>
        </Row>
        <Row label="With icon, loading, disabled">
          <Button variant="accent" icon={<Play size={16} aria-hidden />}>
            Run
          </Button>
          <Button variant="primary" loading>
            Saving
          </Button>
          <Tooltip content="Fix 2 issues before running">
            <Button disabled>Disabled</Button>
          </Tooltip>
          <IconButton label="More" icon={<Ellipsis size={16} aria-hidden />} />
          <IconButton label="Delete" variant="secondary" icon={<Trash2 size={16} aria-hidden />} />
        </Row>
      </Section>

      <Section title="Status" note="Color + icon + label — never color alone (§16).">
        <Row label="Node statuses">
          {Object.values(nodeStatusMeta).map((meta) => (
            <StatusChip key={meta.label} meta={meta} />
          ))}
          <StatusChip meta={nodeStatusMeta.retrying} label="Retrying 2/3" />
        </Row>
        <Row label="Run statuses">
          {Object.values(runStatusMeta).map((meta) => (
            <StatusChip key={meta.label} meta={meta} />
          ))}
        </Row>
        <Row label="Badges">
          <Badge>Mock</Badge>
          <Badge tone="generated">✦ Generated</Badge>
          <Badge tone="count">3</Badge>
          <Badge tone="danger">2 issues</Badge>
        </Row>
      </Section>

      <Section title="Forms">
        <div className="grid gap-5 md:grid-cols-2">
          <Field label="Topic" required help="What should the Researcher look into?">
            {({ id, describedBy }) => (
              <Input
                id={id}
                aria-describedby={describedBy}
                value={topic}
                onChange={(event) => setTopic(event.target.value)}
                placeholder="The future of solar energy in Saudi Arabia"
              />
            )}
          </Field>
          <Field label="Recipients" required error="Enter at least one recipient.">
            {({ id, describedBy, invalid }) => <Input id={id} aria-describedby={describedBy} invalid={invalid} defaultValue="" />}
          </Field>
          <Field label="Number of sources">
            {({ id }) => <NumberInput id={id} defaultValue={5} min={1} max={10} unit="sources" />}
          </Field>
          <Field label="Style">
            {({ id }) => (
              <Select
                id={id}
                defaultValue="informative"
                options={[
                  { value: "informative", label: "Informative" },
                  { value: "persuasive", label: "Persuasive" },
                  { value: "conversational", label: "Conversational" },
                  { value: "academic", label: "Academic" },
                ]}
              />
            )}
          </Field>
          <Field label="Password" help="Auth screens only — the only place a password is typed.">
            {({ id, describedBy }) => <PasswordInput id={id} aria-describedby={describedBy} defaultValue="correct-horse" />}
          </Field>
          <Field label="Message" help="Sent with the links.">
            {({ id, describedBy }) => <Textarea id={id} aria-describedby={describedBy} defaultValue="Here's the latest:" />}
          </Field>
          <div className="grid content-start gap-4">
            <div className="grid gap-1.5">
              <span className="text-body-md font-medium">Length</span>
              <Segmented
                label="Length"
                value={length}
                onChange={setLength}
                options={[
                  { value: "short", label: "Short" },
                  { value: "medium", label: "Medium" },
                  { value: "long", label: "Long" },
                ]}
              />
            </div>
            <Switch
              label="Require approval"
              description="Publishing always waits for a person."
              checked={approval}
              onChange={setApproval}
            />
            <SearchInput label="Search agents" value={search} onValueChange={setSearch} placeholder="Search agents" />
          </div>
        </div>
      </Section>

      <Section title="Feedback">
        <Row label="Banners">
          <div className="grid w-full gap-2">
            <Banner variant="approval" action={<Button size="sm">Review</Button>}>
              Publisher is waiting for your approval.
            </Banner>
            <Banner variant="error">Run stopped at Publisher. Your Google connection has expired.</Banner>
            <Banner variant="warning">Your Google connection expires in 2 days.</Banner>
            <Banner variant="info">Editing works best on a larger screen.</Banner>
            <Banner variant="neutral">Running with mock agents — nothing will be published or sent.</Banner>
          </div>
        </Row>
        <Row label="Toasts">
          <Button onClick={() => toast({ variant: "success", message: "Run finished in 6m 12s. 4 files ready." })}>Success</Button>
          <Button onClick={() => toast({ variant: "error", message: "Couldn't save the workflow. Check your connection." })}>
            Error
          </Button>
          <Button onClick={() => toast({ variant: "undo", message: "Writer deleted.", action: { label: "Undo", onClick: () => {} } })}>
            Undo
          </Button>
        </Row>
        <Row label="Dialogs">
          <Button onClick={() => setDialogOpen(true)}>Open dialog</Button>
          <Button variant="danger" onClick={() => setConfirmOpen(true)}>
            Delete workflow
          </Button>
        </Row>
        <Row label="Progress">
          <Spinner label="Loading" />
          <div className="w-48">
            <ProgressBar value={0.4} label="Run progress" />
          </div>
          <div className="w-48">
            <ProgressBar label="Working" />
          </div>
          <span className="font-mono text-mono-sm text-text-muted">{formatDuration(84.2)}</span>
          <Kbd>⌘</Kbd>
          <Kbd>↵</Kbd>
        </Row>
      </Section>

      <Section title="Containers">
        <Row label="Tabs">
          <Tabs
            label="Run sections"
            value={tab}
            onChange={setTab}
            tabs={[
              { id: "overview", label: "Overview" },
              { id: "logs", label: "Logs" },
              { id: "files", label: "Files", badge: <Badge tone="count">2</Badge> },
              { id: "approval", label: "Approval", badge: <span className="h-1.5 w-1.5 rounded-full bg-status-approval-solid" /> },
            ]}
          />
        </Row>
        <div className="grid gap-4 md:grid-cols-3">
          <Card className="grid gap-3">
            <span className="text-heading-sm">Weekly tech digest</span>
            <span className="font-mono text-mono-sm text-text-muted">researcher → writer → video</span>
            <StatusChip meta={runStatusMeta.succeeded} />
          </Card>
          <SkeletonCard />
          <Card className="grid gap-3">
            <Menu
              items={[
                { id: "open", label: "Open", onSelect: () => {} },
                { id: "duplicate", label: "Duplicate", onSelect: () => {} },
                { id: "delete", label: "Delete", danger: true, separated: true, onSelect: () => {} },
              ]}
              trigger={(props) => <Button {...props}>Card menu ▾</Button>}
            />
            <Skeleton className="h-4 w-2/3" />
            <Skeleton className="h-4 w-1/3" />
          </Card>
        </div>
      </Section>

      <Section title="Patterns" note="§07. Ornament comes only from here, and each pattern has one meaning.">
        <div className="grid gap-4 md:grid-cols-3">
          <Card className="grid gap-3">
            <span className="text-heading-sm">P-02 Handoff lines</span>
            <span className="text-body-sm text-text-muted">Work moving through the chain. Auth hero and covers only.</span>
            <div className="gradient-handoff grain relative h-28 overflow-hidden rounded-sm">
              <HandoffLines className="absolute inset-0 h-full w-full text-[#9fb6ff] opacity-40" />
            </div>
          </Card>
          <Card className="grid gap-3">
            <span className="text-heading-sm">P-05 Chain rule</span>
            <span className="text-body-sm text-text-muted">A section boundary. Never a row divider.</span>
            <div className="grid h-28 place-items-center">
              <ChainRule className="h-3 w-48 text-border-strong" />
            </div>
          </Card>
          <Card className="grid gap-3">
            <span className="text-heading-sm">P-06 Contour</span>
            <span className="text-body-sm text-text-muted">Space waiting to be filled. Empty states, never errors.</span>
            <div className="grid h-28 place-items-center">
              <Contour className="h-24 w-32 text-border-strong" />
            </div>
          </Card>
        </div>
      </Section>

      <Section title="Empty states">
        <div className="grid gap-4 md:grid-cols-2">
          <Card padding="compact">
            <EmptyState
              title="Build your first chain"
              body="Start from a template or drag agents onto a blank canvas."
              actions={
                <>
                  <Button>Use a template</Button>
                  <Button variant="primary" icon={<Plus size={16} aria-hidden />}>
                    New workflow
                  </Button>
                </>
              }
            />
          </Card>
          <Card padding="compact">
            <EmptyState art={false} title="No files were created" body="The run stopped before any step produced a file." actions={<Button>View logs</Button>} />
          </Card>
        </div>
      </Section>

      <Dialog
        open={dialogOpen}
        onClose={() => setDialogOpen(false)}
        title="Reject and stop this run?"
        description="Publisher won't upload anything."
        footer={
          <>
            <Button onClick={() => setDialogOpen(false)}>Back</Button>
            <Button variant="danger" onClick={() => setDialogOpen(false)}>
              Reject
            </Button>
          </>
        }
      >
        <Field label="Note" required help="Tell future you why.">
          {({ id, describedBy }) => <Textarea id={id} aria-describedby={describedBy} rows={2} />}
        </Field>
      </Dialog>

      <ConfirmDialog
        open={confirmOpen}
        onClose={() => setConfirmOpen(false)}
        onConfirm={() => {
          setConfirmOpen(false);
          toast({ message: "Deleted “Weekly tech digest”." });
        }}
        title="Delete “Weekly tech digest”?"
        description="Its 12 runs and their files will be deleted. This can't be undone."
        confirmLabel="Delete workflow"
      />
    </div>
  );
}
