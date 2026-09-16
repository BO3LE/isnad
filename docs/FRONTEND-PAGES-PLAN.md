# Frontend Pages Plan — GP Visual AI-Agent Workflow Platform

| | |
|---|---|
| **Component** | C1 `frontend` |
| **Status** | Planning document — no pages or components implemented from this plan yet |
| **Date** | 15 September 2026 (W1) |
| **Based on** | [`GP-plan.md`](GP-plan.md) · [`DESIGN-SYSTEM.md`](DESIGN-SYSTEM.md) · [`DECISIONS.md`](DECISIONS.md) · [`ADDING_AN_AGENT.md`](ADDING_AN_AGENT.md) |

There are no separate "Requirements", "Architecture" or "User roles" files. That material lives inside `GP-plan.md` (Requirements §8.1, Architecture Part 2 and §5.1, API §5.3, Test Cases §8.3) and `DESIGN-SYSTEM.md` (screens §19–§22, flows §20, components §14–§18). Codes such as S-01 and F-03 refer to screen and flow numbers in `DESIGN-SYSTEM.md`.

Anything the documentation does not settle is marked **Needs clarification** and collected in [Documentation Gaps / Questions](#documentation-gaps--questions).

---

## Contents

1. [Frontend Scope](#1-frontend-scope)
2. [User Roles](#2-user-roles)
3. [Complete Page List](#3-complete-page-list)
4. [Page Categories](#4-page-categories)
5. [Navigation Structure](#5-navigation-structure)
6. [User Flows](#6-user-flows)
7. [Page Dependencies](#7-page-dependencies)
8. [Reusable Frontend Components](#8-reusable-frontend-components)
9. [Frontend Development Order](#9-frontend-development-order)
10. [Final Page Count](#10-final-page-count)
11. [Documentation Gaps / Questions](#documentation-gaps--questions)

---

## 1. Frontend Scope

The frontend is **C1 `frontend`** (GP-plan Part 2). From the docs, it is responsible for:

| Responsibility | Source |
|---|---|
| **Screens:** Auth, Workflow list, Canvas, Config drawer, Run monitor, Approval, Logs, Outputs | GP-plan §5.1 Layer 1 |
| **Connections screen** for Google accounts and the **credential picker** in the config drawer | GP-plan W6; DESIGN-SYSTEM S-09, §17.3 |
| **Drag-and-drop workflow canvas** (FR-01, UC-01) | GP-plan §8.1 |
| **Agent configuration** with no code, using forms built automatically from `GET /agents/catalog` (UC-03, NFR-04) | GP-plan W3; DS §17 |
| **Live run status** through a Realtime subscription, or 2-second polling (UC-02) | GP-plan W3, §5.1 |
| **Human approval** before publishing (UC-04) | GP-plan W7 |
| **Log viewer** with retries, durations, errors and CSV export (UC-06, FR-06) | GP-plan W9 |
| **Downloads and published links** (FR-04, FR-05) | GP-plan W4, W6 |
| **Loading, empty and error states** on every screen; readable errors instead of stack traces | GP-plan W4, W6; RB-03 |
| **Usable by non-technical people** (NFR-03), WCAG 2.1 AA | GP-plan §8.1; DS §13 |

**What the frontend must not do** (GP-plan C1 and §5.1 invariants):
- It must not know about Celery, Redis, the database, how agents work inside, or any external API key.
- It never calls an LLM or external content API directly.
- It never invents its own validation rules. It shows exactly what `/validate` returns.
- It never puts secrets in the workflow graph.
- It talks to the backend only through the REST API (types generated from `openapi.json`), plus Realtime and signed-URL downloads.

**How it is tested:**
- Vitest for components.
- Playwright against a mocked API, so it runs with the entire backend stopped.

**Out of scope for the frontend** (M1 §3.2): chat or voice creation, roles, teams, sharing, a mobile app, Arabic localisation, and advanced video editing.

> **Current state:** the infrastructure setup already added simple skeletons for `/login` (dev sign-in), `/workflows`, `/workflows/:id` and `/runs/:id`, plus a 404 page. This plan treats them as placeholders to rebuild to the design spec.

---

## 2. User Roles

The docs define **one authenticated role**. Roles, permissions, teams and sharing are explicitly out of scope (M1 §3.2, GP-plan Home, DS §14.21). Each user only ever sees their own data, enforced by database row-level security.

| Role | Definition in the docs | Frontend access |
|---|---|---|
| **Visitor** (not signed in) | Anyone without a session | Sign in, Create account, Not found. Every other route redirects to `/login?next=…`. |
| **User / Creator** (signed in) | A non-technical content creator (DS §01 audiences) | Every product page, **limited to their own** workflows, runs, outputs and connections. Other users' items return "not found". |
| *Developer* (not a frontend role) | Adds agents by dropping a folder in (AT-12) | No UI of their own. The frontend must show new agents automatically. |
| *Development environment* (not a role) | `ENVIRONMENT=development` | Shows extras: "Run with mock agents" in the Run menu, the "Mock agents" badge, `/dev/design` |
| *Evaluator* (supervisor, committee) | A design-system audience only | No separate role. They use a normal account or the demo account. |

- **Admin role:** none. The docs exclude it, so this plan has **no admin pages**.
- **Needs clarification:** whether the supervisor needs anything beyond a demo account.

---

## 3. Complete Page List

The config drawer, validation panel and dialogs live *inside* pages and don't have routes, so they are described under their host page and listed at the end of this section.

---

### P-01 · Sign in
- **Route:** `/login` · **Access:** Visitor · **Spec:** DS S-01
- **Purpose:** get a returning user into their workflows in under 10 seconds.
- **Main sections:**
  - Form column: logo, "Sign in" title, email, password with show/hide, "Forgot?" link, primary button, "New here? Create an account", KFU · CCSIT footer.
  - Hero panel on large screens: G-1 gradient with the P-02 line pattern and a serif headline.
  - On mobile, the hero becomes a 160 px gradient strip.
- **Data shown:** none.
- **Actions:** sign in, go to Create account, forgot password (**needs clarification**: no flow is specified).
- **Forms:** sign-in form (email, password).
- **Tables / filters:** none.
- **States:**
  - Loading: button spinner, fields read-only.
  - Empty: not applicable.
  - Error: form alert "That email and password don't match." or "Too many attempts. Try again in a minute."
  - Success: redirect to `next` or `/workflows`.
- **API:** `POST /auth/login` (§5.3, delegated to Supabase if D-01 is approved). Today only `POST /auth/dev-login` exists.
- **Links to:** `/register`, `/workflows`.

### P-02 · Create account
- **Route:** `/register` · **Access:** Visitor · **Spec:** DS S-01
- **Purpose:** create an account without friction.
- **Main sections:** same layout as P-01. Title "Create account"; adds a confirm-password field and password rules.
- **Data shown:** the password rule "At least 8 characters", with a live check mark.
- **Actions:** create account, go to Sign in.
- **Forms:** registration (email, password, confirm password).
- **Tables / filters:** none.
- **States:**
  - Loading: button spinner.
  - Error: field errors (invalid email, passwords don't match) and a server error such as email already registered (**wording needs clarification**).
  - Success: redirect to `/workflows`, which shows its first-visit empty state (F-01).
- **API:** `POST /auth/register` (§5.3). Not built yet; waits on D-01.
- **Links to:** `/login`, `/workflows`.

### P-03 · Workflows (home)
- **Route:** `/workflows` (and `/` redirects here) · **Access:** User · **Spec:** DS S-02 · **Requirement:** UC-01 · **Test:** AT-01
- **Purpose:** see every saved workflow and its last run at a glance, and start a new one.
- **Main sections:**
  - Page header: title, description, primary "New workflow" button.
  - Toolbar: search, sort, grid/table view toggle.
  - "Start from a template" row with 3 cards. Hidden once the user has 3 or more workflows.
  - "Your workflows" as a grid or table.
- **Data shown (per workflow):** name; agent icons in order (max 6, then "+N"); last-run status chip and relative time; last edited. If a run is waiting for approval, a violet chip and a **Review** link.
- **Actions:**
  - New workflow, which creates "Untitled workflow" and opens the canvas.
  - Use a template.
  - Open, Rename, Duplicate, Delete (with a confirm dialog).
  - Review a pending approval.
- **Forms:** inline rename. Search input.
- **Tables:** table view with columns name · steps · last run · last edited · actions.
- **Filters / search:** search by name. Sort by Last edited (default), Name or Last run.
- **States:**
  - Loading: 6 skeleton cards.
  - Empty, first visit: "Build your first chain" with the P-06 contour art and two buttons (use a template, new workflow).
  - Empty, no search match: "No workflows match '…'" with Clear search.
  - Error: inline alert with Retry.
  - Success: delete removes the card. Create goes straight to the canvas.
- **API:** `GET /workflows` (with last-run summary), `POST /workflows`, `PUT /workflows/{id}` (rename), `DELETE /workflows/{id}`.
  - Duplicate: **no endpoint specified**.
  - Templates source: **needs clarification** (see gaps).
- **Links to:** `/workflows/:id`, `/runs/:runId/approve/:nodeId`, the user menu.

### P-04 · Workflow Canvas (with Config Drawer)
- **Route:** `/workflows/:workflowId` · **Access:** User (owner) · **Spec:** DS S-03, S-04, §15, §17
- **Requirements:** FR-01, FR-02, UC-01, UC-02, UC-03, NFR-04 · **Tests:** AT-01, AT-02, AT-07, AT-08, AT-12
- **Purpose:** build a workflow by dragging and connecting agents, configure each agent, then validate, run and watch it.

**Main sections**
- **Top bar:**
  - Logo and breadcrumb; workflow name editable inline.
  - Save status: "Saving…", "Saved · just now", "Not saved — retrying".
  - Validate button and the Run split button.
  - During a run, the Run button becomes Cancel run.
- **Agent palette** (left, 264 px, collapsible):
  - Search.
  - Groups CREATE (Researcher, Writer, Image, Video) and DISTRIBUTE (Publisher, Email), with a Gate symbol on approval agents.
  - Templates link.
- **Canvas:** dot grid, agent nodes, connections, zoom and fit controls, minimap, right-click menu, empty state "Start your chain".
- **Config drawer** (right, 400 px, or a bottom sheet on mobile):
  - Tabs *Settings* and *Last output*.
  - A form built from the agent's schema.
  - Sticky footer with the Require approval switch and save status.
- **Validation panel** (docked above the status bar): the list of issues, each with a "Go to node" or direct fix button.
- **Status bar:** step count · validation state · last run chip with "View run" · zoom · "Mock agents" badge.
- **Run mode overlay** (DS §15.10): run header with elapsed time, progress, View logs and Cancel. Editing is locked while a run is in progress.

**Data shown**
- The workflow graph: nodes, edges, positions, configuration, requires_approval.
- The agent catalog: title, description, family, icon, config schema, requires_approval.
- Validation issues.
- Live node status during a run.

**Actions**
- Drag an agent onto the canvas, or add one with the keyboard.
- Connect or disconnect nodes; delete, with an Undo toast.
- Duplicate a node; toggle Require approval (locked on for Publisher and Email, D-08).
- Rename the workflow; autosave 800 ms after the last change; undo and redo.
- Validate, Run, Cancel run.
- "Tidy up" automatic layout (P2, proposed).
- Keyboard shortcuts (DS §13).

**Forms**
- Config drawer schema form. Field types:
  - text, textarea, number or slider, select, segmented, radio cards, switch, tag input
  - credential picker
  - upstream binding chip
- Inline workflow name.

**Tables:** none. **Filters / search:** palette search.

**States**
- Loading: skeleton top bar and a spinner on the canvas; 6 skeleton palette items.
- Empty canvas: "Start your chain" on the contour pattern with "Use a template".
- Errors:
  - Catalog failed: palette alert "Couldn't load agents. [Retry]".
  - Save failed: top-bar status.
  - Invalid graph: red dashed nodes and edges plus the panel.
  - Missing or foreign workflow: full-page not-found.
  - Queue unavailable (503): error toast.
- Success: "✓ Ready to run" for 2 seconds. When a run finishes, a burst animation and the toast "Run finished in X. N files ready. [View files]".

**API**
- `GET /workflows/{id}`, `PUT /workflows/{id}`, `GET /agents/catalog`, `POST /workflows/{id}/validate`, `POST /workflows/{id}/run` (returns 202).
- Run mode: `GET /runs/{id}` plus Realtime or 2-second polling; `POST /runs/{id}/cancel`.
- Credential picker: **credentials endpoints not specified** (D-09).
- "Last output" tab: **no endpoint specified**.

**Links to:** `/workflows`, `/runs/:runId` ("View run"), `/runs/:runId/logs`, `/settings/connections` ("Connect Google").
**Needs clarification:** whether pressing Run keeps the user on the canvas in run mode (§15.10) or navigates to the run monitor (§21 S-05).

### P-05 · Run History
- **Route:** `/workflows/:workflowId/runs` · **Access:** User (owner) · **Spec:** DS §19 IA only. **No screen specification exists.**
- **Purpose:** list past runs of one workflow (UC-02, UC-06).
- **Main sections:** page header (workflow name, breadcrumb) and a runs list.
- **Data shown:** each run's status chip, created time, completed time. Duration can be derived.
- **Actions:** open a run; go back to the canvas.
- **Forms:** none.
- **Tables:** runs table with columns run · status · started · finished · duration.
- **Filters:** **not specified**. The API returns the latest 50 runs; pagination is not specified.
- **States:**
  - Loading: skeleton rows.
  - Empty: "No runs yet — Press Run on the canvas to start this workflow." with Open canvas (DS §18.2).
  - Error: inline alert with Retry.
- **API:** `GET /workflows/{id}/runs`.
- **Links to:** `/runs/:runId`, `/workflows/:workflowId`.

### P-06 · Run Monitor (Overview)
- **Route:** `/runs/:runId` · **Access:** User (owner) · **Spec:** DS S-05 · **Requirements:** UC-02, FR-06, NFR-01 · **Tests:** AT-07, AT-11
- **Purpose:** follow a run in real time and act on it: approve, cancel, view logs, get files.

**Main sections**
- **Run header:** "Run #n" · run status chip · start time · live elapsed time · "x of y steps" · progress bar · Cancel run.
- **Banners:**
  - Approval (violet) with a Review button.
  - Failure (red) with the cause and a fix action.
  - Cancelled (neutral).
  - Mock mode notice.
- **Tabs:** Overview · Logs · Files (with count) · Approval (violet dot, only while something is pending).
- **Overview:** read-only canvas (60%) beside a Steps list (40%); stacked on narrow screens.
- **Steps list rows** (expandable): step number, agent icon and name, status chip, duration, attempts and error.
  - This list is the accessible alternative to the canvas.

**Data shown**
- Run status, times, total and failed node counts.
- For each node: status, retry count, started, completed, duration, error message.
- Retry countdown ("Attempt 2 of 3 · next in ~4s").
- For long nodes, a card saying "Video is rendering… You can leave this page."

**Actions:** Cancel run (confirm dialog), Review (to approval), View logs, View files, Run again (after the run ends), open a step's detail.
**Forms:** the cancel confirmation dialog.
**Tables:** none; the Steps list is a list.
**Filters:** none.

**States**
- Loading: skeletons.
- Empty: not applicable.
- Errors: run not found (full-page); failure banner.
- Success: green header chip, burst animation, "Run again" and "View files".
- Live: aria-live announcements, browser tab title and favicon dot reflect status (DS §16.6).

**API**
- `GET /runs/{id}` plus a Realtime subscription on `execution_logs` (or 2-second polling), `POST /runs/{id}/cancel`, `POST /workflows/{id}/run` (Run again).
- **Missing from the API:** graph snapshot and positions for the read-only canvas, run number, next retry time (see gaps).

**Links to:** `/runs/:runId/logs`, `/runs/:runId/outputs`, `/runs/:runId/approve/:nodeId`, `/workflows/:workflowId`.

### P-07 · Approval Review
- **Route:** `/runs/:runId/approve/:nodeId` · **Access:** User (owner) · **Spec:** DS S-06 · **Requirements:** UC-04, UC-05 · **Test:** AT-09
- **Purpose:** show exactly what will be published, and record the decision.

**Main sections**
- **Header:** Gate symbol, "Review before publishing", "{Agent} is waiting for your approval. Nothing has been uploaded yet."
- **Preview tabs,** only for outputs that exist:
  - Article: rendered markdown, "✦ Generated" badge, sources list.
  - Video: native player with poster image and a narration script disclosure.
  - PDF/DOCX: embedded viewer or file card.
  - Images: grid.
- **Destination panel:** platform, account, visibility, title, description, tags; for email, recipients and subject; then the steps that follow and whether they also need approval; "waiting since".
- **Decision bar** (sticky): note field, Reject… button, and "Approve and publish to {platform}".
- **Audit footer** after a decision: "Approved by X at Y · note".

**Data shown:** upstream outputs (article, video, PDF, images); the parked node's configuration; approval record once decided.

**Actions**
- Approve.
- Reject: opens a dialog where the note is **required**.
- Switch preview tabs; play the video; open sources.

**Forms:** decision note (optional to approve, required to reject); reject dialog.
**Tables / filters:** none.

**States**
- Loading: skeleton preview.
- Empty: "Nothing to review" with "Back to run" (DS §18.2).
- Errors: approve returns 409 (already decided or not waiting); preview failed to load.
- Success: toast "Approved. Publisher is uploading now." and return to the run. Reject shows the "Rejected by you" banner.
- Already decided: read-only view with the decision banner.

**API**
- `GET /runs/{id}`, `GET /outputs/{id}`, `POST /runs/{id}/nodes/{nodeId}/approve`.
- **Missing:** a way to list a run's outputs with their content, the node's configuration and destination, and the approval record (see gaps).

**Links to:** `/runs/:runId`, `/runs/:runId/outputs`.

### P-08 · Logs
- **Route:** `/runs/:runId/logs` · **Access:** User (owner) · **Spec:** DS S-07
- **Requirements:** FR-06, UC-06 · **Tests:** AT-06, AT-10, RB-01, RB-02, RB-03
- **Purpose:** show exactly what happened in a run (every step, attempt, duration and error) and export it.

**Main sections**
- Run header and tabs.
- Filter bar: text, status, agent, times Local/UTC.
- Log table.
- Footer note about the export format.

**Data shown**
- Per step: number, agent, status, started, completed (hidden on narrower screens), duration, retries, first line of the error.
- Expanded row:
  - Attempt timeline.
  - Plain-language explanation with a fix action.
  - Output JSON and input summary (collapsible).
  - Copyable ids.

**Actions:** expand or collapse rows, filter (reflected in the URL), toggle Local/UTC, Export CSV, copy ids, run the fix action (for example Reconnect Google, which goes to Connections).
**Forms:** filter inputs.
**Tables:** the log table (sortable, sticky header, expandable). On mobile it becomes a list of cards.
**Filters / search:** text search (agent name, error text), status multi-select, agent multi-select.

**States**
- Loading: 5 skeleton rows.
- Empty: "Nothing logged yet — Logs appear as soon as the first step starts."
- Error: inline alert with Retry.
- Live: rows update in place; a "New rows ↓" pill appears if the user has scrolled.
- Success: the CSV downloads (no toast).

**API**
- `GET /runs/{id}/logs`.
- CSV: the columns are specified (`run_id, node_id, agent_type, status, started_at, completed_at, duration_ms, retry_count, error_message`, ISO 8601 UTC). Whether it is built in the browser or by the server **needs clarification**.
- Per-attempt timestamps and per-node output JSON: **no API** (see gaps).

**Links to:** `/runs/:runId`, `/runs/:runId/outputs`, `/settings/connections`.

### P-09 · Outputs (Files)
- **Route:** `/runs/:runId/outputs` · **Access:** User (owner) · **Spec:** DS S-08 · **Requirements:** FR-03, FR-04, FR-05 · **Tests:** AT-03, AT-04, AT-05
- **Purpose:** get everything a run produced: download files and open published links.

**Main sections**
- Run header with "Run again".
- Tabs.
- **PUBLISHED:** YouTube, Drive and Email cards.
- **FILES:** MP4, images, PDF and DOCX cards, grouped by step.
- **ARTICLE (text):** collapsible, with "Copy markdown".

**Data shown**
- Published: platform, visibility, title, link, message id and time for email.
- Files: name, type, size, duration or dimensions or page count, "✦ Generated" badge, video preview.

**Actions:** Download (signed URL), Copy link, Open link in a new tab, play video inline, copy markdown, Run again.
**Forms / tables / filters:** none.

**States**
- Loading: skeleton cards.
- Empty:
  - Run still going: "Files will appear here — each file shows up as soon as its step finishes."
  - Failed before any files: "No files were created" with View logs.
  - Finished: "ready" art.
- Error: per file, "Couldn't prepare this download. [Try again]".
- Success: the browser downloads the file.

**API**
- `GET /outputs/{id}` (signed URL), `GET /runs/{id}`.
- **Missing:** an endpoint to list a run's outputs with their ids (see gaps).

**Links to:** `/runs/:runId`, `/runs/:runId/logs`, external published URLs.

### P-10 · Connections
- **Route:** `/settings/connections` · **Access:** User · **Spec:** DS S-09 · **Requirement:** FR-05 · GP-plan W6
- **Purpose:** manage the Google account(s) used to publish and send email.

**Main sections**
- Page header: "Connections", security note, "Connect Google" button.
- One row per connection.

**Data shown**
- Account email, provider logo.
- Granted scopes in plain words (YouTube · Drive · Gmail).
- Status: connected, expiring, or expired.
- Expiry time; number of workflows using it.

**Actions**
- Connect Google: a scope-explanation dialog, then the OAuth popup.
- Reconnect.
- Disconnect, with a confirm dialog.

**Forms:** scope-explanation dialog and disconnect confirmation.
**Tables:** connection rows (a table or list).
**Filters:** none.

**States**
- Loading: skeleton rows.
- Empty: "No connections yet — Connect a Google account…" with Connect Google.
- Errors: "Google wasn't connected. You can try again." (popup denied or closed).
- Success: toast "Google connected."

**API:** **not defined in §5.3.** Needs list, connect or OAuth callback, and disconnect endpoints (D-09). The Google OAuth flow is Mohammed's W6 task.
**Links to:** the workflows or canvas that use the connection (**needs clarification**: DS shows "Used by N workflows" but no link target).

### P-11 · Not Found
- **Route:** `*` (plus the not-found state inside other pages) · **Access:** Everyone · **Spec:** DS §18.3, §07 (P-06 art)
- **Purpose:** handle unknown routes and resources that don't exist or aren't yours. It always says "not found", never "forbidden", so other users' items aren't revealed.
- **Main sections:** contour art, message, back link.
- **Data shown:** "This workflow doesn't exist or isn't yours." or a generic not-found message.
- **Actions:** Back to workflows (or Sign in if signed out).
- **Forms / tables / filters:** none.
- **States:** static page.
- **API:** none.
- **Links to:** `/workflows` or `/login`.

### P-12 · Design System Kitchen Sink (internal, development builds only)
- **Route:** `/dev/design` · **Access:** Development environment only, never in production · **Spec:** DS §25
- **Purpose:** show every component in every state and both themes, plus every node status. Used for visual QA, Playwright screenshot comparisons and a report figure.
- **Main sections:** component groups (Foundations, Core §14, Canvas §15, Status §16, Forms §17, Feedback §18).
- **Data shown:** static example data.
- **Actions:** theme toggle.
- **Forms / tables:** examples only.
- **States:** shows every component's loading, empty, error and success states.
- **API:** none.
- **Links to:** none.

---

### Screens that live inside pages (no route of their own)
| Element | Host page(s) | Spec |
|---|---|---|
| Config drawer (S-04) | P-04 (also run mode) | DS §17, §21 |
| Validation panel | P-04 | DS §15.5 |
| Run mode overlay | P-04 | DS §15.10 |
| Confirm dialogs: delete workflow, cancel run, reject, disconnect, leave with unsaved changes | P-03, P-04, P-06, P-07, P-10 | DS §18.4 |
| "You've been signed out" dialog | All signed-in pages | DS §18.3 |
| Keyboard shortcuts dialog (`?`) | All signed-in pages | DS §13 |
| Offline banner | All signed-in pages | DS §18.3 |

---

## 4. Page Categories

The docs point to a structure organised around the **workflow and the run**, not around dashboards or admin areas:

| Category | Pages | Notes |
|---|---|---|
| **A. Authentication (public)** | P-01 Sign in, P-02 Create account | Forgot password: needs clarification |
| **B. Workflow workspace** | P-03 Workflows, P-04 Canvas (+ config drawer) | P-03 is the home page. There is **no separate dashboard** in the docs. |
| **C. Runs: execution and review** | P-05 Run history, P-06 Run monitor, P-07 Approval, P-08 Logs, P-09 Outputs | P-06 to P-09 share a run header and tab bar |
| **D. Settings** | P-10 Connections | The only settings page. Theme sits in the user menu. |
| **E. System** | P-11 Not found | Shared |
| **F. Internal (development only)** | P-12 Design system | Not shipped in production |
| **Not applicable** | Admin dashboard, management pages, profile page, reports | Roles and admin are out of scope (M1 §3.2). No profile page is specified. Reporting happens in Notion and the M3 report; the only report-like feature is the CSV log export. |

---

## 5. Navigation Structure

The design system says **no global sidebar** (DS §19): there is one main object (the workflow) and one secondary object (the run).

**Top bar** (every signed-in page, 56 px)
- Logo (links to `/workflows`) · breadcrumb · page-specific actions · help `?` · user avatar.
- On the canvas it adds: save status, Validate, Run ▾ (Validate only · Run with mock agents *(development only)* · Run history).
- On mobile: logo mark + "←" + avatar. On the canvas, a sticky bottom Run/Cancel bar.

**User menu** (avatar)
- Email (greyed out, not clickable) · Connections · Keyboard shortcuts · Theme: Light / Dark / System · Sign out.
- No roles, teams or sharing items.

**Run sub-navigation** (tab bar under the run header on P-06 to P-09)
- Overview · Logs · Files (with count) · Approval (violet badge, only while something is waiting).

**Left side panel**
- Only on the canvas: the **agent palette**. It's a tool panel, not navigation.

**Breadcrumbs**
| Page | Breadcrumb |
|---|---|
| P-03 | Workflows |
| P-04 | Workflows / {name ✎} |
| P-05 | Workflows / {name} / Runs |
| P-06 | Workflows / {name} / Run #n |
| P-07 | Workflows / {name} / Run #n / Approval |
| P-08 | Workflows / {name} / Run #n / Logs |
| P-09 | Workflows / {name} / Run #n / Files |
| P-10 | Connections (**needs clarification**: DS doesn't give its breadcrumb) |

On narrow screens the breadcrumb collapses to "← Workflows".

**Visibility by role**
| Element | Visitor | User | Development environment extra |
|---|---|---|---|
| P-01, P-02 | ✅ | Redirect **needs clarification** | — |
| Top bar, user menu | — | ✅ | "Mock agents" badge |
| P-03 to P-10 | Redirect to `/login?next=` | ✅ (own data only) | "Run with mock agents" menu item |
| P-11 | ✅ | ✅ | — |
| P-12 | — | — | ✅ |

---

## 6. User Flows

Based on DS §20, the GP-plan use cases (§8.1) and test cases (§8.3).

**F-01 · First run** (new user)
Create account → Workflows (empty state) → choose **Use a template** *or* **New workflow**
→ Canvas (template chain, or drag Researcher and Writer and connect them) → click Researcher → set topic
→ Run → invalid? Validation panel → Go to node → fix → Run
→ run mode, steps light up → toast "Run finished" → **View files** → Outputs → download the article

**F-02 · Create and configure a workflow** (UC-01, UC-03, AT-01, AT-08)
Workflows → New workflow → Canvas "Untitled workflow" → rename inline
→ drag agents → connect handles (an incompatible target dims with a tooltip)
→ select a node → drawer opens → fill the form (autosaves) → repeat for each node
→ Validate → issues? fix through the panel → "✓ Ready to run"

**F-03 · Execute and monitor** (UC-02, NFR-01, AT-07, AT-11)
Canvas → Run → validate → run returns 202 → "Queued"
→ live updates (Realtime or 2-second polling) → Researcher running then done → edge flows → Writer running…
→ the user can navigate anywhere meanwhile → a distribution step parks → violet node, announcement, toast "Review"

**F-04 · Review and publish** (UC-04, UC-05, AT-05, AT-09)
Approval needed (toast, banner or badge) → Approval page → preview article, video or PDF → check the destination
→ **Approve** → toast → back to the run → Publisher running then done → Outputs shows the YouTube link
→ *or* **Reject…** → dialog (note required) → run failed "Rejected by you" → later steps skipped

**F-05 · Failure and recovery** (FR-06, UC-06, AT-06, AT-10)
Node running → fails → "Retrying 1/3" countdown → … → "Retrying 3/3" → Failed with an error chip → later steps skipped
→ run banner: what failed, why, and an action → **View logs** (row expanded with every attempt) *or* the fix action (Reconnect Google → Connections)
→ back to the canvas → Run again

**F-06 · Connect a Google account** (FR-05, W6)
Publisher drawer → "Connect Google" (or Connections page) → scope-explanation dialog → OAuth popup
→ granted: popup closes, toast "Google connected", the picker selects it
→ denied or closed: inline message "Google wasn't connected. You can try again."

**F-07 · Cancel a run** (UC-02, W9)
Run monitor (or canvas run mode) → Cancel run → confirm dialog → run "Cancelled" → steps that hadn't started become skipped → neutral banner "You cancelled this run at…"

**F-08 · Review past runs and export logs** (UC-06)
Workflows → open a workflow → Run ▾ → Run history → pick a run → Logs tab → filter → Export CSV

**F-09 · Session expired** (DS §18.3)
Any action returns 401 → dialog "You've been signed out" → Sign in again → back to the same URL, with the unsaved graph restored

**F-10 · A developer adds a seventh agent** (NFR-04, AT-12; the user only sees the effect)
Agent folder added and worker restarted → catalog lists the new agent → it appears in the palette (Create group, fallback icon) → drag it onto the canvas → the drawer builds its form from its schema → run, status, logs and outputs all work, **with no frontend change**

---

## 7. Page Dependencies

| Page or feature | Depends on | Why |
|---|---|---|
| **Everything** | Foundation: design tokens, generated API types, API client, auth token storage, route guard, data-fetching setup, app shell | Shared by every page |
| P-03 to P-10 | P-01 (and P-02) plus the route guard | Protected routes |
| P-01, P-02 final version | **D-01** (Supabase or in-house auth) | Dev sign-in until then |
| P-03 Workflows | P-01; workflow endpoints | Home after sign-in |
| P-03 templates row | **Template source decision** | Seed data exists only for the demo user |
| P-04 Canvas | P-03 (entry point); `GET /agents/catalog` (**a worker must be running**) | Palette and forms come from the catalog |
| Config drawer form | P-04; **D-04** (`x-*` schema hints) | Picking the right field types |
| Credential picker | P-10 Connections + credentials API (**D-09**) + OAuth backend (W6) | Publisher and Email need an account |
| Validation panel | `/validate` messages (backend owns the wording, DS §23.3) | The frontend doesn't invent rules |
| P-06 Run monitor | P-04 (Run creates a run); Realtime/polling decision; run status values (**D-07**) | Nothing to show without a run |
| Canvas run mode | P-06 data (same run state); status visuals (DS §16) | Same run state |
| P-05 Run history | P-04 runs exist; `GET /workflows/{id}/runs` | — |
| P-08 Logs | P-06 (run context and tabs); logs endpoint | Shares the run header and tabs |
| P-09 Outputs | P-06; **outputs list endpoint (missing)**; signed-URL downloads (W4) | Needs output ids |
| P-07 Approval | P-06 (how users arrive); P-09 preview pieces (article, video, PDF viewers); approval gate backend (W7); **outputs and node config API (missing)** | Previews the content that will be published |
| Error chips, retry strip | P-06 and P-04 node components; retry fields in the run state | W9 |
| P-10 Connections | P-01; OAuth flow (Mohammed, W6); credentials API | — |
| P-11 Not found | Nothing | Build early |
| P-12 `/dev/design` | The reusable components themselves | Grows with each component |

---

## 8. Reusable Frontend Components

Identified only — none of these are created by this plan.

| Component | Used on |
|---|---|
| **App shell / Top bar** | P-03 to P-10 |
| **Breadcrumb** (with inline rename on the canvas) | P-04 to P-10 |
| **User menu / Avatar** (Connections, Shortcuts, Theme, Sign out) | Every signed-in page |
| **Route guard** (redirect to `/login?next=`) | P-03 to P-10 |
| **Button** (Primary, Accent-Run, Secondary, Ghost, Danger, Danger-secondary, Link) and **Run split button** | All pages; Run split on P-04, "Run again" on P-06 and P-09 |
| **Icon button** | Toolbars, table rows, palette, canvas controls |
| **Form fields**: text, textarea, number or slider, password, search, select, segmented, combobox, radio cards, switch, checkbox, tag input | P-01, P-02 (auth); P-04 (drawer); P-03, P-08, palette (search); P-07 (note) |
| **Schema form** (JSON Schema to fields) | P-04 drawer (every agent) |
| **Credential picker** | P-04 drawer (Publisher, Email) |
| **Upstream binding chip** | P-04 drawer |
| **Status chip** + **status map** | P-03 (last run), P-04 nodes, P-06, P-05, P-07, P-08, browser tab title, toasts |
| **Badges**: count, "✦ Generated", "Requires approval", "Mock", "Dev" | P-04, P-07, P-09, run tabs, status bar |
| **Cards**: workflow card, template card, file card, published-link card | P-03; P-09; P-07 (file previews) |
| **Tabs** | P-06 to P-09 (run tabs), P-07 (preview tabs), P-04 drawer |
| **Dropdown / context menu** | P-03 card menu, P-04 node menu, Run ▾, user menu |
| **Tooltip** | Icon buttons, disabled-button reasons, truncated names, palette |
| **Dialog / Confirm dialog** | Delete workflow (P-03), cancel run (P-04, P-06), reject (P-07), disconnect (P-10), OAuth scopes (P-10), session expired (global), shortcuts (global) |
| **Drawer / Bottom sheet** | P-04 config drawer; mobile sheets |
| **Toast** (info, success, warning, error, undo) | Global: run finished, approved, node deleted (undo), save errors, Google connected |
| **Inline banner** (info, warning, error, approval, neutral) | P-04 run mode, P-06, P-07, P-08 fix hints, mock mode, offline, mobile read-only notice |
| **Data table** (sortable, expandable, sticky header, mobile cards) | P-08 Logs, P-03 table view, P-05 Run history, P-10 |
| **Filter bar** (text + multi-select + URL sync) | P-08; search and sort on P-03 |
| **Pagination** | **Not specified in the docs**; P-05 is limited to 50 runs (needs clarification) |
| **Progress**: linear bar, spinner, elapsed timer, long-task card, retry countdown ring | P-04 run mode, P-06 header and steps, node footers |
| **Skeleton** | Every data page |
| **Empty state** (with P-06 contour art) | P-03, P-04, P-05, P-08, P-09, P-10, P-07, P-11 |
| **Full-page error / not-found state** | P-04 to P-09 (missing or foreign resource), P-11 |
| **JSON viewer** | P-08 expanded rows |
| **Kbd** + **Shortcuts dialog** | Global, P-04 menus |
| **Canvas set**: agent palette, agent node, edge, handles, validation panel, status bar, controls, minimap, run header, steps list, error chip, retry strip | P-04, P-06 (read-only canvas and steps list) |
| **Media previews**: markdown article preview, video player, PDF viewer, image grid | P-07, P-09 |
| **Live announcer** (aria-live, polite and assertive) | P-04 run mode, P-06, P-08 |
| **Theme switch** | User menu |
| **Logo** (mark, lockup) | Top bar, P-01, P-02, P-11 |

---

## 9. Frontend Development Order

These phases follow the weekly plan in GP-plan Part 4, so the frontend is ready when the backend feature lands.

**Phase 1 – Foundation (W1)**
- Design tokens and Tailwind preset in their final form; fonts (D-06).
- Generated API types and API client; data-fetching setup; auth token storage; route guard.
- App shell: top bar, user menu, breadcrumb.
- Core components: Button, fields, Status chip, Toast, Dialog, Skeleton, Empty state, Banner.
- **Pages:** P-11 Not found; P-12 `/dev/design` (starts here and grows).

**Phase 2 – Authentication (W1–W2)**
- **Pages:** P-01 Sign in, P-02 Create account.
- Dev sign-in until D-01, then real auth; the session-expired dialog.

**Phase 3 – Core workflow pages (W2–W3)**
- **P-03 Workflows:** cards, create, rename, delete, search and sort. Templates wait on that decision.
- **P-04 Canvas:**
  - Palette from the catalog, custom agent node, edges, autosave.
  - Validate plus validation panel, Run button, status bar.
  - **Config drawer** with the schema form (needs D-04).
- AT-01, AT-02, AT-08 should pass at the end of this phase.

**Phase 4 – Execution and outputs (W3–W5)**
- **P-06 Run monitor:**
  - Header, steps list, read-only canvas, live updates.
  - Cancel is in W9 in the plan, but the UI hook can be added now.
- **Canvas run mode** (overlay on P-04).
- **P-09 Outputs** (W4: downloads; W5: video preview and long-task progress).
- **P-05 Run history** (needs its specification first).
- Loading, empty and error states for every page built so far (a W4 requirement).
- AT-03, AT-04, AT-07 should pass at the end of this phase.

**Phase 5 – Integrations and human-in-the-loop (W6–W7)**
- **P-10 Connections** and the **credential picker** in the drawer (W6).
- Published-link cards on P-09 (W6).
- **P-07 Approval** on desktop and mobile, reject dialog, approval banner and tab badge (W7).
- W8 full-pipeline polish; retake the headline canvas screenshot; **feature freeze**.
- AT-05, AT-09, AT-12 should pass at the end of this phase.

**Phase 6 – Hardening, integration and polishing (W9–W11)**
- W9: **P-08 Logs** (table, filters, expanded attempts, CSV export); error chips and retry strips on nodes and steps.
- W9: accessibility passes (keyboard, screen reader, colour-blindness, reduced motion); Lighthouse score ≥ 95.
- Responsive behaviour (DS §22).
- Dark theme decision (D-05).
- W10: visual regression on P-12; Playwright tests for the 3 template workflows.
- W11: usability sessions; fix only critical findings; screenshot sweep for the report.
- AT-06, AT-10, AT-11, US-01 should pass at the end of this phase.

---

## 10. Final Page Count

| Count | Number | Pages |
|---|---|---|
| **Total routed pages** | **12** | 11 product pages + 1 development-only page |
| Public (unauthenticated) | **2** | P-01 Sign in, P-02 Create account |
| Authenticated (User) | **8** | P-03 Workflows, P-04 Canvas, P-05 Run history, P-06 Run monitor, P-07 Approval, P-08 Logs, P-09 Outputs, P-10 Connections |
| Admin / management | **0** | Out of scope (M1 §3.2) |
| Shared (any visitor) | **1** | P-11 Not found |
| Internal, development only | **1** | P-12 Design system |
| In-page screens (not counted) | 7 | Config drawer, validation panel, run mode overlay, confirm dialogs, session-expired dialog, shortcuts dialog, offline banner |

---

## Documentation Gaps / Questions

### Ownership and roles
1. **Frontend owner.** GP-plan assigns C1 `frontend` to **Ahmed**, and Hasan to **C2 api + C3 worker**. Hasan has since described the frontend as his responsibility. Confirm whether ownership changed, and update GP-plan, `CODEOWNERS` and CONTRIBUTING.
2. **Admin or supervisor access.** The docs rule out roles. Confirm the supervisor and committee only need a demo account.

### Authentication
3. **D-01 is still pending.** Supabase Auth or in-house login decides how P-01 and P-02 work. The current API only has `dev-login`.
4. **Forgot password.** The S-01 wireframe shows a "Forgot?" link, but no page or flow is specified.
5. **Signed-in user opening `/login`:** redirect to `/workflows`? Not specified.
6. **Registration errors.** Wording for "email already registered" isn't specified.
7. **Where to store the session token** (localStorage now, or Supabase client) isn't specified.

### Pages without full specifications
8. **P-05 Run history** only appears in the page map (DS §19). There's no layout, filters or pagination.
9. **Canvas run mode or run monitor?** DS §15.10 keeps the user on the canvas after Run; S-05 is a separate page. Which is the main experience after pressing Run?
10. **Connections breadcrumb and links.** "Used by N workflows": link to what?
11. **No profile or account page.** Is one needed (for example to change password or delete the account)? The docs don't mention one.
12. **Public landing page.** A separate landing page was made outside `docs/`. The app docs don't include a public home page. Confirm it stays a separate static site.

### API gaps the pages need (GP-plan §5.3 / D-09)
13. **No endpoint to list a run's outputs** (ids, type, content, file path, URL). Blocks P-09, the approval previews on P-07, and the drawer's "Last output" tab.
14. **The run state doesn't include the graph snapshot** (node positions, configuration). Blocks the read-only canvas on P-06 and the destination panel on P-07.
15. **Approval records can't be read.** Blocks the "Approved by X at Y · note" footer and the "Rejected by you: note" banner.
16. **Credentials endpoints** (list, connect/OAuth callback, disconnect, expiry) aren't defined. Blocks P-10 and the credential picker.
17. **No duplicate-workflow endpoint.** Is Duplicate done by the frontend (copy the graph with new node ids) or the API?
18. **No run number.** The UI shows "Run #14", but runs only have UUIDs.
19. **No next-retry time or per-attempt timestamps.** The API only stores the combined error text, which blocks the retry countdown and the attempt timeline on P-08.
20. **Errors have no codes.** DS §23.5 maps error codes (for example `invalid_grant`, `quotaExceeded`) to plain-language messages, but the API only returns error text.
21. **CSV export:** built in the browser or by the server?
22. **Realtime or polling?** GP-plan allows either. It also conflicts with the rule that "the frontend knows only the HTTP contract" (Supabase Realtime is a second channel).

### Features and requirements
23. **Five or six agents (D-03).** FR-02 lists five agents; the design system and code have six (including Image). The palette design assumes six.
24. **Templates.** P-03 shows a templates row, but templates are only seeded as the demo user's workflows. Where do templates come from for new users?
25. **PDF/DOCX export.** Export is "a service, not a node". The UI has no action to request a PDF or DOCX, yet P-09 lists them and a template is named "Research → PDF → Email". How does a user get a PDF?
26. **Approval notifications.** Beyond in-app toasts, badges and the tab title, is there an email or other notification when a run waits (D-09)? The deep link to P-07 assumes one may exist.
27. **Approval locked on (D-08).** Confirm Publisher and Email approval can't be switched off in the UI.
28. **Schema field hints (D-04).** The `x-widget`, `x-order` and `x-group` hints are only partly present (a credential hint exists on Publisher). The drawer's field choices depend on them.
29. **Run status values (D-07)** are only defined in the code and design system. GP-plan §5.2 doesn't list them.
30. **Minor features marked "proposed" in DS:** "Tidy up" automatic layout, edge data labels, compatible-connection highlighting (needs input and output types in the catalog). Confirm they're in scope before the W8 feature freeze.

### Design and non-functional
31. **Dark theme (D-05):** ship in M3 or later?
32. **Mobile:** canvas read-only below 1024 px (D-10). Confirm with the supervisor, given the mobile app is out of scope but W11 says "works from a phone on mobile data".
33. **Product name (D-02):** "Isnad" in the design system and GitHub repo, "GP Platform" in the current frontend title.
34. **Usability study:** participant count isn't set (GP-plan "Still Unknown" #5). It affects how much polish Phase 6 needs.
35. **Pagination and limits:** not specified for Workflows, Run history or Logs.
