#!/usr/bin/env python3
"""Build landing/site/index.html — the standalone page — from index.html.

index.html is the Artifact body fragment: content only, no <head>. The Artifact runtime supplies
the doctype, charset and viewport when the page is published. Anywhere else (opened from disk,
served by a plain static server, handed to the supervisor on the CD) those are missing, the
browser falls back to windows-1252, and every em dash, middle dot and Arabic character turns into
mojibake. This script prepends the head the runtime would have added.

Run it after editing index.html:  python3 build-site.py
"""

from pathlib import Path

HEAD = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark">
<meta name="theme-color" content="#FAFAF8" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#0B0B0A" media="(prefers-color-scheme: dark)">
<meta property="og:title" content="Isnad — your pipeline, one canvas">
<meta property="og:description" content="Drag AI agents onto a canvas, connect them into a chain, and watch research become a published video — nothing goes public until you approve it.">
<meta property="og:type" content="website">
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='7' fill='%230B0B0A'/%3E%3Cline x1='8.5' y1='16' x2='13.5' y2='16' stroke='%23FAFAF8' stroke-width='1.6'/%3E%3Cline x1='18.5' y1='16' x2='23.5' y2='16' stroke='%23FAFAF8' stroke-width='1.6'/%3E%3Ccircle cx='6.5' cy='16' r='2' fill='none' stroke='%23FAFAF8' stroke-width='1.6'/%3E%3Ccircle cx='16' cy='16' r='2' fill='none' stroke='%23FAFAF8' stroke-width='1.6'/%3E%3Ccircle cx='25.5' cy='16' r='2.6' fill='%23D7FF3A'/%3E%3C/svg%3E">
"""

root = Path(__file__).parent
fragment = (root / "index.html").read_text(encoding="utf-8")
out = root / "site" / "index.html"
out.parent.mkdir(exist_ok=True)
out.write_text(HEAD + fragment, encoding="utf-8")
print(f"wrote {out} ({out.stat().st_size:,} bytes)")
