# Isnad — User Experience Specification

## How someone actually uses the platform: build → run → approve

**Status:** for review · 16 Sep 2026 · covers P-03, P-04, S-04, the run experience and S-06
**Companion to:** [DESIGN-SYSTEM.md](DESIGN-SYSTEM.md) (what things look like) and [FRONTEND-PAGES-PLAN.md](FRONTEND-PAGES-PLAN.md) (what gets built when)

---

## Why this document exists

DESIGN-SYSTEM.md says what every component looks like. FRONTEND-PAGES-PLAN.md says which page gets built in which week. Neither says **what a person is trying to do, or how the product teaches them to do it.**

That gap showed up in the code. The canvas was built first — drag, connect, save, undo all work — and it is still not a product, because a node is a box with a label. Nothing tells a user what Researcher does, what it needs from them, or what it hands to the next step.

This document fills that gap for the part of the product that matters most: the loop from building a chain, to running it, to approving what goes out. It is the reference for the configuration drawer, the canvas teaching affordances, run mode and the approval screen.

It does not restate the design system. Where a visual is already specified, it cites the section and moves on.

---

## 1. Who this is for

From NFR-03 and DESIGN-SYSTEM §01: **non-technical content creators** — a person running a student club newsletter, a lecturer making explainer videos, a small marketing team. They can describe the pipeline in one sentence. They cannot write the code to automate it.

The honest measure is **US-01**: a person we have never met completes *"produce a blog post about a topic of your choice and email it to yourself"* with no instructions and no help from us.

Everything below is in service of that sentence.

---

## 2. The one idea the product is built on

### Each step inherits from the ones before it. What you type overrides that.

The orchestrator merges **every upstream step's output**, then lays **the step's own settings on top** (`worker/src/worker/orchestrator.py`):

```python
for earlier in order[:index]:
    if earlier.id in upstream_of[node.id]:
        data.update(outputs.get(earlier.id, {}))
data.update(node.configuration)   # what the user typed wins
```

So in the drawer:

> **An empty field means "use what the previous step produced."**
> **A filled field means "no — use this instead."**

That one rule explains nearly everything a new user finds strange:

| What they notice | Why |
|---|---|
| Publisher's **Title** can be left blank | It inherits the article's title from Writer |
| Email's **Subject** and **Body** are optional | Same — they inherit from Writer |
| The seeded templates leave most fields empty | Empty *is* the answer, not an oversight |
| Writer without a Researcher before it fails when run | Nothing upstream produced the `notes` it requires |

**Nothing in the interface says this today.** So an optional field looks like a blank you forgot to fill, and a user either fills everything — fighting the system — or fills nothing and never understands why it worked.

**Rule 1: every field states where its value comes from.** An inheriting field shows its source. Typing takes control. Clearing gives control back.

This is also what makes the product's own promise — *"shows every handoff as it happens"* — true while you are still building, not only while you watch.

---

## 3. The three moments

The core loop is three different jobs. Treating them as one screen is the mistake to avoid.

| Moment | What the user is asking | What the screen must do |
|---|---|---|
| **Build** | "What can these things do, and what do I have to tell them?" | Teach, and prevent mistakes |
| **Run** | "Is it working? Is it stuck?" | Reassure. Never look hung. |
| **Approve** | "What exactly is about to go out under my name?" | Show the real thing. Make the consequence unmissable. |

---

## 4. Moment one — Build

### 4.1 Arriving with nothing

A new account has no workflows. The empty state (§18.2) offers two doors: **Use a template** or **New workflow**.

Templates are the only onboarding this product has. There is no tour, no coach marks, no checklist — and that is the right call, because a template is a working example the user can take apart. Picking one copies it into their own workflows and opens it, already configured, already runnable.

> **Open gap.** Templates exist only as the demo user's seeded workflows. Nothing in the API marks a workflow as a template, so a new user sees no templates at all. See §9, gap 4.

### 4.2 The canvas teaches through its nodes

A node is the primary teaching surface.

```
        ●
┌──────────────────────────────────────────┐
│ ┌────┐  Writer                      ⋯    │
│ │ ✎  │  WRITER · STEP 2                  │
│ └────┘                                    │
│ ──────────────────────────────────────── │
│ Medium · Informative · Blog post          │
│ ──────────────────────────────────────── │
│ [⟳ Running]   0:42                  ‖    │
└──────────────────────────────────────────┘
                                          ●
```

| Part | What it teaches |
|---|---|
| **Step number** | `STEP 2` is the step's position in the chain, so it only appears once connected. Connecting is what numbers it — which teaches that order matters, without saying so. |
| **Settings summary** | What this step is set to do, in the user's words. |
| **Missing marker** | `Missing: topic` in red, so an unconfigured step is never silently empty. |
| **Gate mark `‖`** | This step waits for a person before it does anything outside the platform. |

**The settings summary must read as labels, not raw values.** What it renders today, against the real seeded configs:

| Node | Renders today | Must read |
|---|---|---|
| Researcher | `The future of solar energy in Saudi Arabia · 5` | `5 sources` |
| Publisher | `youtube · unlisted · Solar energy…` | `YouTube · Unlisted` |
| Email | `Weekly digest · Here's the latest:` | `1 recipient · Weekly digest` |

Three faults: raw enum values (`youtube` instead of `YouTube`), a naked `5` whose meaning is lost without its unit, and the message **body** spilling onto the canvas. It also skips arrays entirely, so the Email node never shows who it is addressed to — the one thing that matters on that node.

The labels and units are already in each agent's schema (`title`, `x-unit`). The summary is built from the schema, never from the values alone.

### 4.3 The edges show the handover

Hovering a connection names what actually crosses it:

```
Researcher  ──  notes · sources  ──▶  Writer
```

This is the cheapest possible expression of *"see every handoff"*, and it is the answer to "what does this arrow mean?" — a question every first-time user asks.

### 4.4 The canvas guides; the server decides

A user can wire **Email → Writer** backwards today. Validate passes. The run then dies mid-way with *"Writer is missing input: notes"* — after they have waited.

The validator checks loops, orphans and missing settings (`api/src/api/services/validation.py`). It never checks whether one step can actually feed the next.

The canvas therefore surfaces the mismatch **before** the connection is made — but it never hard-blocks, and it never hard-codes which agent may follow which, because AT-12 requires a brand-new agent to work with zero frontend changes.

| Moment | What the user sees |
|---|---|
| Dragging a connection | Each possible target says what it needs — "Writer needs notes" |
| After connecting something that cannot work | The node says so on its face, with the fix |
| On Validate | The server's message, word for word, with **Go to node** |

**The server's wording is never paraphrased.** `/validate` owns the words (§15.5). If a message is bad, we fix it in the API, not in the frontend.

### 4.5 The drawer — how you give a step its orders

This is the screen the whole product depends on, and the one the user asked about most directly: *how do I tell each agent what to do?*

Right-hand drawer, 400px, resizable 360–560 (§14.13). It **builds itself from the agent's JSON Schema** — there is no per-agent React code anywhere, because the moment there is, AT-12 fails and a seventh agent needs a developer.

```
┌──────────────────────────────────────┐
│ ┌──┐ Writer                       ✕  │
│ └──┘ WRITER · STEP 2                 │
├──────────────────────────────────────┤
│ [ Settings ]  [ Last output ]        │
├──────────────────────────────────────┤
│ Fields marked * are required         │
│                                      │
│ Notes                                │
│ ○──● From Researcher · notes          │
│ Filled automatically when Researcher │
│ finishes.                            │
│                                      │
│ Length *                             │
│ [ Short | Medium | Long ]  Default   │
│                                      │
│ Style *                              │
│ [ Informative            ▾ ]         │
│                                      │
│ ▸ Advanced                           │
├──────────────────────────────────────┤
│ Require approval            ( ○ )    │
│ Saved · just now                     │
└──────────────────────────────────────┘
```

Four rules that are new in this document:

1. **Inheriting fields show their source.** Not an empty box — a chip reading *"From Writer · title"* with the help text *"Leave empty to use it."* If nothing upstream can supply it, the chip turns red: *"Needs a Writer before this step"* with **Go to canvas**.
2. **Defaults read as defaults.** Writer opens pre-filled with Medium / Informative / Blog post and a quiet `Default` hint until the user changes something. The message is "this is already sensible", not "this has already been answered".
3. **There is no Save button.** Every change autosaves into the workflow's existing 800 ms debounce, and the footer says so. A Save button implies work can be lost.
4. **Secrets are never text fields.** The Google account is a picker holding a reference, never a pasted token — and no secret ever appears in the form, the graph or the URL.

#### The rule that makes inheriting actually work

**The form must never write a default into a step's settings.** This sounds like an implementation detail. It is not — it is the difference between the product working and not.

Image's "what should the image show?" has a default of *nothing*, meaning *inherit the article title*. If simply opening the drawer wrote that empty default into the saved settings, the orchestrator's last line — `data.update(node.configuration)` — would lay that emptiness over Writer's title, and `ImageInput` rejects an empty prompt. Every Writer → Image chain would break, **caused by nothing but opening the drawer to look**.

So: settings hold only what the user has actually chosen. A field the user clears is *removed*, not stored as empty. That is what makes "leave it empty to inherit" true rather than a figure of speech, and it is why the saved graph for the seeded templates is as short as it is.

The same rule keeps client and server agreeing on the word "missing": `/validate` treats `null`, `""` and `[]` as missing, and so does the form.

**Validation timing** (§17.2), which is deliberately three-tier:

| When | What is checked |
|---|---|
| On blur | Format — "that is not an email address" |
| On Validate or Run | Completeness — "Researcher is missing topic" |
| Server | The authority. Its messages attach to the field. |

---

## 5. The six agents, in plain language

This is the reference for *"how do I give orders to each agent"*. Field names are the real ones from `contracts/src/contracts/agent_io.py`; the descriptions are what the user should understand.

### Researcher — *finds sources on a topic and gathers notes*

| Field | Control | What it means | Default |
|---|---|---|---|
| **Topic** * | Textarea | The only thing in the whole product a user must type to run anything. 3–300 characters. | — |
| **Number of sources** | Number, suffix "sources" | How many sources to gather. 1–10. | 5 |

Hands on: `notes`, `sources`. If it finds nothing it stops with *"Try a broader topic."*

### Writer — *turns research notes into an article*

| Field | Control | What it means | Default |
|---|---|---|---|
| **Notes** | Inherit chip | From Researcher. Required — Writer cannot run without it. | inherited |
| **Length** | Segmented | Short ≈ 400 words · Medium ≈ 800 · Long ≈ 1500. The word count is real, not a vague hint. | Medium |
| **Style** | Select | Informative · Persuasive · Conversational · Academic | Informative |
| **Format** | Segmented | Blog post · Article · Video script. Pick **Video script** when a Video step follows. | Blog post |

Hands on: `title`, `summary`, `article_md` — which is why almost every later step can leave its title and subject blank.

### Image — *creates a thumbnail and images*

| Field | Control | What it means | Default |
|---|---|---|---|
| **What should the image show?** | Textarea or inherit chip | Leave empty to use the article's title. | inherited from Writer |
| **Number of images** | Number | 1–4. | 1 |
| **Shape** | Segmented | Landscape 16:9 · Square 1:1 | Landscape |

### Video — *narrates a script and assembles a playable MP4*

| Field | Control | What it means | Default |
|---|---|---|---|
| **Script** | Inherit chip | From Writer's article. Required. | inherited |
| **Narration voice** | Text | A language code such as `en` or `en-uk`. | `en` |
| **Resolution** | Segmented | 720p · 1080p | 720p |

Video is the slow step. Above ten seconds it shows *"Video is rendering — long videos can take a few minutes. You can leave this page."* A five-minute render must never look like a hang.

> **Rough edge.** Narration voice is a free text box with nothing validating it, so a typo is only discovered mid-run. It should become a Select. See §9.

### Publisher — *uploads to YouTube or Google Drive* ‖

| Field | Control | What it means | Default |
|---|---|---|---|
| **Publish to** | Segmented | YouTube · Google Drive | YouTube |
| **Google account** * | Credential picker | Never a pasted token. If none is connected, the field offers **Connect Google**. | — |
| **Title** | Text or inherit chip | Leave empty to use the article's title. Max 100 (YouTube's limit). | inherited |
| **Tags** | Tag input | YouTube only. | — |
| **Visibility** | Segmented | Unlisted · Private · Public. **Defaults to Unlisted on purpose** — an accidental public upload is the worst thing this product could do. | Unlisted |
| **Require approval** | Switch, **locked on** | Publishing always waits for a person (D-08). | On |

### Email — *sends the links and files to your recipients* ‖

| Field | Control | What it means | Default |
|---|---|---|---|
| **To** * | Tag input | At least one address. **Defaults to the signed-in user's own address**, so the first thing anyone sends goes to themselves. | you |
| **Subject** | Text or inherit chip | Leave empty to use the article's title. | inherited |
| **Message** | Textarea | Any links from a Publisher step are appended automatically. | inherited |
| **Require approval** | Switch, **locked on** | Sending always waits for a person (D-08). | On |

---

## 6. Moment two — Run

**The canvas is where you watch.** Pressing Run does not navigate away. The user built this chain; watching their own chain light up is the product's entire argument. `/runs/:runId` stays a real page for deep links, notifications and coming back later — but it is not where Run lands you.

*(This settles a contradiction between §15.10 and §21 S-05 — see FRONTEND-PAGES-PLAN gap #9. It needs a row in the Decisions Log.)*

| | |
|---|---|
| **Editing locks** | The palette collapses: *"Editing is paused while this workflow runs."* |
| **Status is everywhere** | Node, edge, minimap, browser tab title and favicon dot (§16.6) — so a user in another tab still notices when something needs them |
| **Retries are narrated** | *"Attempt 2 of 3 failed. Trying again in ~4s."* Never a frozen spinner. |
| **Slow steps explain themselves** | The long-task card, with elapsed time and permission to leave |
| **Cancel is always one click** | And it says what will happen: steps that have not started are skipped, files already made are kept |
| **A Steps list is always there** | The accessible equivalent of the graph. The whole run is usable without seeing the diagram. |

When it ends: success shows a burst and *"Run finished in 6m 12s. 4 files ready."* with **View files**. Failure shows what failed, why, and one action — *"Run stopped at Publisher. Your Google connection has expired."* with **Reconnect Google**.

---

## 7. Moment three — Approve

The headline guarantee: **nothing goes public until a person says so.**

The gate parks the step **before** it acts, so the preview is of something that genuinely has not gone anywhere. The screen says so in as many words: *"Nothing has been uploaded yet."*

| | |
|---|---|
| **Show the real thing** | The article, the video, the PDF — not a description of them |
| **Show the destination** | Platform, which Google account, visibility, title, recipients |
| **The button reads the consequence** | **Approve and publish to YouTube** — never "OK", never "Confirm" |
| **Reject needs a reason** | The note is required, and the run then reads *"Rejected by you"* — never confused with a technical failure |
| **A decision is final and visible** | Revisiting shows a read-only record of who decided what, and when |

> **Open gap.** No API lists what a run produced, so the preview has nothing to show. This blocks the single most important screen in the project. See §9, gap 1.

---

## 8. The copy that carries the experience

Voice rules from §02 that this spec depends on: say what happened then what to do; never blame the user; be specific with numbers; no exclamation marks. And the word list — the interface says **step**, **run**, **file**, **Google connection**, never *node*, *execution*, *artifact*, *credential*.

| Moment | What we say |
|---|---|
| Canvas, nothing on it | **Start your chain** · Drag Researcher from the left to begin. |
| A step is unconfigured | Missing: topic |
| Inheriting field | From Writer · title — leave empty to use it |
| Nothing upstream can supply it | Needs a Writer before this step · **Go to canvas** |
| Validation found problems | *(the server's words, verbatim)* · **Go to step** |
| Ready | ✓ Ready to run |
| Queued | Queued — starting in a moment… |
| Retrying | Attempt 2 of 3 failed. Trying again in ~4s. |
| Video is slow | Video is rendering — long videos can take a few minutes. You can leave this page. |
| Waiting for a person | Publisher is waiting for your approval. **Review** |
| On the approval screen | Nothing has been uploaded yet. |
| Approving | **Approve and publish to YouTube** |
| Rejected | Rejected by you at 16:05: "Wrong thumbnail" |
| Finished | Run finished in 6m 12s. 4 files ready. **View files** |
| Failed | Run stopped at Publisher. Your Google connection has expired. **Reconnect Google** |
| Running on fakes | Running with mock agents — nothing will be published or sent. |

---

## 9. Open gaps

Four things block finishing this experience. Two are small API changes; two are one-line schema changes.

| # | Gap | What it blocks | Owner |
|---|---|---|---|
| 1 | **Nothing lists a run's outputs.** `GET /outputs/{id}` needs an id nothing hands you. | The approval preview — the headline feature. Also the drawer's "Last output" tab and the Files screen. | **C2 — add `GET /runs/{run_id}/outputs`** |
| 2 | **Templates are not marked.** Seeds are just the demo user's workflows. | A new user gets no starting point, and templates are the only onboarding that exists. | **C2 — add `GET /workflows/templates`** |
| 3 | **`format: email` is missing** from Email's schema — validity is a Python validator the form cannot see. | Recipient chips cannot validate without hard-coding the agent's name, which breaks AT-12. | C0/C4 — add `format: email` |
| 4 | **Narration voice is an unconstrained string.** | A typo is only discovered mid-run. | C0/C4 — make it an enum |

Two smaller notes for whoever implements the renderer: optional fields come through as `anyOf [T, null]` with no top-level type, so they must be unwrapped or five fields fall back to "cannot edit this"; and `tags` has no `default` key at all, so "has a default" cannot be tested by presence.

---

## 10. How we will know it worked

| Check | Bar |
|---|---|
| **AT-08** | Researcher shows topic and sources; Writer shows length, style, format; bad values show inline errors; values survive a reload |
| **AT-12** | A brand-new seventh agent appears with a working form and **zero files changed under `frontend/`** — enforced by a test, not by inspection |
| **AT-09** | A run parks, publishes nothing, and resumes only on approval. Rejecting halts it. |
| **US-01** | Someone non-technical completes *"produce a blog post and email it to yourself"* with no help |

US-01 is the one that counts. The rest are how we avoid embarrassing ourselves before we get there.
