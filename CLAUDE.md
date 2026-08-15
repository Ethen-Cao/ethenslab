# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Hugo static blog "Ethen 的实验室" — an Android / 智能座舱 development knowledge base. All content is written in Chinese. Published to GitHub Pages from the `master` branch via the `docs/` directory.

- Theme: PaperMod, vendored as a git submodule at `themes/PaperMod`. If missing, run `git submodule update --init`.
- `docs/` is the build output committed to git (GitHub Pages serves `master` + `/docs`). Never edit it by hand; regenerate with Hugo.
- Local work happens on `master`; `main` also exists but publishing flows to `origin master`.

## Commands

- `hugo server -D` — local preview including drafts, at http://localhost:1313/ethenslab/ (note the baseURL subpath)
- `./update-blog.sh` — build + commit + push in one step (`hugo --minify -d docs`, `git add .`, commit, push to origin master). The normal workflow after editing posts.
- `hugo new content/<section>/<post-name>.md` — scaffold a post. The archetype sets `draft: true`; flip to `draft: false` or the post will not be published.

## Content architecture

Top-level sections are the subdirectories of `content/` (`android-dev`, `android-automotive-os-dev`, `qnx`, `gunyah`, `ivi-solution`, `explore-ai`, `mcu`, `others`). Each section has an `_index.md` carrying `title`, `description`, `weight`. The homepage renders one card per top-level section, ordered by `weight`; the menu in `hugo.toml` mirrors these sections and must be kept in sync when sections are added or removed.

Post front matter is minimal: `date`, `draft`, `title`. `hugo.toml` sets `markup.goldmark.renderer.unsafe = true`, so raw HTML inside Markdown posts renders as-is.

Images live in `static/images/`, standalone diagrams in `static/diagrams/`. Reference them in Markdown relative to the site root (e.g. `images/foo.png`) so they resolve under the `/ethenslab/` baseURL.

## Layout overrides (on top of PaperMod)

Custom layouts in `layouts/` replace PaperMod's default post-list behavior:

- `layouts/index.html` + `layouts/_default/list.html` — card-based section navigation instead of a flat post list.
- `layouts/_default/_markup/render-image.html` — strips a `/static/` prefix from image paths (artifact of VS Code Markdown preview) and applies `relURL` so images resolve under the baseURL subpath.
- `layouts/_default/_markup/render-codeblock-mermaid.html` — renders ```mermaid fences as `<div class="mermaid">` for client-side rendering.
- `layouts/partials/extend_footer.html` — loads mermaid and plantuml-encoder from CDN; also renders ```plantuml fences client-side via the plantuml.com server. Posts should use mermaid/plantuml code fences for diagrams.

## Other directories

- `work/` (tracked) — scratch area for in-progress docs and analysis notes; drafts here sometimes get polished and moved into `content/`.
- `assets/` — working materials not part of the published site (plantuml jars, drawio files, prompt templates, css sources).
- `aispace/` — per-project notes (H47A, polaris, qualcomm-tools).
