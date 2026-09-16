# Landing page

The public marketing page for Isnad — `landing/site/index.html`, a single self-contained
file with no build step and no framework. It is written against the same tokens as the
product (DESIGN-SYSTEM.md §04, §05, §11, §12 and §24), so the page and the app stay
recognisably the same brand.

It is **not** one of the seven components. It ships no product code, imports nothing from
the repo, and can be deployed or handed over on its own.

## The two files

| File | What it is |
|---|---|
| `index.html` | The source: page content only, no `<head>`. This is the file to edit. |
| `site/index.html` | The build: the same bytes with a real `<head>` in front. This is the file to open, deploy or put on the CD. |

`index.html` has no `<head>` because it is also published as a Claude artifact, and the
artifact runtime supplies the doctype, charset and viewport itself. Opened straight from
disk it therefore has no charset, the browser falls back to windows-1252, and every em
dash, middle dot and Arabic character renders as mojibake. That is the missing wrapper,
not a missing font — so never hand anyone `index.html` directly.

## Editing it

Edit `index.html`, then regenerate the standalone page:

```bash
make landing
```

`make landing-check` fails if `site/index.html` is out of date, the same way CI checks
that `contracts/openapi.json` matches the API. Run it before opening a pull request.

## What it depends on

Two CDN resources, both on the allowlist the artifact runtime enforces:

- Geist, Geist Mono and Instrument Serif from Google Fonts
- Lucide 0.460.0 from jsDelivr, pinned

The page renders and reads correctly without either — the font stack falls back and the
icons are decorative (`aria-hidden`), so nothing meaningful is lost offline.

## Before you publish a change

- Both themes: it follows `prefers-color-scheme` and honours an explicit `data-theme`.
- 375 px wide: no horizontal scrolling on the page itself. The timeline and the log table
  scroll inside their own containers, which is intended.
- `prefers-reduced-motion`: the run animation stops.
- Headings still descend one level at a time, and every icon is still `aria-hidden`.
